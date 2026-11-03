import json
import secrets
import time
import threading
import hmac
import uuid
from urllib.parse import urlparse
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import select, func, delete
from .config import Settings, get_settings
from .db import Database, Team, LoginSession, Event, Version, Submission, Generation, Attempt, Audit, StyleReference
from .security import authenticate, login, digest, team_code, rate_limit, sign_preview, PASSWORDS, COOKIE, session_cookie
from .service import (GenerationService, event_config, save_event, remaining, require_build, totals,
                      team_dict, version_dict, request_dict, add_version, STARTERS, active_key, current_team)
from .events import dashboard_data, export_event, install_event_routes
from .references import normalize_image, reference_dict
from .validation import validate_game, InvalidGame
from pathlib import Path
from starlette.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .provider_config import load_private_config, persist_private_config, public_provider_config


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class TeamLogin(StrictModel):
    code: str = Field(min_length=3, max_length=80)


class AdminLogin(StrictModel):
    password: str = Field(min_length=1, max_length=200)


class Generate(StrictModel):
    prompt: str = Field(min_length=4, max_length=3000)
    key: str = Field(min_length=16, max_length=80, pattern=r'^[a-zA-Z0-9_-]+$')
    reference_ids: list[str] | None = Field(default=None, max_length=3)


class ReferenceUpload(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    base64: str = Field(min_length=8, max_length=2_700_000)


class TeamCreate(StrictModel):
    name: str = Field(min_length=2, max_length=80)


class Allowance(StrictModel):
    add: int = Field(default=0, ge=0, le=100)
    release_emergency: int = Field(default=0, ge=0, le=100)


class Submit(StrictModel):
    version_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=5, max_length=1000)


