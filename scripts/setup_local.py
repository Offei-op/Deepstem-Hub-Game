"""Create a development .env without overwriting an existing configuration."""
import getpass
import secrets
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from app.security import PASSWORDS

if __name__=='__main__':
    target=ROOT/'.env'
    if target.exists():raise SystemExit('.env already exists. Edit it directly; nothing was overwritten.')
    password=getpass.getpass('Choose an organizer password (12+ characters): ')
    if len(password)<12 or password!=getpass.getpass('Confirm organizer password: '):
        raise SystemExit('Passwords must match and contain at least 12 characters.')
    content=(ROOT/'.env.example').read_text(encoding='utf-8')
    content=content.replace("ADMIN_PASSWORD_HASH=''",f"ADMIN_PASSWORD_HASH='{PASSWORDS.hash(password)}'")
    content=content.replace('SESSION_SECRET=local-only-change-this-secret-before-an-event-12345','SESSION_SECRET='+secrets.token_urlsafe(48))
    content=content.replace('PREVIEW_SECRET=local-preview-secret-change-before-an-event-12345','PREVIEW_SECRET='+secrets.token_urlsafe(48))
    if '--docker' not in sys.argv:
        content=content.replace('APP_ORIGIN=http://localhost:8080','APP_ORIGIN=http://localhost:5173')
        content=content.replace('DATABASE_URL=sqlite:////data/studio.db','DATABASE_URL=sqlite:///./data/studio.db')
    target.write_text(content,encoding='utf-8')
    print('Created local .env with independent secrets, your password hash and explicit mock mode.')
    print('No API keys were requested. Sign in at /admin to create teams and start the clock.')
