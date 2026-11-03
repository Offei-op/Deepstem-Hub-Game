"""Identify this checkout's local services; never stop a process by port alone."""
from contextlib import contextmanager
import os
from pathlib import Path
import re
import sqlite3
import time
import psutil

PORTS = {5173: 'frontend', 8000: 'api', 8001: 'preview', 8080: 'api', 8081: 'preview'}


def _same_path(first, second):
    return os.path.normcase(str(Path(first).resolve())) == os.path.normcase(str(Path(second).resolve()))


def _in_checkout(process, root):
    try:
        if any(_same_path(process.cwd(), path) for path in [root, root / 'frontend', root / 'backend']):
            return True
    except (psutil.Error, OSError):
        pass
    # An absolute interpreter/app path also identifies the checkout if cwd cannot be read.
    for argument in process.cmdline():
        path = Path(argument)
        if path.is_absolute():
            try:
                path.resolve().relative_to(root.resolve())
                return True
            except ValueError:
                pass
    return False


def service_kind(process, root):
    args = process.cmdline()
    if not args or not _in_checkout(process, root):
        return None
    normalized = [arg.replace('\\', '/').lower() for arg in args]
    if any(arg == 'uvicorn' or arg.endswith('/uvicorn.exe') for arg in normalized):
        if 'app.main:create_app' in normalized:
            return 'api'
        if any(name in normalized for name in ['app.preview:create_preview', 'app.preview:create_event_preview']):
            return 'preview'
    if any(arg.endswith('/vite/bin/vite.js') or arg in {'vite', 'vite.js'} for arg in normalized):
        return 'frontend'
    text = ' '.join(normalized)
    if process.name().lower() in {'node', 'node.exe', 'cmd.exe', 'npm', 'npm.cmd', 'sh', 'bash'}:
        if 'npm' in text and re.search(r'\brun\s+dev\b', text):
            return 'frontend'
    return None


def is_launcher(process, root):
    if not _in_checkout(process, root):
        return False
    for argument in process.cmdline():
        if not argument.replace('\\', '/').lower().endswith('scripts/launch.py'):
            continue
        path = Path(argument)
        if not path.is_absolute():
            path = Path(process.cwd()) / path
        if _same_path(path, root / 'scripts' / 'launch.py'):
            return True
    return False


def find_hosts(root, connections=None, process_factory=None):
    """Preflight every occupied port before returning anything that may be stopped."""
    connections = psutil.net_connections(kind='tcp') if connections is None else connections
    process_factory = process_factory or psutil.Process
    hosts, supervisors, occupied = {}, {}, set()
    for connection in connections:
        if connection.status != psutil.CONN_LISTEN or not connection.laddr:
            continue
        port = connection.laddr.port
        if port not in PORTS:
            continue
        if connection.pid is None:
            raise RuntimeError(f'Cannot identify the owner of port {port}; it was left running.')
        try:
            process = process_factory(connection.pid)
            expected = PORTS[port]
            if service_kind(process, root) != expected:
                raise RuntimeError(f'Port {port} is used by another application. It was left running; close it or free that port first.')
            occupied.add(port)
            host = process
            for parent in process.parents():
                if parent.pid == os.getpid():
                    break
                if is_launcher(parent, root):
                    supervisors[parent.pid] = parent
                    break
                if service_kind(parent, root) == expected:
                    host = parent
                else:
                    break  # Never walk into a user's terminal or an unrelated parent.
            hosts[host.pid] = host
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied as exc:
            raise RuntimeError(f'Cannot verify the process on port {port}; it was left running.') from exc
    return list(hosts.values()), list(supervisors.values()), occupied


def _service_runtime(process):
    name = process.name().lower()
    return name.startswith('python') or name in {'node', 'node.exe', 'cmd.exe', 'npm', 'npm.cmd', 'sh', 'bash', 'esbuild', 'esbuild.exe', 'cloudflared', 'cloudflared.exe'}


def stop_processes(processes, include_children=True):
    """psutil Process objects retain process identities and guard against PID reuse."""
    targets = {}
    for process in processes:
        try:
            targets[process.pid] = process
            if include_children:
                for child in process.children(recursive=True):
                    if _service_runtime(child):
                        targets[child.pid] = child
        except psutil.NoSuchProcess:
            continue
    for process in reversed(list(targets.values())):
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(list(targets.values()), timeout=3)
    for process in alive:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(alive, timeout=5)
    if alive:
        raise RuntimeError('An old studio process could not be closed. Close its terminal and try again.')


