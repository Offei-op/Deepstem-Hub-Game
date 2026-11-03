"""Public HTTPS rehearsal access. All application listeners remain on loopback."""
import html
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from urllib.parse import quote, urlparse
import webbrowser

APP_PORT, PREVIEW_PORT = 8080, 8081
URL_PATTERN = re.compile(r'https://[a-z0-9]+(?:-[a-z0-9]+)+\.trycloudflare\.com\b')
HEALTH_HEADERS = {'User-Agent': 'DeepstemStudio/1.0'}


def clean_network_env():
    # Transport and preview processes never inherit provider or organizer credentials.
    prefixes = ('OPENAI_', 'GEMINI_', 'ADMIN_', 'SESSION_', 'PREVIEW_', 'PROVIDER_', 'DATABASE_', 'LOCAL_ORGANIZER_', 'TUNNEL_', 'CLOUDFLARE_', 'CF_')
    return {k: v for k, v in os.environ.items() if not k.upper().startswith(prefixes)}


def current_provider(database_url, default):
    if not database_url.startswith('sqlite:///'):
        raise RuntimeError('Online rehearsal currently requires this studio’s SQLite database.')
    path = Path(database_url.removeprefix('sqlite:///')).resolve()
    if not path.is_file():
        return default
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5) as db:
        row = db.execute('SELECT config FROM event WHERE id=1').fetchone()
    return json.loads(row[0]).get('primary', default) if row else default


def wait_link(log_path, process, seconds=75):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('Cloudflare Tunnel stopped. See the private online-tunnel logs.')
        matches = URL_PATTERN.findall(log_path.read_text(encoding='utf-8', errors='replace'))
        if matches:
            return matches[0]
        time.sleep(.25)
    raise RuntimeError('Could not obtain an HTTPS link. Check internet access and the private online-tunnel logs.')


def wait_ready(url, process, host=None, seconds=60):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('An online service stopped. See data-private/online-*.log.')
        try:
            request = urllib.request.Request(url, headers={**HEALTH_HEADERS, **({'Host': host} if host else {})})
            with urllib.request.urlopen(request, timeout=3) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(.4)
    raise RuntimeError('The service did not become reachable. Check data-private/online-*.log.')


def reuse_online(root, no_browser=False, expected_app=None):
    import psutil
    # Reopening the online launcher should reuse working links, not break them.
    status_file = root / 'artifacts' / 'online-status.json'
    try:
        existing = json.loads(status_file.read_text(encoding='utf-8'))
        if expected_app is not None and existing.get('app_url') != expected_app:
            return False
        from launcher_hosts import is_launcher
        owner = psutil.Process(existing['pid'])
        if (existing.get('status') == 'ready' and is_launcher(owner, root) and '--share' in owner.cmdline()):
            request = urllib.request.Request(f'http://127.0.0.1:{APP_PORT}/api/health',
                headers={**HEALTH_HEADERS, 'Host': urlparse(existing['app_url']).netloc})
            with urllib.request.urlopen(request, timeout=3) as response:
                if response.status == 200:
                    # A live local process does not imply the disposable public DNS
                    # still exists. Check both external routes before reusing them.
                    for origin in [existing['app_url'], existing['preview_url']]:
                        path = '/api/health' if origin == existing['app_url'] else '/health'
                        with urllib.request.urlopen(urllib.request.Request(origin + path, headers=HEALTH_HEADERS), timeout=5) as public:
                            if public.status != 200:
                                return False
                    print('Online studio is already running. Keep its original launcher open.', flush=True)
                    print('Share with teams: ' + existing['app_url'], flush=True)
                    if not no_browser:
                        try:
                            webbrowser.open((root/'data-private'/'online-access.html').as_uri())
                        except (OSError, webbrowser.Error):
                            print('Open data-private/online-access.html manually. Online access is still running.', flush=True)
                    return True
    except (OSError, ValueError, KeyError, psutil.Error):
        pass
    return False


