"""Isolated browser/load rehearsal servers; never use for the real event."""
import os
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
import uvicorn
from app.config import Settings
from app.main import create_app
from app.preview import create_preview
from app.security import PASSWORDS

if __name__=='__main__':
    run_id=os.environ.get('E2E_RUN_ID','manual-rehearsal')
    if not all(c.isalnum() or c in '-_' for c in run_id):raise SystemExit('Invalid rehearsal ID')
    path=(ROOT/'artifacts'/f'e2e-{run_id}.db').as_posix()
    settings=Settings(_env_file=None,environment='development',cookie_secure=False,
        app_origin=os.environ.get('E2E_APP_ORIGIN','http://localhost:5173'),preview_origin=os.environ.get('PREVIEW_ORIGIN','http://127.0.0.1:8001'),
        database_url='sqlite:///'+path,primary_ai_provider='mock',fallback_ai_provider='',
        openai_api_key='',gemini_api_key='',safe_retries=0,
        provider_config_path=str(ROOT/'artifacts'/f'private-{run_id}'/'providers.json'),
        admin_password_hash=PASSWORDS.hash('browser-test-password-2026'))
    target=create_app(settings) if sys.argv[1]=='api' else create_preview(settings)
    uvicorn.run(target,host='127.0.0.1',port=int(os.environ.get('E2E_API_PORT','8000')) if sys.argv[1]=='api' else int(os.environ.get('E2E_PREVIEW_PORT','8001')),access_log=False)
