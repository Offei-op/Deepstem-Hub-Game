import asyncio
import hashlib
import json
import random
import time
import uuid
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy import select, func
from .db import Team, Event, Generation, Attempt, Version, Submission, Audit, StyleReference
from .references import ReferenceImage
from .prompt import SYSTEM_PROMPT, make_input
from .providers import GameOutput, ProviderError, get_provider, estimate_cost
from .validation import validate_game, InvalidGame


def event_config(db):
    return json.loads(db.get(Event, 1).config)


def active_key(db):
    return event_config(db).get('event_key', 'legacy')


def current_team(db, team_id):
    team = db.get(Team, team_id)
    if not team or team.event_key != active_key(db):
        raise HTTPException(401, 'This event has been archived. Ask your organizer for a new team code.')
    return team


def save_event(db, config):
    db.get(Event, 1).config = json.dumps(config)


def remaining(config, now=None):
    now = now or time.time()
    return max(0, int(config['ends_at'] - now)) if config['phase'] == 'running' else config['remaining_seconds']


def require_build(config):
    if config['frozen'] or config['phase'] == 'ended' or (config['phase'] == 'running' and remaining(config) <= 0):
        raise HTTPException(409, 'Building has ended. Your saved games and submission are safe.')
    if config['phase'] != 'running':
        raise HTTPException(409, 'The competition clock is not running yet.')


def totals(db, event_key=None):
    spent, held = db.execute(select(func.coalesce(func.sum(Generation.cost_micro), 0),
        func.coalesce(func.sum(Generation.reserved_micro), 0)).join(Team, Team.id == Generation.team_id).where(
            Team.event_key == (event_key if event_key is not None else active_key(db)))).one()
    return int(spent), int(held)


def version_dict(v):
    return {k: getattr(v, k) for k in ['id', 'number', 'title', 'prompt', 'explanation', 'source', 'created']}


def team_dict(t):
    return {**{k: getattr(t, k) for k in ['id', 'name', 'allowance', 'emergency', 'used', 'last_seen',
        'current_version', 'active_request']}, 'remaining': max(0, t.allowance - t.used),
        'active': t.last_seen > time.time() - 300}


def request_dict(r):
    return {**{k: getattr(r, k) for k in ['id', 'team_id', 'status', 'version_id', 'error', 'fallback',
        'created', 'duration_ms', 'cost_micro', 'reserved_micro', 'prompt']}, 'reference_ids': json.loads(r.reference_ids)}


def add_version(db, team, title, html, prompt, explanation, source='ai'):
    count = db.scalar(select(func.count()).select_from(Version).where(Version.team_id == team.id))
    if count >= 100:
        raise HTTPException(409, 'This team has reached the 100 saved version safety limit.')
    version = Version(team_id=team.id, number=count + 1, title=title[:100], html=html,
                      prompt=prompt, explanation=explanation[:2000], source=source)
    db.add(version)
    db.flush()
    team.current_version = version.id
    return version


STARTERS = [dict(id='arcade', title='Cosmic Collector', genre='Arcade', description='Catch stardust. Dodge the meteors.'),
            dict(id='platformer', title='Skybound', genre='Platformer', description='Leap between islands and find the portal.'),
            dict(id='puzzle', title='Light Circuit', genre='Puzzle', description='Turn every light on. Each move changes its neighbors.'),
            dict(id='runner', title='Neon Dash', genre='Runner', description='Jump the barriers. Keep your streak alive.'),
            dict(id='topdown', title='Garden Guardian', genre='Top-down', description='Collect blooms before the shadows catch you.')]