class EventPatch(StrictModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    theme: str | None = Field(default=None, min_length=1, max_length=120)
    announcement: str | None = Field(default=None, max_length=1000)
    paused: bool | None = None
    emergency_mode: bool | None = None
    frozen: bool | None = None
    max_teams: int | None = Field(default=None, ge=1, le=10)
    initial_allowance: int | None = Field(default=None, ge=1, le=100)
    emergency_allowance: int | None = Field(default=None, ge=0, le=100)
    budget_micro: int | None = Field(default=None, ge=0, le=1_000_000_000)
    max_concurrent: int | None = Field(default=None, ge=1, le=10)
    max_input_tokens: int | None = Field(default=None, ge=2000, le=250_000)
    max_output_tokens: int | None = Field(default=None, ge=1000, le=50_000)
    primary: Literal['openai', 'gemini', 'mock'] | None = None
    fallback: Literal['openai', 'gemini', ''] | None = None


class Timer(StrictModel):
    action: Literal['start', 'pause', 'end', 'reset']
    minutes: int = Field(default=120, ge=1, le=480)
    reopen: bool = False


class Reconcile(StrictModel):
    cost_micro: int = Field(ge=0, le=1_000_000_000)
    note: str = Field(min_length=10, max_length=1000)


class ImportGame(StrictModel):
    title: str = Field(min_length=1, max_length=100)
    html: str = Field(min_length=100, max_length=180_000)


class LocalLogin(StrictModel):
    token: str = Field(min_length=32, max_length=200)


class ProviderConnection(StrictModel):
    provider: Literal['openai', 'gemini']
    api_key: str | None = Field(default=None, min_length=10, max_length=500)
    model: str = Field(min_length=1, max_length=100)
    input_price: float = Field(ge=0, le=10000, allow_inf_nan=False)
    output_price: float = Field(ge=0, le=10000, allow_inf_nan=False)
    make_primary: bool = True


def create_app(settings: Settings | None = None, provider_factory=None):
    settings = settings or get_settings()
    load_private_config(settings)
    database = Database(settings.database_url)
    database.initialize(settings)
    service = GenerationService(database, settings, provider_factory)
    local_login_lock = threading.Lock()
    local_login_used = False

    @asynccontextmanager
    async def lifespan(app):
        yield
        await service.drain()
        database.engine.dispose()

    app = FastAPI(title='Deepstem Hub AI Game Jam Studio', lifespan=lifespan,
                  docs_url='/api/docs' if settings.environment != 'production' else None, redoc_url=None)
    app.state.database, app.state.settings, app.state.service = database, settings, service
    if settings.frontend_dir:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=[urlparse(settings.app_origin).hostname, '127.0.0.1', 'localhost'])

    @app.middleware('http')
    async def boundary(request, call_next):
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            if request.headers.get('origin') != settings.app_origin:
                return JSONResponse({'detail': 'Request origin is not permitted.'}, status_code=403)
            try:
                length = int(request.headers.get('content-length', '-1'))
            except ValueError:
                length = -1
            limit = 2_800_000 if request.url.path == '/api/references' else 256_000
            if length < 0 or length > limit:
                return JSONResponse({'detail': 'Request size is missing or too large.'}, status_code=413)
            total, chunks = 0, []
            async for chunk in request.stream():
                total += len(chunk)
                if total > limit:
                    return JSONResponse({'detail': 'Request is too large.'}, status_code=413)
                chunks.append(chunk)
            request._body = b''.join(chunks)
        response = await call_next(request)
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer', 'X-Frame-Options': 'DENY',
            'Content-Security-Policy': "default-src 'none'; frame-ancestors 'none'; base-uri 'none'",
            'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=()'})
        if settings.frontend_dir and not request.url.path.startswith('/api'):
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
                "font-src 'self'; connect-src 'self'; frame-src " + settings.preview_origin +
                "; worker-src 'none'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'")
        return response

    def auth(request, role=None):
        return authenticate(request, role)

    def owned_version(db, session, version_id):
        if session.role == 'team':
            current_team(db, session.team_id)
        version = db.get(Version, version_id)
        if not version or (session.role != 'admin' and version.team_id != session.team_id):
            raise HTTPException(404, 'Game version not found.')
        return version

    @app.get('/api/health')
    def health():
        with database.read() as db:
            db.execute(select(Event.id).limit(1))
        return {'status': 'ok'}

    @app.get('/api/setup/status')
    def setup_status():
        return {'organizer_configured': bool(settings.admin_password_hash),
                'local_access': bool(settings.local_organizer_token_hash) and settings.environment == 'development'}

    @app.post('/api/auth/local-organizer')
    def local_organizer(body: LocalLogin, request: Request, response: Response):
        nonlocal local_login_used
        if (settings.environment != 'development' or urlparse(settings.app_origin).hostname not in {'localhost', '127.0.0.1'}
                or request.client.host not in {'127.0.0.1', '::1', 'localhost'}):
            raise HTTPException(403, 'Local organizer access is available only through the local launcher.')
        with local_login_lock:
            if (local_login_used or time.time() > settings.local_organizer_token_expires
                    or not settings.local_organizer_token_hash
                    or not hmac.compare_digest(digest(body.token), settings.local_organizer_token_hash)):
                raise HTTPException(401, 'This organizer link has expired or was used. Open Start Studio again.')
            local_login_used = True
        return login(database, settings, response, 'admin')

    @app.get('/api/admin/providers')
    def provider_status(request: Request):
        auth(request, 'admin')
        return public_provider_config(settings)

    @app.post('/api/admin/providers')
    def configure_provider(body: ProviderConnection, request: Request):
        auth(request, 'admin')
        with database.write() as db:
            if db.scalar(select(func.count()).select_from(Generation).where(Generation.status == 'running')):
                raise HTTPException(409, 'Wait for active games to finish before changing the AI connection.')
            if not body.api_key and not getattr(settings, f'{body.provider}_api_key'):
                raise HTTPException(422, 'Enter an API key for this provider.')
            values = {f'{body.provider}_{field}': getattr(body, field)
                      for field in ['model', 'input_price', 'output_price']}
            if body.api_key:
                values[f'{body.provider}_api_key'] = body.api_key
            # Store privately before updating live state. Never include key material in audit/response.
            persist_private_config(settings, values)
            for key, value in values.items():
                setattr(settings, key, value)
            if body.make_primary:
                config = event_config(db)
                config['primary'] = body.provider
                if config['fallback'] == body.provider:
                    config['fallback'] = ''
                save_event(db, config)
            db.add(Audit(action=f'Updated {body.provider} connection; primary={body.make_primary}'))
        return {'providers': public_provider_config(settings), 'message': 'AI connection saved. No paid request was made.'}

    @app.post('/api/auth/team')
    def team_signin(body: TeamLogin, request: Request, response: Response):
        rate_limit(database, 'login:' + request.client.host, 20)
        with database.read() as db:
            team = db.scalar(select(Team).where(Team.code_hash == digest(body.code.upper(), settings.session_secret),
                                               Team.event_key == active_key(db)))
            if not team:
                raise HTTPException(401, 'That team code did not match. Check it with your organizer.')
            team_id = team.id
        with database.write() as db:
            current_team(db, team_id).last_seen = int(time.time())
        return login(database, settings, response, 'team', team_id)

    @app.post('/api/auth/admin')
    def admin_signin(body: AdminLogin, request: Request, response: Response):
        rate_limit(database, 'admin-login:' + request.client.host, 5)
        good = False
        if settings.admin_password_hash:
            try:
                good = PASSWORDS.verify(body.password, settings.admin_password_hash)
            except Exception:
                pass
        if not good:
            raise HTTPException(401, 'Organizer password did not match or has not been configured.')
        return login(database, settings, response, 'admin')

    @app.get('/api/auth/session')
    def session(request: Request):
        s = auth(request)
        return {'role': s.role, 'team_id': s.team_id, 'csrf': s.csrf}

    @app.post('/api/auth/logout')
    def logout(request: Request, response: Response):
        session = auth(request)
        clear_legacy = False
        with database.write() as db:
            legacy = db.get(LoginSession, digest(request.cookies.get(COOKIE, '')))
            if legacy and legacy.role == session.role:
                clear_legacy = True
                db.delete(legacy)
            db.execute(delete(LoginSession).where(LoginSession.token_hash == session.token_hash))
        response.delete_cookie(session_cookie(session.role), path='/')
        if clear_legacy:
            response.delete_cookie(COOKIE, path='/')
        return {'ok': True}

    @app.get('/api/workspace')
    def workspace(request: Request):
        s = auth(request, 'team')
        with database.write() as db:
            team = current_team(db, s.team_id)
            if team.last_seen < time.time() - 30:
                team.last_seen = int(time.time())
            c = event_config(db)
            public = {k: c[k] for k in ['theme', 'announcement', 'paused', 'emergency_mode', 'frozen', 'phase']}
            public.update(server_time=int(time.time()), remaining_seconds=remaining(c),
                          demo_mode=c['primary'] == 'mock')
            versions = list(db.scalars(select(Version).where(Version.team_id == s.team_id).order_by(Version.number)))
            submission = db.get(Submission, s.team_id)
            references = list(db.scalars(select(StyleReference).where(StyleReference.team_id == s.team_id,
                StyleReference.removed == 0).order_by(StyleReference.created, StyleReference.id)))
            return {'team': team_dict(team), 'event': public, 'versions': [version_dict(v) for v in versions],
                    'references': [reference_dict(r) for r in references],
                    'submission': {'version_id': submission.version_id, 'title': submission.title,
                        'description': submission.description, 'created': submission.created} if submission else None}

    @app.post('/api/generations', status_code=202)
    async def generate(body: Generate, request: Request):
        s = auth(request, 'team')
        rate_limit(database, f'generate:{s.team_id}', 12)
        if len(body.prompt) > settings.max_prompt_chars:
            raise HTTPException(413, 'Please shorten your prompt.')
        record, work = service.reserve(s.team_id, body.prompt, body.key, body.reference_ids)
        service.launch(work)
        return record

    @app.get('/api/generations/{request_id}')
    def generation_status(request_id: str, request: Request):
        s = auth(request)
        with database.read() as db:
            row = db.get(Generation, request_id)
            if not row or (s.role != 'admin' and row.team_id != s.team_id):
                raise HTTPException(404, 'Request not found.')
            return request_dict(row)

    def can_change_references(db, team_id):
        team = current_team(db, team_id)
        c = event_config(db)
        if c['frozen'] or c['phase'] == 'ended' or (c['phase'] == 'running' and remaining(c) <= 0):
            raise HTTPException(409, 'Building has ended. Your saved references and games are safe.')
        if team.active_request:
            raise HTTPException(409, 'Wait for your game to finish before changing reference images.')

    @app.post('/api/references', status_code=201)
    def upload_reference(body: ReferenceUpload, request: Request):
        s = auth(request, 'team')
        rate_limit(database, f'references:{s.team_id}', 12)
        # Check inexpensive authorization/quotas before decoding any supplied pixels.
        with database.read() as db:
            can_change_references(db, s.team_id)
            if db.scalar(select(func.count()).select_from(StyleReference).where(
                    StyleReference.team_id == s.team_id, StyleReference.removed == 0)) >= 3:
                raise HTTPException(409, 'Your team can save up to three reference images. Remove one to add another.')
        data, width, height, sha256 = normalize_image(body.base64)
        with database.write() as db:
            can_change_references(db, s.team_id)
            active = list(db.scalars(select(StyleReference).where(StyleReference.team_id == s.team_id, StyleReference.removed == 0)))
            if len(active) >= 3:
                raise HTTPException(409, 'Your team can save up to three reference images.')
            if any(r.sha256 == sha256 for r in active):
                raise HTTPException(409, 'This image is already in your style references.')
            if db.scalar(select(func.count()).select_from(StyleReference).where(StyleReference.team_id == s.team_id)) >= 100:
                raise HTTPException(409, 'Reference image history is full. Ask your organizer for help.')
            name = Path(body.name.replace('\\', '/')).name[:100] or 'Style reference'
            row = StyleReference(id=uuid.uuid4().hex, team_id=s.team_id, name=name, data=data,
                                 width=width, height=height, sha256=sha256)
            db.add(row)
            db.flush()
            return reference_dict(row)

    @app.get('/api/references/{reference_id}/image')
    def reference_image(reference_id: str, request: Request):
        s = auth(request)
        with database.read() as db:
            row = db.get(StyleReference, reference_id)
            if not row or (s.role != 'admin' and (row.team_id != s.team_id or row.removed)):
                raise HTTPException(404, 'Reference image not found.')
            return Response(row.data, media_type='image/jpeg', headers={
                'Content-Disposition': 'inline; filename="style-reference.jpg"'})

    @app.delete('/api/references/{reference_id}')
    def remove_reference(reference_id: str, request: Request):
        s = auth(request, 'team')
        with database.write() as db:
            can_change_references(db, s.team_id)
            row = db.get(StyleReference, reference_id)
            if not row or row.team_id != s.team_id or row.removed:
                raise HTTPException(404, 'Reference image not found.')
            row.removed = 1  # Retain the exact image used by historical requests.
            return {'ok': True}

    @app.post('/api/versions/{version_id}/restore')
    def restore(version_id: int, request: Request):
        s = auth(request, 'team')
        with database.write() as db:
            require_build(event_config(db))
            version = owned_version(db, s, version_id)
            team = current_team(db, s.team_id)
            if team.active_request:
                raise HTTPException(409, 'Wait for the current generation before restoring.')
            team.current_version = version.id
            return version_dict(version)

    @app.get('/api/versions/{version_id}/preview')
    def preview(version_id: int, request: Request):
        s = auth(request)
        with database.read() as db:
            owned_version(db, s, version_id)
        return {'url': f'{settings.preview_origin}/play/{sign_preview(settings, version_id)}',
                'expires_in': settings.preview_token_seconds}

    @app.get('/api/versions/{version_id}/download')
    def download(version_id: int, request: Request):
        s = auth(request)
        with database.read() as db:
            version = owned_version(db, s, version_id)
            return Response(version.html, media_type='application/octet-stream', headers={
                'Content-Disposition': f'attachment; filename="deepstem-team-{version.team_id}-v{version.number}.html"',
                'Content-Security-Policy': "default-src 'none'; sandbox"})

    @app.get('/api/starters')
    def starters(request: Request):
        auth(request)
        return STARTERS

    @app.post('/api/starters/{starter_id}')
    def use_starter(starter_id: str, request: Request):
        s = auth(request, 'team')
        rate_limit(database, f'starter:{s.team_id}', 10)
        starter = next((x for x in STARTERS if x['id'] == starter_id), None)
        if not starter:
            raise HTTPException(404, 'Starter not found.')
        html = (Path(__file__).parent / 'starters' / f'{starter_id}.html').read_text(encoding='utf-8')
        validate_game(html, settings.max_html_bytes)
        with database.write() as db:
            require_build(event_config(db))
            team = current_team(db, s.team_id)
            if team.active_request:
                raise HTTPException(409, 'Wait for the current generation first.')
            return version_dict(add_version(db, team, starter['title'], html, 'Selected offline starter: ' + starter['title'],
                                           starter['description'], 'starter'))

    @app.post('/api/submissions')
    def submit(body: Submit, request: Request):
        s = auth(request, 'team')
        with database.write() as db:
            require_build(event_config(db))
            version = owned_version(db, s, body.version_id)
            team = current_team(db, s.team_id)
            if team.active_request:
                raise HTTPException(409, 'Wait for your generation to finish before submitting.')
            history = json.dumps([{'version': v.number, 'prompt': v.prompt, 'created': v.created}
                for v in db.scalars(select(Version).where(Version.team_id == s.team_id).order_by(Version.number))])
            row = db.get(Submission, s.team_id)
            if not row:
                row = Submission(team_id=s.team_id)
                db.add(row)
            row.team_name, row.version_id, row.title = team.name, version.id, body.title
            row.description, row.created = body.description, int(time.time())
            row.prompt_history = history
            return {'ok': True, 'version_id': version.id, 'created': row.created}

    @app.get('/api/admin/dashboard')
    def dashboard(request: Request):
        auth(request, 'admin')
        with database.read() as db:
            return dashboard_data(db)

    @app.post('/api/admin/teams', status_code=201)
    def create_team(body: TeamCreate, request: Request):
        auth(request, 'admin')
        with database.write() as db:
            c = event_config(db)
            if db.scalar(select(func.count()).select_from(Team).where(Team.event_key == active_key(db))) >= c['max_teams']:
                raise HTTPException(409, 'Maximum number of teams reached.')
            if db.scalar(select(Team).where(func.lower(Team.name) == body.name.lower(), Team.event_key == active_key(db))):
                raise HTTPException(409, 'A team with this name already exists.')
            code = team_code()
            team = Team(name=body.name, code_hash=digest(code, settings.session_secret),
                        event_key=active_key(db), allowance=c['initial_allowance'], emergency=c['emergency_allowance'])
            db.add(team)
            db.flush()
            db.add(Audit(action=f'Created team {team.id}'))
            return {**team_dict(team), 'code': code}

    @app.post('/api/admin/teams/{team_id}/code')
    def regenerate(team_id: int, request: Request):
        auth(request, 'admin')
        with database.write() as db:
            team = current_team(db, team_id)
            if not team:
                raise HTTPException(404, 'Team not found.')
            code = team_code()
            team.code_hash = digest(code, settings.session_secret)
            db.execute(delete(LoginSession).where(LoginSession.team_id == team_id))
            db.add(Audit(action=f'Regenerated code and revoked sessions for team {team_id}'))
        return {'code': code}

    @app.post('/api/admin/teams/{team_id}/allowance')
    def allowance(team_id: int, body: Allowance, request: Request):
        auth(request, 'admin')
        with database.write() as db:
            team = current_team(db, team_id)
            if not team:
                raise HTTPException(404, 'Team not found.')
            if body.release_emergency > team.emergency:
                raise HTTPException(409, 'Not enough reserved emergency requests.')
            team.allowance += body.add + body.release_emergency
            team.emergency -= body.release_emergency
            db.add(Audit(action=f'Allowance team {team_id}: +{body.add}, emergency released {body.release_emergency}'))
            return team_dict(team)

    @app.patch('/api/admin/event')
    def update_event(body: EventPatch, request: Request):
        auth(request, 'admin')
        patch = body.model_dump(exclude_none=True)
        if settings.environment == 'production' and patch.get('primary') == 'mock':
            raise HTTPException(422, 'Mock mode is disabled in production.')
        with database.write() as db:
            c = event_config(db)
            if patch.get('max_teams', 10) < db.scalar(select(func.count()).select_from(Team).where(Team.event_key == active_key(db))):
                raise HTTPException(409, 'Team limit cannot be below the number of existing teams.')
            if 'budget_micro' in patch:
                spent, held = totals(db)
                if patch['budget_micro'] < spent + held:
                    raise HTTPException(409, 'Budget cannot be below spending plus in-flight reservations.')
            c.update(patch)
            if c['emergency_mode']:
                c['paused'] = True
            save_event(db, c)
            db.add(Audit(action='Event settings: ' + json.dumps(patch)))
            return c

    @app.post('/api/admin/timer')
    def timer(body: Timer, request: Request):
        auth(request, 'admin')
        with database.write() as db:
            c = event_config(db)
            if body.action == 'reset':
                c.update(phase='ready', remaining_seconds=body.minutes * 60, ends_at=None)
                if body.reopen:
                    if db.scalar(select(func.count()).select_from(Generation).where(Generation.status == 'running')):
                        raise HTTPException(409, 'Wait for active generations before reopening building.')
                    c.update(frozen=False, paused=False, emergency_mode=False)
            elif body.action == 'start':
                seconds = remaining(c)
                if seconds <= 0 or c['phase'] == 'ended':
                    raise HTTPException(409, 'Reset the clock before starting a new building phase.')
                c.update(phase='running', ends_at=int(time.time()) + seconds, remaining_seconds=seconds)
            elif body.action == 'pause':
                c.update(remaining_seconds=remaining(c), phase='paused', ends_at=None)
            else:
                c.update(phase='ended', remaining_seconds=0, ends_at=None, frozen=True)
            save_event(db, c)
            db.add(Audit(action='Timer: ' + body.action))
            return c

    @app.get('/api/admin/teams/{team_id}/versions')
    def inspect_versions(team_id: int, request: Request):
        auth(request, 'admin')
        with database.read() as db:
            return [version_dict(v) for v in db.scalars(select(Version).where(Version.team_id == team_id).order_by(Version.number))]

    @app.post('/api/admin/teams/{team_id}/import')
    def import_game(team_id: int, body: ImportGame, request: Request):
        auth(request, 'admin')
        try:
            validate_game(body.html, settings.max_html_bytes,
                          [settings.openai_api_key, settings.gemini_api_key, settings.session_secret, settings.preview_secret])
        except InvalidGame as exc:
            raise HTTPException(422, str(exc)) from exc
        with database.write() as db:
            require_build(event_config(db))
            team = current_team(db, team_id)
            if not team:
                raise HTTPException(404, 'Team not found.')
            if team.active_request:
                raise HTTPException(409, 'Team has an active generation.')
            db.add(Audit(action=f'Imported contingency game for team {team_id}'))
            return version_dict(add_version(db, team, body.title, body.html, 'Organizer contingency import',
                                           'Imported by your organizer.', 'import'))

    @app.post('/api/admin/requests/{request_id}/recover')
    def recover(request_id: str, request: Request):
        auth(request, 'admin')
        if any(t.get_name() == f'generation:{request_id}' and not t.done() for t in service.tasks):
            raise HTTPException(409, 'This server is still processing the request. It cannot be recovered yet.')
        with database.write() as db:
            row = db.get(Generation, request_id)
            if not row or row.status != 'running':
                raise HTTPException(409, 'Only abandoned running requests can be recovered.')
            current_team(db, row.team_id)
            safe_age = (settings.provider_timeout_seconds + 10) * (settings.safe_retries + 1) * 2 + 120
            if row.created > time.time() - safe_age:
                raise HTTPException(409, f'Request may still be running. Recovery requires an age of {safe_age} seconds.')
            row.cost_micro, row.reserved_micro = row.reserved_micro, 0
            row.status, row.error = 'failed', 'Recovered abandoned request. Cost held conservatively; reconcile provider invoice.'
            for attempt in db.scalars(select(Attempt).where(Attempt.request_id == request_id, Attempt.status == 'running')):
                attempt.status, attempt.uncertain = 'interrupted', 1
                attempt.error = 'Recovered abandoned provider call; reconcile at request level.'
            db.get(Team, row.team_id).active_request = None
            c = event_config(db)
            c['paused'] = True
            save_event(db, c)
            db.add(Audit(action=f'Recovered abandoned request {request_id}'))
            return request_dict(row)

    @app.post('/api/admin/requests/{request_id}/reconcile')
    def reconcile(request_id: str, body: Reconcile, request: Request):
        auth(request, 'admin')
        with database.write() as db:
            row = db.get(Generation, request_id)
            if not row or row.status == 'running':
                raise HTTPException(409, 'Only completed requests can be reconciled.')
            current_team(db, row.team_id)
            db.add(Audit(action=f'Reconcile {request_id}: {row.cost_micro} -> {body.cost_micro} microUSD; {body.note}'))
            row.cost_micro = body.cost_micro
            c = event_config(db)
            spent, held = totals(db)
            if spent + held >= c['budget_micro']:
                c['paused'] = True
                save_event(db, c)
            return request_dict(row)

    @app.get('/api/admin/export')
    def export(request: Request):
        auth(request, 'admin')
        with database.read() as db:
            def rows(cls, excluded=()):
                return [{col.name: getattr(row, col.name) for col in cls.__table__.columns if col.name not in excluded}
                        for row in db.scalars(select(cls))]
            data = export_event(db, event_config(db))
            data['audit'] = rows(Audit)
            return Response(json.dumps(data, indent=2), media_type='application/json',
                headers={'Content-Disposition': 'attachment; filename="deepstem-event-export.json"'})

    install_event_routes(app, database, auth)

    if settings.frontend_dir:
        class StudioFiles(StaticFiles):
            async def get_response(self, path, scope):
                if path == 'api' or path.startswith('api/'):
                    raise StarletteHTTPException(404)
                try:
                    return await super().get_response(path, scope)
                except StarletteHTTPException as exc:
                    if exc.status_code == 404 and path in {'admin', 'studio', 'guide'}:
                        return await super().get_response('index.html', scope)
                    raise
        app.mount('/', StudioFiles(directory=settings.frontend_dir, html=True), name='studio')
    return app


# Use a factory so tests, CLI and preview do not initialize an unrelated default database.
