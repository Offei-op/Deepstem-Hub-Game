"""One-time named Cloudflare tunnel setup; no credentials are printed or committed."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[1]
HOST = re.compile(r'(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}\Z')


def find_cloudflared():
    installed = shutil.which('cloudflared')
    if installed:
        return installed
    for location in ['C:/Program Files (x86)/cloudflared/cloudflared.exe',
                     'C:/Program Files/cloudflared/cloudflared.exe']:
        if Path(location).is_file():
            return location
    raise RuntimeError('Install Cloudflare Tunnel (cloudflared) before starting online access.')


def load_hosting(root):
    path = root / 'data-private' / 'permanent-hosting.json'
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        data['tunnel_id'] = str(uuid.UUID(data['tunnel_id']))
        for key in ['app_host', 'preview_host']:
            if not HOST.fullmatch(data[key]):
                raise ValueError('Invalid hostname')
        if data['app_host'] == data['preview_host']:
            raise ValueError('Preview must have an independent hostname')
        credential = root / 'data-private' / 'tunnel-credentials.json'
        contents = json.loads(credential.read_text(encoding='utf-8'))
        if contents['TunnelID'] != data['tunnel_id'] or not contents.get('TunnelSecret'):
            raise ValueError('Tunnel credentials do not match')
        return data
    except (OSError, ValueError, KeyError, TypeError):
        raise RuntimeError('Permanent hosting settings or credentials are incomplete. Run Set Up Permanent Hosting.cmd; existing services were left running.') from None


def tunnel_config(root, hosting):
    # JSON is a YAML subset, avoiding platform-specific path escaping mistakes.
    return json.dumps({
        'tunnel': hosting['tunnel_id'],
        'credentials-file': str(root / 'data-private' / 'tunnel-credentials.json'),
        'no-autoupdate': True, 'protocol': 'auto', 'edge-ip-version': '4',
        'metrics': '127.0.0.1:0',
        'ingress': [
            {'hostname': hosting['app_host'], 'service': 'http://127.0.0.1:8080'},
            {'hostname': hosting['preview_host'], 'service': 'http://127.0.0.1:8081'},
            {'service': 'http_status:404'},
        ],
    }, indent=2) + '\n'


def setup(root, domain):
    from event_network import clean_network_env
    from launcher_hosts import startup_lock
    domain = domain.strip().lower()
    if not HOST.fullmatch(domain):
        raise RuntimeError('Enter a domain such as deepstemhubgame.online, without https:// or a path.')
    binary = find_cloudflared()
    private = root / 'data-private'
    private.mkdir(exist_ok=True, mode=0o700)
    cert = Path.home() / '.cloudflared' / 'cert.pem'
    if not cert.is_file():
        print('Cloudflare will open in your browser. Sign in, select ' + domain + ', and click Authorize.', flush=True)
        print('This creates a local management certificate. Keep it private.', flush=True)
        subprocess.run([binary, 'tunnel', 'login'], check=True, env=clean_network_env())
    if not cert.is_file():
        raise RuntimeError('Cloudflare authorization has not completed. Run setup again after authorizing this domain.')

    # Explicit blank config prevents accidental inheritance of another tunnel's ingress.
    setup_config = private / 'cloudflare-setup.yml'
    setup_config.write_text('no-autoupdate: true\n', encoding='utf-8')
    command = [binary, 'tunnel', '--config', str(setup_config), '--origincert', str(cert)]

    def run(arguments):
        result = subprocess.run(command + arguments, capture_output=True, text=True,
                                env=clean_network_env(), timeout=90)
        if result.returncode:
            # Details stay in a private file rather than exposing account or credential data.
            (private / 'cloudflare-setup-error.log').write_text(result.stdout + result.stderr, encoding='utf-8')
            raise RuntimeError('Cloudflare could not complete ' + arguments[0] + '. See data-private/cloudflare-setup-error.log. No DNS records were overwritten.')
        return result.stdout

    with startup_lock(root):
        credential = private / 'tunnel-credentials.json'
        name = 'deepstem-studio-' + domain.replace('.', '-')
        if not credential.exists():
            existing = json.loads(run(['list', '--output', 'json', '--name', name]))
            if existing:
                # Never delete/recreate an existing tunnel just because its secret is missing.
                saved = Path.home() / '.cloudflared' / (existing[0]['id'] + '.json')
                if not saved.is_file():
                    raise RuntimeError('This named tunnel already exists but its credential file is missing. Restore its private credentials from backup before continuing.')
                shutil.copyfile(saved, credential)
            else:
                print('Creating the permanent studio tunnel…', flush=True)
                run(['create', '--credentials-file', str(credential), name])
        os.chmod(credential, 0o600)
        contents = json.loads(credential.read_text(encoding='utf-8'))
        hosting = {'tunnel_id': str(uuid.UUID(contents['TunnelID'])),
                   'app_host': 'studio.' + domain, 'preview_host': 'games.' + domain}
        for key in ['app_host', 'preview_host']:
            print('Connecting ' + hosting[key] + '…', flush=True)
            # No --overwrite-dns: refuse a conflicting existing record.
            run(['route', 'dns', hosting['tunnel_id'], hosting[key]])
        metadata = private / 'permanent-hosting.json'
        metadata.write_text(json.dumps(hosting, indent=2), encoding='utf-8')
        os.chmod(metadata, 0o600)
        print('Permanent addresses configured. Open Start Event Online.cmd to host the studio.', flush=True)
        print('Contestants: https://' + hosting['app_host'], flush=True)
        print('Isolated games: https://' + hosting['preview_host'], flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--domain', default='deepstemhubgame.online')
    args = parser.parse_args()
    os.chdir(ROOT)
    try:
        setup(ROOT, args.domain)
    except (RuntimeError, subprocess.SubprocessError, OSError, ValueError, KeyError) as exc:
        print('Setup stopped: ' + str(exc), flush=True)
        raise SystemExit(1)
