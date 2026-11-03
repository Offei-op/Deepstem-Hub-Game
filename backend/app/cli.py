import argparse
import getpass
import secrets
import sqlite3
from pathlib import Path
from .security import PASSWORDS
from .config import get_settings
from .db import Database


def main():
    parser = argparse.ArgumentParser(description='Deepstem studio maintenance')
    parser.add_argument('action', choices=['hash-password', 'secrets', 'init-db', 'backup'])
    parser.add_argument('--output', default='backups/studio.db')
    args = parser.parse_args()
    if args.action == 'hash-password':
        password = getpass.getpass('Organizer password (at least 12 characters): ')
        if len(password) < 12 or password != getpass.getpass('Confirm password: '):
            raise SystemExit('Password must match and contain at least 12 characters.')
        print(PASSWORDS.hash(password))
    elif args.action == 'secrets':
        print('SESSION_SECRET=' + secrets.token_urlsafe(48))
        print('PREVIEW_SECRET=' + secrets.token_urlsafe(48))
    elif args.action == 'init-db':
        s = get_settings()
        Database(s.database_url).initialize(s)
        print('Database schema v2 is ready.')
    else:
        s = get_settings()
        source = Path(s.database_url.removeprefix('sqlite:///')).resolve()
        target = Path(args.output).resolve()
        if target == source:
            raise SystemExit('Backup target must differ from live database.')
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
            src.backup(dst)
        print(f'Consistent SQLite backup saved to {target}')


if __name__ == '__main__':
    main()