class GenerationService:
    def __init__(self, database, settings, provider_factory=None):
        self.database, self.settings = database, settings
        self.provider_factory = provider_factory or get_provider
        self.tasks = set()

    def reserve(self, team_id, prompt, key, reference_ids=None):
        settings = self.settings
        with self.database.write() as db:
            team = current_team(db, team_id)
            if reference_ids is None:
                reference_ids = list(db.scalars(select(StyleReference.id).where(
                    StyleReference.team_id == team_id, StyleReference.removed == 0).order_by(StyleReference.created, StyleReference.id)))
            payload_hash = hashlib.sha256(json.dumps([prompt, reference_ids], separators=(',', ':')).encode()).hexdigest()
            existing = db.scalar(select(Generation).where(Generation.team_id == team_id,
                                                        Generation.idempotency_key == key))
            if existing:
                legacy_hash = hashlib.sha256(prompt.encode()).hexdigest()
                if existing.payload_hash != payload_hash and not (not reference_ids and existing.payload_hash == legacy_hash):
                    raise HTTPException(409, 'This request key belongs to a different prompt.')
                return request_dict(existing), None
            config = event_config(db)
            require_build(config)
            if config['paused'] or config['emergency_mode']:
                raise HTTPException(409, 'AI generation is paused by the organizers. Saved games still work.')
            if len(reference_ids) > 3 or len(set(reference_ids)) != len(reference_ids):
                raise HTTPException(422, 'Choose up to three different reference images.')
            images = []
            for reference_id in reference_ids:
                reference = db.get(StyleReference, reference_id)
                if not reference or reference.team_id != team_id or reference.removed:
                    raise HTTPException(404, 'A reference image is no longer available to your team.')
                images.append(ReferenceImage(reference.data))
            if team.active_request:
                raise HTTPException(409, 'Your team already has a game being created.')
            if team.used >= team.allowance:
                raise HTTPException(429, 'Your team has used its requests. Ask an organizer for an extension.')
            count = db.scalar(select(func.count()).select_from(Generation).where(Generation.status == 'running'))
            if count >= config['max_concurrent']:
                raise HTTPException(429, 'The studio is busy. Please try again shortly.')
            if db.scalar(select(func.count()).select_from(Version).where(Version.team_id == team_id)) >= 100:
                raise HTTPException(409, 'Saved version limit reached.')
            current = db.get(Version, team.current_version) if team.current_version else None
            text = make_input(prompt, config['theme'], current.html if current else None)
            bound = (len((SYSTEM_PROMPT + text + json.dumps(GameOutput.model_json_schema())).encode()) + 1024
                     + len(images) * settings.reference_image_token_reserve)
            if bound > config['max_input_tokens']:
                raise HTTPException(413, 'This game is too large to safely modify within the input limit. Ask an organizer for help.')
            names = [config['primary']]
            if config['fallback'] and config['fallback'] != config['primary']:
                names.append(config['fallback'])
            providers = []
            try:
                # Validate both configurations before spending anything. A broken fallback is visible.
                providers = [(name, self.provider_factory(settings, name)) for name in names]
            except ProviderError as exc:
                db.add(Audit(action=f'Provider configuration blocked generation: {exc}'))
                # Commit the audit before returning the error (raising here rolls back).
                db.commit()
                raise HTTPException(503, str(exc)) from exc
            caps = [estimate_cost(p, config['max_input_tokens'], config['max_output_tokens']) for _, p in providers]
            # Safe retries only happen on explicit unbilled rejection. Reserve all potential calls anyway.
            reservation = sum(caps) * (1 + settings.safe_retries)
            spent, held = totals(db)
            if spent + held + reservation > config['budget_micro']:
                raise HTTPException(409, 'The event spending limit has been reached. Please contact an organizer.')
            request = Generation(id=str(uuid.uuid4()), team_id=team_id, idempotency_key=key,
                payload_hash=payload_hash, prompt=prompt, reference_ids=json.dumps(reference_ids), reserved_micro=reservation)
            db.add(request)
            team.active_request = request.id
            team.last_seen = int(time.time())
            db.flush()
            work = (request.id, text, config['max_output_tokens'], providers, caps, images)
            return request_dict(request), work

    def launch(self, work):
        if work:
            task = asyncio.create_task(self.run(*work), name=f'generation:{work[0]}')
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)

    async def run(self, request_id, text, max_output, providers, caps, images=None):
        started = time.monotonic()
        final_game, error, used_fallback = None, '', False
        cancelled = False
        try:
            for index, ((name, provider), cap) in enumerate(zip(providers, caps)):
                used_fallback = index > 0
                for retry in range(self.settings.safe_retries + 1):
                    attempt_started = time.monotonic()
                    with self.database.write() as db:
                        request = db.get(Generation, request_id)
                        attempt = Attempt(request_id=request_id, team_id=request.team_id, provider=name,
                            model=provider.model, status='running', fallback=int(used_fallback))
                        db.add(attempt)
                        db.flush()
                        attempt_id = attempt.id
                    kind = None
                    try:
                        call = provider.generate(text, max_output, images=images) if images else provider.generate(text, max_output)
                        result = await asyncio.wait_for(call,
                                                        timeout=self.settings.provider_timeout_seconds + 5)
                        unknown = result.input_tokens is None or result.output_tokens is None
                        cost = cap if unknown else estimate_cost(provider, result.input_tokens, result.output_tokens)
                        with self.database.write() as db:
                            attempt = db.get(Attempt, attempt_id)
                            attempt.input_tokens, attempt.output_tokens = result.input_tokens, result.output_tokens
                            attempt.cost_micro, attempt.uncertain = cost, int(unknown)
                            attempt.provider_request_id = result.provider_request_id[:180]
                            attempt.status = 'received'
                        if not result.game:
                            raise InvalidGame('The provider returned an incomplete or refused response. Try a simpler prompt.')
                        if not result.game.title.strip() or len(result.game.explanation) > 2000:
                            raise InvalidGame('The generated game metadata was invalid.')
                        validate_game(result.game.html, self.settings.max_html_bytes,
                            [self.settings.openai_api_key, self.settings.gemini_api_key,
                             self.settings.session_secret, self.settings.preview_secret])
                        final_game = result.game
                        with self.database.write() as db:
                            db.get(Attempt, attempt_id).status = 'success'
                        error = ''
                    except (ProviderError, asyncio.TimeoutError) as exc:
                        kind = exc.kind if isinstance(exc, ProviderError) else 'uncertain'
                        error = str(exc) if isinstance(exc, ProviderError) else 'Provider timed out. Your last game is safe.'
                        with self.database.write() as db:
                            attempt = db.get(Attempt, attempt_id)
                            attempt.status, attempt.error = kind, error
                            attempt.cost_micro = cap if kind == 'uncertain' else 0
                            attempt.uncertain = int(kind == 'uncertain')
                            attempt.provider_request_id = getattr(exc, 'request_id', '')[:180]
                    except InvalidGame as exc:
                        kind, error = 'invalid', str(exc)
                        with self.database.write() as db:
                            attempt = db.get(Attempt, attempt_id)
                            attempt.status, attempt.error = kind, error
                    finally:
                        with self.database.write() as db:
                            db.get(Attempt, attempt_id).duration_ms = int((time.monotonic() - attempt_started) * 1000)
                    if final_game or kind != 'rate_limit' or retry == self.settings.safe_retries:
                        break
                    await asyncio.sleep(min(4, 0.6 * (2 ** retry)) + random.uniform(0.1, 0.5))
                if final_game or kind in {'configuration', 'invalid'}:
                    break
                # An uncertain call is NOT retried at the same provider. Its full cap stays charged.
                # A single fallback is allowed only under the up-front combined budget reservation.
        except asyncio.CancelledError:
            cancelled = True
            error = 'Generation interrupted. Organizers must reconcile the reserved API cost.'
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Generation %s failed internally', request_id)
            error = 'The studio could not finish this game. Your previous version is safe; contact an organizer.'
            cancelled = True  # Preserve the full reserve on an unclassified failure.
        finally:
            with self.database.write() as db:
                request = db.get(Generation, request_id)
                team = db.get(Team, request.team_id)
                attempts = list(db.scalars(select(Attempt).where(Attempt.request_id == request_id)))
                for attempt in attempts:
                    if attempt.status == 'running':
                        attempt.status, attempt.uncertain = 'interrupted', 1
                        attempt.error = error[:1000]
                request.cost_micro = request.reserved_micro if cancelled else sum(a.cost_micro for a in attempts)
                request.reserved_micro = 0
                request.duration_ms = int((time.monotonic() - started) * 1000)
                request.fallback = int(used_fallback)
                request.error = error[:1000]
                if final_game and not cancelled:
                    version = add_version(db, team, final_game.title, final_game.html, request.prompt, final_game.explanation)
                    request.version_id, request.status = version.id, 'success'
                    team.used += 1
                else:
                    request.status = 'failed'
                team.active_request = None
                config = event_config(db)
                spent, held = totals(db)
                # Flush before totals so actual costs are included. SQLAlchemy autoflush does this.
                if spent + held >= config['budget_micro'] or any(a.uncertain for a in attempts) or cancelled:
                    config['paused'] = True
                    save_event(db, config)
                    db.add(Audit(action=f'AI paused: budget or uncertain cost after {request_id}; reconcile before resuming.'))
            for _, provider in providers:
                try:
                    await provider.close()
                except Exception:
                    pass

    async def drain(self):
        if self.tasks:
            await asyncio.gather(*list(self.tasks), return_exceptions=True)
