import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
import httpx
from app.config import Settings
from app.main import create_app
from app.security import PASSWORDS
from app.providers import MockProvider

ADMIN_PASSWORD = 'test-organizer-password-2026'
ADMIN_HASH = PASSWORDS.hash(ADMIN_PASSWORD)


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, database_url='sqlite:///' + (tmp_path / 'test.db').as_posix(),
        admin_password_hash=ADMIN_HASH, safe_retries=0, provider_timeout_seconds=1,
        provider_config_path=str(tmp_path / 'private' / 'providers.json'),
        openai_api_key='', gemini_api_key='', openai_model='', gemini_model='',
        openai_input_price=None, openai_output_price=None, gemini_input_price=None, gemini_output_price=None)


@pytest.fixture
def app(settings):
    return create_app(settings)


def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://localhost:5173',
                             headers={'Origin': 'http://localhost:5173'})


@pytest.fixture
async def client(app):
    async with client_for(app) as c:
        yield c
    await app.state.service.drain()
    app.state.database.engine.dispose()


async def admin_client(app):
    client = client_for(app)
    r = await client.post('/api/auth/admin', json={'password': ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    client.headers['X-CSRF-Token'] = r.json()['csrf']
    return client


async def team_client(app, admin, name='Team Quartz'):
    r = await admin.post('/api/admin/teams', json={'name': name})
    assert r.status_code == 201, r.text
    team = r.json()
    client = client_for(app)
    r = await client.post('/api/auth/team', json={'code': team['code']})
    assert r.status_code == 200, r.text
    client.headers['X-CSRF-Token'] = r.json()['csrf']
    return client, team


async def start(admin):
    r = await admin.post('/api/admin/timer', json={'action': 'start'})
    assert r.status_code == 200, r.text


async def generate(app, client, prompt='Create an arcade game', key='test-request-key-0001'):
    r = await client.post('/api/generations', json={'prompt': prompt, 'key': key})
    assert r.status_code == 202, r.text
    await app.state.service.drain()
    result = await client.get('/api/generations/' + r.json()['id'])
    return result.json()