@contextmanager
def generation_guard(database_url):
    """Hold the reservation write lock until the old API is stopped, closing the check/kill race."""
    if not database_url.startswith('sqlite:///'):
        raise RuntimeError('Cannot safely check generations for this database; existing services were left running.')
    path = Path(database_url.removeprefix('sqlite:///')).resolve()
    if not path.is_file():
        raise RuntimeError('Cannot locate the running studio database; existing services were left running.')
    connection = None
    try:
        connection = sqlite3.connect(f'{path.as_uri()}?mode=rw', uri=True, timeout=5)
        connection.execute('BEGIN IMMEDIATE')
        count = connection.execute("SELECT count(*) FROM generations WHERE status='running'").fetchone()[0]
        if count:
            raise RuntimeError('A game is still generating (or needs stale-request recovery). Finish it before restarting; existing hosts were left running.')
        yield
    except sqlite3.Error as exc:
        raise RuntimeError('Cannot safely check active generations. Existing services were left running; try again shortly.') from exc
    finally:
        if connection:
            connection.rollback()
            connection.close()


def close_existing_hosts(root, database_url):
    try:
        hosts, supervisors, occupied = find_hosts(root)
        if not hosts:
            tunnels = owned_tunnels(root)
            if tunnels:
                stop_processes(tunnels)
                invalidate_online_access(root)
            return 0

        def close():
            print(f'Closing {len(hosts)} already-running Deepstem service(s)…', flush=True)
            tunnels = owned_tunnels(root)
            if tunnels:
                stop_processes(tunnels)
            invalidate_online_access(root)
            # Stop old supervisors first so their cleanup cannot race the replacement services.
            mark_intentional_restart(root, supervisors)
            stop_processes(supervisors, include_children=False)
            stop_processes(hosts)
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                busy = {c.laddr.port for c in psutil.net_connections(kind='tcp')
                        if c.status == psutil.CONN_LISTEN and c.laddr and c.laddr.port in occupied}
                if not busy:
                    return
                time.sleep(0.15)
            raise RuntimeError('Studio ports have not been released yet. Wait a moment and try again.')

        if any(PORTS[port] == 'api' for port in occupied):
            with generation_guard(database_url):
                close()
        else:
            close()  # A crashed API's persistent reservations are retained for recovery after launch.
        return len(hosts)
    except psutil.AccessDenied as exc:
        raise RuntimeError('Windows did not allow the old studio process to close. Close its terminal and retry.') from exc


def owned_tunnels(root, processes=None):
    """Find even orphaned tunnels by this checkout's exact config and origin URL."""
    config = root / 'data-private' / 'online-cloudflare.yml'
    found = []
    for process in psutil.process_iter() if processes is None else processes:
        try:
            if process.name().lower() not in {'cloudflared', 'cloudflared.exe'}:
                continue
            # A replacement launcher stages its new tunnels before stopping old hosts.
            if any(parent.pid == os.getpid() for parent in process.parents()):
                continue
            args = process.cmdline()
            if '--config' not in args:
                continue
            quick = ('--url' in args and args[args.index('--url') + 1] in
                     {'http://127.0.0.1:8080', 'http://127.0.0.1:8081'})
            named = 'run' in args and '--url' not in args
            if _same_path(args[args.index('--config') + 1], config) and (quick or named):
                found.append(process)
        except (psutil.Error, OSError, IndexError):
            continue
    return found


def invalidate_online_access(root):
    """Do not leave a ready status or a sign-in link pointing to a stopped server."""
    import json
    status_path = root / 'artifacts' / 'online-status.json'
    if status_path.exists():
        try:
            status = json.loads(status_path.read_text(encoding='utf-8'))
            status['status'] = 'stopped'
            status_path.write_text(json.dumps(status, indent=2), encoding='utf-8')
        except (ValueError, OSError):
            pass
    access = root / 'data-private' / 'online-access.html'
    if access.exists():
        access.write_text('<!doctype html><html><head><meta charset="utf-8"><title>Online studio stopped</title>'
            '<style>body{font:18px system-ui;max-width:720px;margin:60px auto;padding:24px;color:#08265b}</style>'
            '</head><body><h1>Online access is stopped</h1><p>The old public links no longer work.</p>'
            '<p>Open <strong>Start Event Online.cmd</strong> in your project folder, wait for '
            '<strong>ONLINE STUDIO IS READY</strong>, then refresh this page for the current links.</p>'
            '<p><strong>Start Studio.cmd</strong> is for local use and replaces the online server.</p>'
            '<p>Your teams, saved games and API settings are preserved.</p></body></html>', encoding='utf-8')


def mark_intentional_restart(root, supervisors):
    """Tell each owning .cmd window that replacement is intentional, not a crash."""
    for process in supervisors:
        try:
            launch_id = process.environ().get('DEEPSTEM_LAUNCH_ID', '')
        except (psutil.Error, AttributeError, OSError):
            continue
        if re.fullmatch(r'\d{1,5}-\d{1,5}-\d{1,5}', launch_id):
            directory = root / 'data-private'
            directory.mkdir(exist_ok=True, mode=0o700)
            (directory / f'restart-{launch_id}.flag').write_text('Replaced by another studio launcher.\n', encoding='utf-8')


@contextmanager
def startup_lock(root):
    """Prevent two double-clicks from starting replacement stacks simultaneously."""
    directory = root / 'data-private'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (directory / 'startup.lock').open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError('Studio startup is already in progress. Wait for that window to finish.') from exc
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