def run_public(root, python, npm, values, no_browser=False):
    sys.path.insert(0, str(root / 'backend'))
    import psutil
    from pwdlib import PasswordHash
    from launcher_hosts import close_existing_hosts, find_hosts, startup_lock, stop_processes
    from app.config import Settings
    from app.provider_config import load_private_config
    from permanent_network import find_cloudflared, load_hosting, tunnel_config
    hosting = load_hosting(root)
    if reuse_online(root, no_browser, expected_app='https://' + hosting['app_host'] if hosting else None):
        return 0

    cloudflared = find_cloudflared()
    # Validate the existing private configuration without printing keys or changing .env.
    base = Settings()
    load_private_config(base)
    base.primary_ai_provider = current_provider(base.database_url, base.primary_ai_provider)
    if base.primary_ai_provider == 'mock':
        raise RuntimeError('Connect an AI provider in the local organizer screen before opening public event access.')
    if not getattr(base, base.primary_ai_provider + '_api_key', ''):
        raise RuntimeError('The selected AI provider has no key. Use Connect AI locally first.')
    try:
        Settings.model_validate({**base.model_dump(), 'environment': 'production', 'cookie_secure': True,
            'app_origin': 'https://studio.example.org', 'preview_origin': 'https://games.example.net'})
    except ValueError:
        raise RuntimeError('Public settings need strong independent session/preview secrets and an organizer password hash. Existing services were left running.') from None
    print('Building the event website (no AI requests are made)…', flush=True)
    subprocess.run([npm, 'run', 'build', '--prefix', 'frontend'], check=True, cwd=root)

    private = root / 'data-private'
    private.mkdir(exist_ok=True, mode=0o700)
    empty_config = private / 'online-cloudflare.yml'
    empty_config.write_text(tunnel_config(root, hosting) if hosting else 'no-autoupdate: true\n', encoding='utf-8')
    children, managed, logs = [], [], []
    status_path = root / 'artifacts' / 'online-status.json'
    access_path = private / 'online-access.html'
    runtime_env = clean_network_env()
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    def spawn(name, command, env):
        log_path = private / f'online-{name}.log'
        log = log_path.open('w', encoding='utf-8')
        logs.append(log)
        process = subprocess.Popen(command, cwd=root, env=env, stdout=log, stderr=log, creationflags=flags)
        children.append(process)
        managed.append(psutil.Process(process.pid))
        return process, log_path

    status = {'status': 'starting'}
    try:
        with startup_lock(root):
            # Verify every occupied port belongs to this checkout. Owned public
            # services reject the replacement tunnels' new Host headers until swap.
            _, _, occupied = find_hosts(root)
            links = {}
            for name, port in ([] if hosting else [('app-tunnel', APP_PORT), ('preview-tunnel', PREVIEW_PORT)]):
                for attempt in range(3):
                    process, log_path = spawn(name, [
                        cloudflared, 'tunnel', '--config', str(empty_config), '--no-autoupdate',
                        '--protocol', 'http2', '--edge-ip-version', '4', '--url', f'http://127.0.0.1:{port}', '--loglevel', 'info',
                    ], runtime_env)
                    try:
                        links[name] = wait_link(log_path, process)
                        break
                    except RuntimeError:
                        stop_processes([managed[-1]])
                        children.remove(process)
                        if attempt == 2:
                            raise
                        print('The free tunnel service timed out; retrying this link…', flush=True)
                        time.sleep(2 ** attempt)
            if hosting:
                app_url, preview_url = 'https://' + hosting['app_host'], 'https://' + hosting['preview_host']
            else:
                app_url, preview_url = links['app-tunnel'], links['preview-tunnel']
            if urlparse(app_url).hostname == urlparse(preview_url).hostname:
                raise RuntimeError('Independent preview hostname was not allocated; online access was stopped.')

            organizer_password = secrets.token_urlsafe(24)
            settings_values = {
                **base.model_dump(), 'environment': 'production', 'cookie_secure': True,
                'app_origin': app_url, 'preview_origin': preview_url,
                'admin_password_hash': PasswordHash.recommended().hash(organizer_password),
                'frontend_dir': str(root / 'frontend' / 'dist'),
                'local_organizer_token_hash': '', 'local_organizer_token_expires': 0,
            }
            try:
                Settings.model_validate(settings_values)
            except ValueError:
                raise RuntimeError('Public settings need strong independent session/preview secrets and valid provider settings. No private values were printed.') from None
            app_env = {**os.environ, **{k.upper(): str(v) for k, v in settings_values.items() if v is not None}}
            app_env['COOKIE_SECURE'] = 'true'
            # SDK keys remain only in this API process; preview receives an explicit allowlist.
            preview_env = {
                **runtime_env, 'DATABASE_URL': base.database_url, 'APP_ORIGIN': app_url,
                'PREVIEW_ORIGIN': preview_url, 'PREVIEW_SECRET': base.preview_secret,
                'ENVIRONMENT': 'production',
            }
            # Recheck active generations atomically immediately before replacement.
            close_existing_hosts(root, base.database_url)
            api, _ = spawn('api', [
                str(python), '-m', 'uvicorn', 'app.main:create_app', '--factory',
                '--app-dir', str(root / 'backend'), '--host', '127.0.0.1', '--port', str(APP_PORT),
                '--no-access-log', '--proxy-headers', '--forwarded-allow-ips', '127.0.0.1',
            ], app_env)
            preview, _ = spawn('preview', [
                str(python), '-m', 'uvicorn', 'app.preview:create_event_preview', '--factory',
                '--app-dir', str(root / 'backend'), '--host', '127.0.0.1', '--port', str(PREVIEW_PORT),
                '--no-access-log',
            ], preview_env)
            wait_ready(f'http://127.0.0.1:{APP_PORT}/api/health', api)
            wait_ready(f'http://127.0.0.1:{PREVIEW_PORT}/health', preview, urlparse(preview_url).netloc)
            if hosting:
                # Start only after old hosts/tunnels are stopped: avoid overlapping replicas
                # sending requests to servers with different organizer sessions.
                spawn('named-tunnel', [cloudflared, 'tunnel', '--config', str(empty_config),
                    '--no-autoupdate', 'run', hosting['tunnel_id']], runtime_env)
            print('Waiting for the public HTTPS routes…', flush=True)
            wait_ready(app_url + '/api/health', api, seconds=120 if hosting else 60)
            wait_ready(preview_url + '/health', preview, seconds=120 if hosting else 60)

        private_link = app_url + '/admin#event-organizer=' + quote(organizer_password, safe='')
        access_path.write_text(
            '<!doctype html><html><head><meta charset="utf-8"><meta name="referrer" content="no-referrer"><meta http-equiv="refresh" content="60">'
            '<title>Private studio access</title><style>body{font:18px system-ui;max-width:760px;margin:60px auto;'
            'padding:24px;color:#08265b}a{display:block;margin:24px 0;padding:18px;border:1px solid #087f46;'
            'border-radius:12px;color:#087f46}code{overflow-wrap:anywhere}</style></head><body>'
            '<h1>Your online game jam</h1><p>Share ONLY the contestant link with teams.</p>'
            f'<a href="{html.escape(app_url)}" target="_blank" rel="noopener noreferrer">Contestant entrance: {html.escape(app_url)}</a>'
            f'<a href="{html.escape(private_link)}" target="_blank" rel="noopener noreferrer">PRIVATE: Open organizer control room</a>'
            '<p>The organizer button signs you in. Do not share this file, button or its address.</p>'
            f'<p>Manual organizer password: <code>{html.escape(organizer_password)}</code></p>'
            '<p>Keep the laptop powered, awake, connected to the internet, and the online launcher running. '
            + ('Your addresses stay the same after restarting. The private organizer password changes. ' if hosting else
               'Restarting creates new addresses and a new organizer password. ')
            + 'Existing games and teams stay saved.</p>'
            '<p>Rehearse with contestant laptops before event day. Public access requires this laptop to remain online.</p>'
            '</body></html>', encoding='utf-8')
        os.chmod(access_path, 0o600)
        status = {'status': 'ready', 'app_url': app_url, 'preview_url': preview_url,
                  'organizer_access_file': str(access_path), 'pid': os.getpid(), 'started': int(time.time())}
        status_path.parent.mkdir(exist_ok=True)
        status_path.write_text(json.dumps(status, indent=2), encoding='utf-8')
        print('\nONLINE STUDIO IS READY', flush=True)
        print('Share with teams: ' + app_url, flush=True)
        print('Private organizer access: ' + str(access_path), flush=True)
        print('Keep this launcher open. Ctrl+C stops public access. ' +
              ('Your domain addresses stay the same on restart.' if hosting else 'Free links change on restart.'), flush=True)
        if not no_browser:
            try:
                webbrowser.open(access_path.as_uri())
            except (OSError, webbrowser.Error):
                print('Open the private organizer access file above manually; online access is still running.', flush=True)
        next_health = time.monotonic() + 30
        while all(process.poll() is None for process in children):
            if time.monotonic() >= next_health:
                reachable = True
                for origin, path in [(app_url,'/api/health'),(preview_url,'/health')]:
                    try:
                        with urllib.request.urlopen(urllib.request.Request(origin + path, headers=HEALTH_HEADERS), timeout=5) as health:
                            reachable = reachable and health.status == 200
                    except OSError:
                        reachable = False
                status['status'] = 'ready' if reachable else 'unreachable'
                status_path.write_text(json.dumps(status, indent=2), encoding='utf-8')
                notice = '<p id="network-warning"><strong>Public link is unavailable.</strong> Reopen Start Event Online.cmd to recover it. Your saved games are safe.</p>'
                content = access_path.read_text(encoding='utf-8').replace(notice, '')
                if not reachable:
                    content = content.replace('<body>', '<body>' + notice, 1)
                    print('Public HTTPS is unavailable. Local games are preserved. Reopen Start Event Online to recover the links.', flush=True)
                access_path.write_text(content, encoding='utf-8')
                next_health = time.monotonic() + 30
            time.sleep(.5)
        raise RuntimeError('An online service or tunnel stopped. Stop and reopen Start Event Online.')
    except KeyboardInterrupt:
        print('\nStopping public access…', flush=True)
    finally:
        stop_processes(managed)
        for log in logs:
            log.close()
        if status.get('status') in {'ready', 'unreachable'}:
            from launcher_hosts import invalidate_online_access
            invalidate_online_access(root)
    return 0


def stop_public(root, values):
    from launcher_hosts import close_existing_hosts, find_hosts, startup_lock, owned_tunnels, stop_processes, invalidate_online_access
    with startup_lock(root):
        _, _, occupied = find_hosts(root)
        if not occupied.intersection({APP_PORT, PREVIEW_PORT}):
            stop_processes(owned_tunnels(root))
            invalidate_online_access(root)
            print('Online access is stopped. Local studio services were left running.')
            return 0
        database_url = os.environ.get('DATABASE_URL') or values.get('DATABASE_URL') or 'sqlite:///./data/studio.db'
        close_existing_hosts(root, database_url)
        path = root / 'artifacts' / 'online-status.json'
        if path.exists():
            status = json.loads(path.read_text(encoding='utf-8'))
            status['status'] = 'stopped'
            path.write_text(json.dumps(status, indent=2), encoding='utf-8')
    print('Online event access stopped. Your saved games and configuration are preserved.')
    return 0

