"""Public entry and isolation checks: no external AI calls or real credentials."""
import sys
from pathlib import Path
import httpx
import pytest
from app.main import create_app
from app.preview import create_event_preview

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from event_network import clean_network_env, URL_PATTERN


def test_reopening_launcher_reuses_healthy_online_session(tmp_path, monkeypatch):
    import json
    from unittest.mock import Mock, MagicMock
    import event_network
    import launcher_hosts
    (tmp_path/'artifacts').mkdir()
    status = {'status':'ready','pid':12345,'app_url':'https://current.example.org','preview_url':'https://preview.example.net'}
    path = tmp_path/'artifacts'/'online-status.json'
    path.write_text(json.dumps(status))
    monkeypatch.setattr('psutil.Process', lambda _:Mock(cmdline=lambda:['python','scripts/launch.py','--share']))
    monkeypatch.setattr(launcher_hosts,'is_launcher',lambda *_:True)
    response=MagicMock()
    response.__enter__.return_value.status=200
    check=Mock(return_value=response)
    monkeypatch.setattr(event_network.urllib.request,'urlopen',check)
    assert event_network.reuse_online(tmp_path,no_browser=True)
    assert check.call_args_list[0].args[0].get_header('Host') == 'current.example.org'
    assert json.loads(path.read_text()) == status
    check.side_effect=OSError('No server listening')
    assert not event_network.reuse_online(tmp_path,no_browser=True)
    check.side_effect=[response, OSError('Public DNS no longer exists')]
    assert not event_network.reuse_online(tmp_path,no_browser=True)


@pytest.fixture
def public_app(settings, tmp_path):
    built = tmp_path / 'dist'
    built.mkdir()
    (built / 'index.html').write_text('<!doctype html><title>Studio</title><h1>Public studio</h1>', encoding='utf-8')
    (built / 'studio.js').write_text('console.log("studio")', encoding='utf-8')
    settings.frontend_dir = str(built)
    settings.app_origin = 'https://studio.example.org'
    settings.preview_origin = 'https://games.example.net'
    settings.cookie_secure = True
    app = create_app(settings)
    yield app
    app.state.database.engine.dispose()


async def test_public_entry_serves_only_build_and_preserves_api_authorization(public_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=public_app), base_url='https://studio.example.org') as client:
        for path in ['/', '/admin']:
            response = await client.get(path)
            assert response.status_code == 200
            assert 'Public studio' in response.text
            csp = response.headers['content-security-policy']
            assert 'frame-src https://games.example.net;' in csp
            assert "script-src 'self';" in csp
            assert "frame-ancestors 'none'" in csp
        assert (await client.get('/studio.js')).status_code == 200
        for path in ['/.env', '/data-private/providers.json', '/src/App.tsx', '/api/missing']:
            assert (await client.get(path)).status_code == 404
        assert (await client.get('/api/admin/dashboard')).status_code == 401
        assert (await client.get('/', headers={'Host': 'attacker.invalid'})).status_code == 400


async def test_public_cookie_is_host_only_secure_and_csrf_is_enforced(public_app):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=public_app), base_url='https://studio.example.org') as client:
        response = await client.post('/api/auth/admin', headers={'Origin':'https://studio.example.org'},
                                     json={'password':'test-organizer-password-2026'})
        assert response.status_code == 200
        cookie = response.headers['set-cookie'].lower()
        assert 'secure' in cookie and 'httponly' in cookie and 'samesite=strict' in cookie
        assert 'domain=' not in cookie
        assert (await client.patch('/api/admin/event', headers={'Origin':'https://studio.example.org'}, json={'paused':True})).status_code == 403
        assert (await client.post('/api/auth/admin', headers={'Origin':'https://games.example.net'}, json={'password':'test-organizer-password-2026'})).status_code == 403
        assert (await client.post('/api/auth/local-organizer', headers={'Origin':'https://studio.example.org'}, json={'token':'x'*48})).status_code == 403


def test_preview_and_transport_environment_does_not_inherit_credentials(monkeypatch):
    for key in ['OPENAI_API_KEY','GEMINI_API_KEY','ADMIN_PASSWORD_HASH','SESSION_SECRET','PREVIEW_SECRET','TUNNEL_TOKEN','PROVIDER_CONFIG_PATH']:
        monkeypatch.setenv(key, 'private-test-value')
    clean = clean_network_env()
    assert not any(key in clean for key in ['OPENAI_API_KEY','GEMINI_API_KEY','ADMIN_PASSWORD_HASH','SESSION_SECRET','PREVIEW_SECRET','TUNNEL_TOKEN','PROVIDER_CONFIG_PATH'])


def test_tunnel_discovery_never_mistakes_api_error_urls_for_a_public_link():
    assert not URL_PATTERN.findall('Post "https://api.trycloudflare.com/tunnel": timeout')
    assert URL_PATTERN.findall('Visit https://green-forest-tiny-robot.trycloudflare.com') == ['https://green-forest-tiny-robot.trycloudflare.com']


async def test_event_preview_remains_cookieless_and_rejects_app_host(monkeypatch, tmp_path):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + str(tmp_path / 'unused.db'))
    monkeypatch.setenv('APP_ORIGIN', 'https://studio.example.org')
    monkeypatch.setenv('PREVIEW_ORIGIN', 'https://games.example.net')
    monkeypatch.setenv('PREVIEW_SECRET', 's' * 48)
    monkeypatch.setenv('ENVIRONMENT', 'production')
    app = create_event_preview()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://games.example.net') as client:
        response = await client.get('/health')
        assert response.status_code == 200
        assert 'set-cookie' not in response.headers
        csp = response.headers['content-security-policy']
        assert "connect-src 'none'" in csp and 'sandbox allow-scripts' in csp
        assert 'allow-same-origin' not in csp
        assert 'frame-ancestors https://studio.example.org' in csp
        assert (await client.get('/api/admin/dashboard')).status_code == 404
        assert (await client.get('/health', headers={'Host':'studio.example.org'})).status_code == 400
