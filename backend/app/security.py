import base64
import hashlib
import hmac
import json
import secrets
import time
from fastapi import HTTPException, Request
from pwdlib import PasswordHash
from sqlalchemy import delete
from .db import LoginSession, RateBucket, Team, Event

PASSWORDS = PasswordHash.recommended()
COOKIE = 'deepstem_session'


def session_cookie(role):
    return f'deepstem_{role}_session'


def digest(value: str, secret: str = '') -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def team_code():
    return 'DS-' + secrets.token_hex(5).upper()


def rate_limit(database, key: str, limit: int, seconds: int = 60):
    window = int(time.time()) // seconds
    with database.write() as db:
        row = db.get(RateBucket, key)
        if row is None:
            db.add(RateBucket(key=key, window=window, count=1))
        elif row.window != window:
            row.window, row.count = window, 1
        elif row.count >= limit:
            raise HTTPException(429, 'Too many attempts. Please wait a minute.')
        else:
            row.count += 1
        # Keep unauthenticated IP buckets bounded over a long-running event.
        db.execute(delete(RateBucket).where(RateBucket.window < window - 2))


def login(database, settings, response, role, team_id=None):
    token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    with database.write() as db:
        db.execute(delete(LoginSession).where(LoginSession.expires < int(time.time())))
        db.add(LoginSession(token_hash=digest(token), role=role, team_id=team_id, csrf=csrf,
                            expires=int(time.time()) + settings.session_hours * 3600))
    response.set_cookie(session_cookie(role), token, httponly=True, secure=settings.cookie_secure,
                        samesite='strict', max_age=settings.session_hours * 3600, path='/')
    return {'role': role, 'team_id': team_id, 'csrf': csrf}


def authenticate(request: Request, role: str | None = None):
    # Separate role cookies let an organizer test a contestant in another tab.
    # Choosing a role only selects a cookie; its stored role is always verified.
    selected = role or request.headers.get('x-studio-role') or request.query_params.get('role')
    if selected and selected not in {'admin', 'team'}:
        raise HTTPException(400, 'Unknown studio view.')
    if selected:
        token = request.cookies.get(session_cookie(selected)) or request.cookies.get(COOKIE, '')
    else:
        token = request.cookies.get(session_cookie('team')) or request.cookies.get(session_cookie('admin')) or request.cookies.get(COOKIE, '')
    with request.app.state.database.read() as db:
        session = db.get(LoginSession, digest(token))
        if not session or session.expires < time.time():
            if role and not token and any(request.cookies.get(session_cookie(r)) for r in ['team', 'admin']):
                raise HTTPException(403, 'Organizer access required.' if role == 'admin' else 'Team access required.')
            raise HTTPException(401, 'Your session has ended. Please sign in again.')
        if selected and session.role != selected:
            raise HTTPException(403 if role else 401, 'Organizer access required.' if selected == 'admin' else 'Team access required.')
        if session.role == 'team':
            team = db.get(Team, session.team_id)
            config = json.loads(db.get(Event, 1).config)
            if not team or team.event_key != config.get('event_key', 'legacy'):
                raise HTTPException(401, 'This event has been archived. Ask your organizer for a new team code.')
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), session.csrf):
                raise HTTPException(403, 'Session check failed. Refresh the page and try again.')
        return session


def sign_preview(settings, version_id):
    payload = base64.urlsafe_b64encode(json.dumps({'v': version_id, 'exp': int(time.time()) +
        settings.preview_token_seconds}, separators=(',', ':')).encode()).decode().rstrip('=')
    return payload + '.' + digest(payload, settings.preview_secret)


def verify_preview(settings, token):
    try:
        payload, signature = token.split('.')
        if not hmac.compare_digest(signature, digest(payload, settings.preview_secret)):
            raise ValueError()
        data = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
        if data['exp'] < time.time() or not isinstance(data['v'], int):
            raise ValueError()
        return data['v']
    except (ValueError, KeyError, TypeError):
        raise HTTPException(403, 'Preview link expired. Refresh the studio.')
