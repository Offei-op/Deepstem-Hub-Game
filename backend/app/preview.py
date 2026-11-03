"""Read-only game origin. No app routes, sessions, API clients or API keys are loaded here."""
import sqlite3
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic_settings import BaseSettings, SettingsConfigDict
from .security import verify_preview
from .validation import preview_csp


class PreviewSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'sqlite:///./data/studio.db'
    app_origin: str = 'http://localhost:5173'
    preview_origin: str = 'http://127.0.0.1:8001'
    preview_secret: str = 'local-preview-secret-change-before-an-event-12345'
    environment: str = 'development'


def create_preview(settings=None):
    settings = settings or PreviewSettings()
    if settings.app_origin == settings.preview_origin:
        raise ValueError('Preview origin must be isolated')
    if settings.environment == 'production':
        if (urlparse(settings.preview_origin).scheme != 'https' or
            urlparse(settings.app_origin).hostname == urlparse(settings.preview_origin).hostname or
            len(settings.preview_secret) < 32 or 'local-' in settings.preview_secret):
            raise ValueError('Production requires an isolated HTTPS preview hostname and strong preview secret')
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware('http')
    async def isolate(request: Request, call_next):
        expected = urlparse(settings.preview_origin).netloc
        if request.headers.get('host') != expected:
            return JSONResponse({'detail': 'Invalid preview host'}, status_code=400)
        response = await call_next(request)
        response.headers.update({'Content-Security-Policy': preview_csp(settings.app_origin),
            'Referrer-Policy': 'no-referrer', 'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff', 'Cross-Origin-Resource-Policy': 'cross-origin',
            'Permissions-Policy': 'camera=(), microphone=(), geolocation=(), payment=(), usb=(), clipboard-write=()',
            'Origin-Agent-Cluster': '?1'})
        # Never set cookies, never vary by app session; capability tokens grant short-lived read access.
        return response

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.get('/play/{token}', response_class=HTMLResponse)
    def play(token: str):
        version_id = verify_preview(settings, token)
        path = Path(settings.database_url.removeprefix('sqlite:///')).resolve().as_posix()
        try:
            with sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=5) as db:
                row = db.execute('SELECT html FROM versions WHERE id=?', (version_id,)).fetchone()
        except sqlite3.OperationalError:
            raise HTTPException(503, 'Saved games are temporarily unavailable.')
        if not row:
            raise HTTPException(404, 'Game not found.')
        return HTMLResponse(row[0])

    return app


def create_event_preview():
    # Public event launcher supplies only these settings, never the private .env.
    return create_preview(PreviewSettings(_env_file=None))
