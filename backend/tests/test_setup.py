import json
import time
from pathlib import Path
from sqlalchemy import select
from app.main import create_app
from app.security import digest
from app.db import Audit, Generation
from conftest import admin_client, team_client, client_for


async def test_provider_setup_private_persistent_and_never_returned(settings):
    app=create_app(settings)
    admin=await admin_client(app)
    team,_=await team_client(app,admin)
    assert (await team.get('/api/admin/providers')).status_code==403
    assert (await admin.get('/api/admin/providers')).json()['openai']['configured'] is False
    key='unit-test-key-not-a-real-provider-secret'
    payload={'provider':'openai','api_key':key,'model':'unit-test-model','input_price':1.5,'output_price':4,'make_primary':True}
    assert (await team.post('/api/admin/providers',json=payload)).status_code==403
    response=await admin.post('/api/admin/providers',json=payload)
    assert response.status_code==200 and key not in response.text
    assert response.json()['providers']['openai']['configured']
    assert (await admin.get('/api/admin/dashboard')).json()['event']['primary']=='openai'
    assert app.state.settings.openai_api_key==key
    private=json.loads(Path(settings.provider_config_path).read_text(encoding='utf-8'))
    assert private['openai_api_key']==key
    assert key not in (await admin.get('/api/admin/export')).text
    # Blank replacement retains the stored key; no paid provider is contacted.
    assert (await admin.post('/api/admin/providers',json={**payload,'api_key':None,'model':'updated-model'})).status_code==200
    assert app.state.settings.openai_api_key==key
    from app.config import Settings
    fresh=Settings.model_validate({**settings.model_dump(),'openai_api_key':'','openai_model':''})
    restarted=create_app(fresh)
    assert restarted.state.settings.openai_api_key==key and restarted.state.settings.openai_model=='updated-model'
    with app.state.database.read() as db:
        assert all(key not in a.action for a in db.scalars(select(Audit)))


async def test_provider_setup_requires_key_finite_prices_and_csrf(app):
    admin=await admin_client(app)
    payload={'provider':'gemini','api_key':None,'model':'test','input_price':1,'output_price':2}
    assert (await admin.post('/api/admin/providers',json=payload)).status_code==422
    assert (await admin.post('/api/admin/providers',json={**payload,'api_key':'not-real-test-key','output_price':-1})).status_code==422
    admin.headers.pop('X-CSRF-Token')
    assert (await admin.post('/api/admin/providers',json={**payload,'api_key':'not-real-test-key'})).status_code==403


async def test_local_organizer_link_is_single_use_and_expiring(settings):
    token='launcher-token-with-at-least-thirty-two-characters'
    settings.local_organizer_token_hash=digest(token)
    settings.local_organizer_token_expires=int(time.time())+60
    app=create_app(settings)
    async with client_for(app) as client:
        assert (await client.post('/api/auth/local-organizer',json={'token':token+'bad'})).status_code==401
        response=await client.post('/api/auth/local-organizer',json={'token':token})
        assert response.status_code==200 and response.json()['role']=='admin'
        assert (await client.post('/api/auth/local-organizer',json={'token':token})).status_code==401
        assert (await client.get('/api/admin/dashboard')).status_code==200
    settings.local_organizer_token_expires=int(time.time())-1
    expired=create_app(settings)
    async with client_for(expired) as client:
        assert (await client.post('/api/auth/local-organizer',json={'token':token})).status_code==401


async def test_setup_status_does_not_leak_credentials(app):
    async with client_for(app) as c:
        response=await c.get('/api/setup/status')
        assert response.status_code==200
        assert set(response.json())=={'organizer_configured','local_access'}
