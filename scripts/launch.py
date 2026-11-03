"""One command starts all local services and opens secure local organizer access."""
import argparse
import hashlib
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import urllib.request
import venv
import webbrowser

ROOT = Path(__file__).resolve().parents[1]


def wait_for(url, process, seconds=45):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('A studio service stopped. Check artifacts/launcher-*.log for details.')
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError(f'The service at {url} did not become ready. See artifacts/launcher-*.log.')


def open_browser(url):
    try:
        if webbrowser.open(url):
            return
    except (OSError, webbrowser.Error):
        pass
    print('Automatic browser opening was unavailable. Studio is still running; open the link above manually.', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--share', action='store_true', help='Start two isolated public HTTPS rehearsal links')
    parser.add_argument('--stop-share', action='store_true', help='Stop this checkout’s online event services')
    parser.add_argument('--local', action='store_true', help='Explicitly switch from online hosting to localhost')
    args = parser.parse_args()
    os.chdir(ROOT)
    python = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        print('First launch: creating the Python environment…', flush=True)
        venv.create(ROOT / '.venv', with_pip=True)
    if Path(sys.executable).resolve() != python.resolve():
        return subprocess.call([str(python), str(Path(__file__).resolve()), *sys.argv[1:]])
    try:
        import fastapi, sqlalchemy, pwdlib, tree_sitter_javascript, uvicorn, pydantic_settings, PIL
        from openai import AsyncOpenAI
        from google import genai
    except ImportError:
        print('Preparing or repairing backend dependencies for this Python version…', flush=True)
        subprocess.run([str(python), '-m', 'pip', 'install', '--force-reinstall', '-r', 'backend/requirements.lock'], check=True)
        os.execv(str(python), [str(python), str(Path(__file__).resolve()), *sys.argv[1:]])
    try:
        import psutil
    except ImportError:
        subprocess.run([str(python), '-m', 'pip', 'install', '-r', 'backend/requirements.lock'], check=True)
        os.execv(str(python), [str(python), str(Path(__file__).resolve()), *sys.argv[1:]])
    from launcher_hosts import close_existing_hosts, startup_lock, stop_processes
    npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
    if not npm:
        raise RuntimeError('Install Node.js LTS from https://nodejs.org, then open Start Studio again.')
    if not (ROOT / 'frontend/node_modules/vite').exists():
        print('First launch: installing frontend dependencies…', flush=True)
        subprocess.run([npm, 'ci', '--prefix', 'frontend'], check=True)
    from pwdlib import PasswordHash
    from dotenv import dotenv_values
    env_path = ROOT / '.env'
    if not env_path.exists():
        content = (ROOT / '.env.example').read_text(encoding='utf-8')
        content = content.replace('APP_ORIGIN=http://localhost:8080', 'APP_ORIGIN=http://localhost:5173')
        content = content.replace('DATABASE_URL=sqlite:////data/studio.db', 'DATABASE_URL=sqlite:///./data/studio.db')
        content = content.replace('SESSION_SECRET=local-only-change-this-secret-before-an-event-12345', 'SESSION_SECRET=' + secrets.token_urlsafe(48))
        content = content.replace('PREVIEW_SECRET=local-preview-secret-change-before-an-event-12345', 'PREVIEW_SECRET=' + secrets.token_urlsafe(48))
        password = secrets.token_urlsafe(18)
        content = content.replace("ADMIN_PASSWORD_HASH=''", f"ADMIN_PASSWORD_HASH='{PasswordHash.recommended().hash(password)}'")
        env_path.write_text(content, encoding='utf-8')
        print('Created private local settings. Your organizer password is:', password, flush=True)
        print('The launcher will sign you in automatically. Save the password for manual login.', flush=True)
    values = dotenv_values(env_path)
    if values.get('ENVIRONMENT', 'development') != 'development':
        raise RuntimeError('This launcher is for local development. Use the documented production deployment for a live server.')
    if args.stop_share:
        from event_network import stop_public
        return stop_public(ROOT, values)
    if args.share:
        from event_network import run_public
        return run_public(ROOT, python, npm, values, args.no_browser)
    if not args.local:
        from event_network import reuse_online
        if reuse_online(ROOT, args.no_browser):
            return 0
    token = secrets.token_urlsafe(48)
    env = dict(os.environ, APP_ORIGIN='http://localhost:5173', PREVIEW_ORIGIN='http://127.0.0.1:8001')
    # Match security.digest (HMAC-SHA256 with an empty key), not plain SHA256.
    import hmac
    env['LOCAL_ORGANIZER_TOKEN_HASH'] = hmac.new(b'', token.encode(), hashlib.sha256).hexdigest()
    env['LOCAL_ORGANIZER_TOKEN_EXPIRES'] = str(int(time.time()) + 600)
    database_url = env.get('DATABASE_URL') or values.get('DATABASE_URL') or 'sqlite:///./data/studio.db'
    if database_url == 'sqlite:////data/studio.db':
        database_url = 'sqlite:///./data/studio.db'
    env['DATABASE_URL'] = database_url
    commands = [
        ('api', [str(python), '-m', 'uvicorn', 'app.main:create_app', '--factory', '--app-dir', str(ROOT / 'backend'), '--port', '8000', '--no-access-log']),
        ('preview', [str(python), '-m', 'uvicorn', 'app.preview:create_preview', '--factory', '--app-dir', str(ROOT / 'backend'), '--port', '8001', '--no-access-log']),
        ('frontend', [npm, 'run', 'dev', '--prefix', 'frontend', '--', '--host', '127.0.0.1', '--port', '5173', '--strictPort']),
    ]
    (ROOT / 'artifacts').mkdir(exist_ok=True)
    children, managed, logs = [], [], []
    try:
        with startup_lock(ROOT):
            close_existing_hosts(ROOT, database_url)
            for name, command in commands:
                log = (ROOT / 'artifacts' / f'launcher-{name}.log').open('w', encoding='utf-8')
                logs.append(log)
                flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                process = subprocess.Popen(command, env=env, stdout=log, stderr=log, creationflags=flags)
                children.append(process)
                managed.append(psutil.Process(process.pid))
            for url, process in zip(['http://127.0.0.1:8000/api/health', 'http://127.0.0.1:8001/health', 'http://localhost:5173'], children):
                wait_for(url, process)
        url = 'http://localhost:5173/admin#local-organizer=' + token
        print('\nStudio is ready. Keep this window open. Ctrl+C stops all three services.', flush=True)
        print('Team entrance: http://localhost:5173', flush=True)
        print('Private, one-use organizer link (expires in 10 minutes):\n' + url, flush=True)
        if not args.no_browser:
            open_browser(url)
        while all(process.poll() is None for process in children):
            time.sleep(0.5)
        stopped = [(name, process.returncode) for (name, _), process in zip(commands, children) if process.poll() is not None]
        name, code = stopped[0]
        raise RuntimeError(f'The {name} service stopped (exit code {code}). See artifacts/launcher-{name}.log.')
    except KeyboardInterrupt:
        print('\nStopping studio…', flush=True)
    finally:
        # Cached process identities prevent an old launcher from stopping reused PIDs.
        try:
            stop_processes(managed)
        except (psutil.Error, RuntimeError) as exc:
            print(f'Could not fully close a studio child process: {exc}', file=sys.stderr)
        for process in children:
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        for log in logs:
            log.close()
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print('\n' + str(exc), file=sys.stderr)
        raise SystemExit(1)
