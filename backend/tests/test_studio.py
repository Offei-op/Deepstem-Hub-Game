import asyncio
import json
import time
from urllib.parse import urlparse
import httpx
import pytest
from sqlalchemy import select
from app.main import create_app
from app.db import Team, Generation, Attempt, Version, Event, Audit
from app.providers import MockProvider, ProviderError, Result, GameOutput, get_provider, classify
from app.preview import create_preview
from app.security import digest, sign_preview
from app.service import event_config, save_event
from app.validation import validate_game, InvalidGame
from conftest import admin_client, team_client, client_for, start, generate
from pathlib import Path


async def test_auth_session_csrf_and_admin_authorization(app, client):
    assert (await client.get('/api/workspace')).status_code == 401
    assert (await client.post('/api/auth/team', json={'code':'wrong'})).status_code == 401
    admin = await admin_client(app)
    team, info = await team_client(app, admin)
    session = (await team.get('/api/auth/session')).json()
    assert session['role'] == 'team'
    assert (await team.get('/api/admin/dashboard')).status_code == 403
    assert (await admin.get('/api/workspace')).status_code == 403
    team.headers.pop('X-CSRF-Token')
    assert (await team.post('/api/auth/logout',json={})).status_code == 403
    team.headers['X-CSRF-Token'] = session['csrf']
    team.headers['Origin'] = 'https://evil.example'
    assert (await team.post('/api/auth/logout',json={})).status_code == 403
    team.headers['Origin'] = 'http://localhost:5173'
    assert (await team.post('/api/auth/logout',json={})).status_code == 200
    assert (await team.get('/api/workspace')).status_code == 401
    with app.state.database.read() as db:
        assert db.get(Team, info['id']).code_hash != info['code']
    await admin.aclose(); await team.aclose()


async def test_code_rotation_revokes_sessions_and_old_code(app):
    admin = await admin_client(app)
    team, info = await team_client(app, admin)
    r = await admin.post(f"/api/admin/teams/{info['id']}/code",json={})
    assert r.status_code == 200
    assert (await team.get('/api/workspace')).status_code == 401
    assert (await team.post('/api/auth/team',json={'code':info['code']})).status_code == 401
    assert (await team.post('/api/auth/team',json={'code':r.json()['code']})).status_code == 200
    await admin.aclose(); await team.aclose()


async def test_team_isolation_version_restore_download_and_submission(app):
    admin = await admin_client(app)
    a, _ = await team_client(app,admin,'Team A')
    b, _ = await team_client(app,admin,'Team B')
    await start(admin)
    one = await generate(app,a)
    two = await generate(app,a,'Add a puzzle','test-request-key-0002')
    assert one['status'] == two['status'] == 'success'
    workspace=(await a.get('/api/workspace')).json()
    assert [v['number'] for v in workspace['versions']] == [1,2]
    assert workspace['team']['used'] == 2
    for path in ['preview','download']:
        assert (await b.get(f"/api/versions/{one['version_id']}/{path}")).status_code == 404
    assert (await b.get('/api/generations/'+one['id'])).status_code == 404
    assert (await b.post(f"/api/versions/{one['version_id']}/restore",json={})).status_code == 404
    assert (await b.post('/api/submissions',json={'version_id':one['version_id'],'title':'Steal','description':'another game'})).status_code == 404
    restored = await a.post(f"/api/versions/{one['version_id']}/restore",json={})
    assert restored.status_code == 200
    assert (await a.get('/api/workspace')).json()['team']['current_version']==one['version_id']
    download = await a.get(f"/api/versions/{one['version_id']}/download")
    assert 'attachment;' in download.headers['content-disposition']
    assert download.text.startswith('<!DOCTYPE html>')
    submit = {'version_id':one['version_id'],'title':'My game','description':'Catch all the stars'}
    assert (await a.post('/api/submissions',json=submit)).status_code == 200
    gallery = (await admin.get('/api/admin/dashboard')).json()['submissions']
    assert gallery[0]['version_id'] == one['version_id']
    exported = (await admin.get('/api/admin/export')).json()
    assert 'code_hash' not in exported['teams'][0]
    assert len(exported['versions'])==2 and exported['submissions'][0]['prompt_history']
    for c in [a,b,admin]: await c.aclose()


async def test_allowance_limit_and_failed_requests_are_refunded(settings):
    class Fail(MockProvider):
        async def generate(self,*args):
            raise ProviderError('rate_limit','Busy')
    mode={'fail':True}
    app=create_app(settings,lambda *_: Fail() if mode['fail'] else MockProvider())
    admin=await admin_client(app)
    await admin.patch('/api/admin/event',json={'initial_allowance':1})
    a,info=await team_client(app,admin)
    await start(admin)
    fail=await generate(app,a)
    assert fail['status']=='failed'
    assert (await a.get('/api/workspace')).json()['team']['used']==0
    mode['fail']=False
    success=await generate(app,a,key='test-request-key-0002')
    assert success['status']=='success'
    r=await a.post('/api/generations',json={'prompt':'Another game','key':'test-request-key-0003'})
    assert r.status_code==429
    assert (await admin.post(f"/api/admin/teams/{info['id']}/allowance",json={'release_emergency':1})).status_code==200
    assert (await a.get('/api/workspace')).json()['team']['remaining']==1
    assert (await admin.post(f"/api/admin/teams/{info['id']}/allowance",json={'release_emergency':3})).status_code==409


async def test_idempotency_and_one_active_request_per_team(settings):
    gate=asyncio.Event()
    calls=[]
    class Slow(MockProvider):
        async def generate(self,*args):
            calls.append(1);await gate.wait();return await super().generate(*args)
    app=create_app(settings,lambda *_:Slow())
    admin=await admin_client(app);a,_=await team_client(app,admin);await start(admin)
    payload={'prompt':'Make an arcade game','key':'idempotent-request-001'}
    first,duplicate,other=await asyncio.gather(a.post('/api/generations',json=payload),
        a.post('/api/generations',json=payload),
        a.post('/api/generations',json={**payload,'key':'different-request-001'}))
    assert first.status_code==duplicate.status_code==202
    assert first.json()['id']==duplicate.json()['id']
    assert other.status_code==409
    assert len(calls)==1
    with app.state.database.write() as db:
        db.get(Generation,first.json()['id']).created=int(time.time())-3600
    assert (await admin.post('/api/admin/requests/'+first.json()['id']+'/recover',json={})).status_code==409
    gate.set();await app.state.service.drain()
    repeated=await a.post('/api/generations',json=payload)
    assert repeated.json()['status']=='success' and len(calls)==1
    changed=await a.post('/api/generations',json={**payload,'prompt':'A different prompt'})
    assert changed.status_code==409
    assert (await a.get('/api/workspace')).json()['team']['used']==1


async def test_ten_concurrent_teams_and_global_concurrency_limit(settings):
    gate=asyncio.Event()
    calls=[]
    class Slow(MockProvider):
        async def generate(self,*args):
            calls.append(1);await gate.wait();return await super().generate(*args)
    app=create_app(settings,lambda *_:Slow())
    admin=await admin_client(app)
    clients=[(await team_client(app,admin,f'Team {i}'))[0] for i in range(10)]
    assert (await admin.post('/api/admin/teams',json={'name':'Eleventh team'})).status_code==409
    await start(admin)
    await admin.patch('/api/admin/event',json={'max_concurrent':2})
    first=await clients[0].post('/api/generations',json={'prompt':'An arcade game','key':'concurrent-request-000'})
    second=await clients[1].post('/api/generations',json={'prompt':'An arcade game','key':'concurrent-request-001'})
    blocked=await clients[2].post('/api/generations',json={'prompt':'An arcade game','key':'concurrent-request-002'})
    assert first.status_code==second.status_code==202 and blocked.status_code==429
    await admin.patch('/api/admin/event',json={'max_concurrent':10})
    responses=await asyncio.gather(*[c.post('/api/generations',json={'prompt':'Create an arcade game','key':f'concurrent-request-{i:03}'}) for i,c in enumerate(clients[2:],start=2)])
    assert all(r.status_code==202 for r in responses)
    dashboard=(await admin.get('/api/admin/dashboard')).json()
    assert dashboard['metrics']['running']==10
    assert len(calls)==10
    gate.set();await app.state.service.drain()
    dashboard=(await admin.get('/api/admin/dashboard')).json()
    assert dashboard['metrics']['success']==10 and dashboard['metrics']['running']==0
    assert all(t['used']==1 and not t['active_request'] for t in dashboard['teams'])


async def test_spending_ceiling_includes_inflight_reservations(settings):
    gate=asyncio.Event()
    class Paid(MockProvider):
        input_price=output_price=1.0
        async def generate(self,*args):
            await gate.wait();r=await super().generate(*args);r.input_tokens=100;r.output_tokens=200;return r
    app=create_app(settings,lambda *_:Paid())
    admin=await admin_client(app);a,_=await team_client(app,admin,'A team');b,_=await team_client(app,admin,'B team')
    await admin.patch('/api/admin/event',json={'budget_micro':67000})
    await start(admin)
    r=await a.post('/api/generations',json={'prompt':'Create game','key':'spending-request-0001'})
    assert r.status_code==202 and r.json()['reserved_micro']==67000
    assert (await b.post('/api/generations',json={'prompt':'Create game','key':'spending-request-0002'})).status_code==409
    assert (await admin.patch('/api/admin/event',json={'budget_micro':66000})).status_code==409
    gate.set();await app.state.service.drain()
    m=(await admin.get('/api/admin/dashboard')).json()['metrics']
    assert m['spent_micro']==300 and m['reserved_micro']==0


@pytest.mark.parametrize('kind,expected_fallback',[('rate_limit',True),('uncertain',True),('configuration',False)])
async def test_fallback_records_costs_and_configuration_errors(settings,kind,expected_fallback):
    calls=[]
    class Primary(MockProvider):
        input_price=output_price=1
        async def generate(self,*args):
            calls.append('primary');raise ProviderError(kind,'Provider problem')
    class Secondary(MockProvider):
        async def generate(self,*args):
            calls.append('fallback');return await super().generate(*args)
    app=create_app(settings,lambda _,name:Primary() if name=='openai' else Secondary())
    admin=await admin_client(app);a,_=await team_client(app,admin)
    await admin.patch('/api/admin/event',json={'primary':'openai','fallback':'gemini'})
    await start(admin);r=await generate(app,a)
    assert ('fallback' in calls)==expected_fallback
    assert r['status']==('success' if expected_fallback else 'failed')
    d=(await admin.get('/api/admin/dashboard')).json()
    assert len(d['attempts'])==(2 if expected_fallback else 1)
    if kind=='uncertain':
        assert d['event']['paused'] and d['metrics']['spent_micro']==67000
        assert d['attempts'][-1]['uncertain']==1
    if kind=='configuration':
        assert r['error']=='Provider problem' and d['teams'][0]['used']==0


async def test_invalid_generation_preserves_working_game_and_accounts_usage(settings):
    bad={'enabled':False}
    class SometimesBad(MockProvider):
        input_price=output_price=1
        async def generate(self,*args):
            r=await super().generate(*args)
            r.input_tokens=12;r.output_tokens=24
            if bad['enabled']:r.game.html='<html>Not a game</html>'
            return r
    app=create_app(settings,lambda *_:SometimesBad());admin=await admin_client(app);a,_=await team_client(app,admin)
    await start(admin);one=await generate(app,a);bad['enabled']=True
    two=await generate(app,a,key='invalid-output-request-2')
    assert one['status']=='success' and two['status']=='failed'
    w=(await a.get('/api/workspace')).json()
    assert len(w['versions'])==1 and w['team']['current_version']==one['version_id'] and w['team']['used']==1
    assert two['cost_micro']==36


async def test_freeze_timer_deadline_emergency_and_starters(app):
    admin=await admin_client(app);a,_=await team_client(app,admin)
    assert (await a.post('/api/starters/arcade',json={})).status_code==409
    await start(admin)
    await admin.patch('/api/admin/event',json={'emergency_mode':True})
    assert (await a.post('/api/generations',json={'prompt':'Create a game','key':'emergency-request-001'})).status_code==409
    v=(await a.post('/api/starters/arcade',json={})).json()
    body={'version_id':v['id'],'title':'Saved game','description':'A game for judging'}
    assert (await a.post('/api/submissions',json=body)).status_code==200
    await admin.patch('/api/admin/event',json={'frozen':True})
    assert (await a.post('/api/submissions',json=body)).status_code==409
    assert (await a.post(f"/api/versions/{v['id']}/restore",json={})).status_code==409
    await admin.patch('/api/admin/event',json={'frozen':False})
    with app.state.database.write() as db:
        c=event_config(db);c['ends_at']=int(time.time())-1;save_event(db,c)
    assert (await a.post('/api/submissions',json=body)).status_code==409
    assert (await a.post('/api/starters/runner',json={})).status_code==409
    assert (await a.get(f"/api/versions/{v['id']}/download")).status_code==200
    assert (await a.get(f"/api/versions/{v['id']}/preview")).status_code==200
    assert (await admin.get('/api/admin/dashboard')).json()['submissions'][0]['title']=='Saved game'


async def test_preview_isolated_signed_readonly_and_has_network_csp(app,settings):
    admin=await admin_client(app);a,_=await team_client(app,admin);await start(admin)
    v=(await a.post('/api/starters/arcade',json={})).json()
    url=(await a.get(f"/api/versions/{v['id']}/preview")).json()['url']
    assert url.startswith('http://127.0.0.1:8001/play/')
    preview=create_preview(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=preview),base_url=settings.preview_origin) as p:
        response=await p.get(url)
        assert response.status_code==200
        csp=response.headers['content-security-policy']
        assert "connect-src 'none'" in csp and 'sandbox allow-scripts' in csp and 'allow-same-origin' not in csp
        assert 'frame-ancestors http://localhost:5173' in csp
        assert 'set-cookie' not in response.headers
        assert (await p.get('/api/admin/dashboard')).status_code==404
        assert (await p.get(url+'bad')).status_code==403
        assert (await p.get(url,headers={'Host':'localhost:5173'})).status_code==400
    source=Path(__file__).resolve().parents[2].joinpath('frontend/src/components.tsx').read_text(encoding='utf-8')
    assert 'sandbox="allow-scripts"' in source and 'allow-same-origin' not in source


@pytest.mark.parametrize('slug',['arcade','platformer','puzzle','runner','topdown'])
def test_bundled_games_pass_validation(slug):
    html=(Path(__file__).resolve().parents[1]/'app/starters'/f'{slug}.html').read_text(encoding='utf-8')
    assert validate_game(html,180000)==html


@pytest.mark.parametrize('replacement',[
    '<script src="https://evil.example/x.js"></script>', '<iframe srcdoc="hi"></iframe>',
    '<meta http-equiv="refresh" content="0;url=https://evil.example">', '<a href="https://evil.example">x</a>',
    '<script>fetch("https://evil.example")</script>', '<script>eval("alert(1)")</script>',
    '<script>new Function("alert(1)")</script>', '<script>window.location="https://evil.example"</script>',
    '<script>parent.document.body.textContent="bad"</script>', '<script>localStorage.getItem("secret")</script>',
    '<img src="data:image/svg+xml,bad">', '<button onclick="alert(1)">x</button>',
])
def test_rejects_prohibited_html(replacement):
    html=(Path(__file__).resolve().parents[1]/'app/starters/arcade.html').read_text(encoding='utf-8')
    with pytest.raises(InvalidGame):validate_game(html.replace('</body>',replacement+'</body>'),180000)


def test_size_structure_secrets_validation():
    with pytest.raises(InvalidGame):validate_game('x'*200,100)
    with pytest.raises(InvalidGame):validate_game('<html></html>',180000)
    html=(Path(__file__).resolve().parents[1]/'app/starters/arcade.html').read_text(encoding='utf-8')
    with pytest.raises(InvalidGame):validate_game(html.replace('</body>','secret-api-value</body>'),180000,['secret-api-value'])
    with pytest.raises(InvalidGame):validate_game(html.replace("'use strict';",'const broken = ;'),180000)


def test_environment_template_loads_blank_prices_without_real_keys():
    from app.config import Settings
    s=Settings(_env_file=Path(__file__).resolve().parents[2]/'.env.example')
    assert s.primary_ai_provider=='mock' and s.openai_input_price is None


async def test_stale_recovery_and_reconciliation(app):
    admin=await admin_client(app);a,team=await team_client(app,admin)
    with app.state.database.write() as db:
        r=Generation(id='abandoned',team_id=team['id'],idempotency_key='abandoned-request',payload_hash='x',
                     prompt='Lost request',reserved_micro=10000,created=int(time.time())-3600)
        db.add(r);db.get(Team,team['id']).active_request='abandoned'
    r=await admin.post('/api/admin/requests/abandoned/recover',json={})
    assert r.status_code==200 and r.json()['cost_micro']==10000
    assert (await a.get('/api/workspace')).json()['team']['active_request'] is None
    r=await admin.post('/api/admin/requests/abandoned/reconcile',json={'cost_micro':1250,'note':'Confirmed from provider invoice export.'})
    assert r.status_code==200 and r.json()['cost_micro']==1250
    assert (await admin.get('/api/admin/dashboard')).json()['event']['paused']
    with app.state.database.read() as db:
        assert any('Reconcile abandoned' in row.action for row in db.scalars(select(Audit)))


def test_production_config_rejects_unsafe_origins(settings):
    from app.config import Settings
    with pytest.raises(ValueError):Settings(_env_file=None,environment='production')
    with pytest.raises(ValueError):Settings(_env_file=None,preview_origin='http://localhost:5173')


def test_provider_sdk_configuration_and_error_classification(settings):
    from google.genai import types
    from openai import AsyncOpenAI
    assert hasattr(AsyncOpenAI(api_key='unit-test').responses,'parse')
    assert types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)).retry_options.attempts==1
    with pytest.raises(ProviderError):get_provider(settings,'openai')
    class Error(Exception):pass
    error=Error();error.status_code=429;error.body={'code':'insufficient_quota'}
    assert classify(error).kind=='configuration'
    error.body={};assert classify(error).kind=='rate_limit'
    error.status_code=500;assert classify(error).kind=='uncertain'
    from google.genai.errors import ClientError
    google_billing=ClientError(429,{'error':{'message':'Billing quota exhausted','status':'RESOURCE_EXHAUSTED'}})
    assert classify(google_billing).kind=='configuration'


async def test_independent_services_cannot_reserve_same_team_twice(settings):
    from fastapi import HTTPException
    first=create_app(settings);second=create_app(settings)
    admin=await admin_client(first);a,_=await team_client(first,admin);await start(admin)
    team_id=(await a.get('/api/workspace')).json()['team']['id']
    async def reserve(app,key):
        try:
            return await asyncio.to_thread(app.state.service.reserve,team_id,'Create a simple arcade game',key)
        except HTTPException as exc:
            return exc.status_code
    results=await asyncio.gather(reserve(first,'independent-service-0001'),reserve(second,'independent-service-0002'))
    assert sum(isinstance(r,tuple) for r in results)==1 and 409 in results
    for app,result in zip([first,second],results):
        if isinstance(result,tuple):
            app.state.service.launch(result[1]);await app.state.service.drain()
    assert (await a.get('/api/workspace')).json()['team']['used']==1


async def test_both_providers_fail_preserves_allowance(settings):
    class Busy(MockProvider):
        async def generate(self,*args):raise ProviderError('rate_limit','Both services are busy.')
    app=create_app(settings,lambda *_:Busy())
    admin=await admin_client(app);a,_=await team_client(app,admin)
    await admin.patch('/api/admin/event',json={'primary':'openai','fallback':'gemini'})
    await start(admin);r=await generate(app,a)
    assert r['status']=='failed' and r['fallback']==1
    d=(await admin.get('/api/admin/dashboard')).json()
    assert len(d['attempts'])==2 and d['teams'][0]['used']==0 and not d['teams'][0]['active_request']


async def test_safe_retries_are_bounded_and_recorded(settings):
    settings.safe_retries=1
    calls=[]
    class Busy(MockProvider):
        async def generate(self,*args):calls.append(1);raise ProviderError('rate_limit','Temporarily busy.')
    app=create_app(settings,lambda *_:Busy())
    admin=await admin_client(app);a,_=await team_client(app,admin);await start(admin)
    r=await generate(app,a)
    assert r['status']=='failed' and len(calls)==2
    assert len((await admin.get('/api/admin/dashboard')).json()['attempts'])==2


async def test_unknown_usage_holds_conservative_estimate_and_pauses(settings):
    class Unknown(MockProvider):
        input_price=output_price=1
        async def generate(self,*args):
            r=await super().generate(*args);r.input_tokens=None;r.output_tokens=None;return r
    app=create_app(settings,lambda *_:Unknown());admin=await admin_client(app);a,_=await team_client(app,admin)
    await start(admin);r=await generate(app,a)
    assert r['status']=='success' and r['cost_micro']==67000
    assert (await admin.get('/api/admin/dashboard')).json()['event']['paused']


async def test_expired_sessions_and_preview_tokens_are_rejected(app,settings):
    from app.db import LoginSession
    import base64
    admin=await admin_client(app);a,_=await team_client(app,admin)
    with app.state.database.write() as db:
        sessions=list(db.scalars(select(LoginSession).where(LoginSession.role=='team')))
        sessions[0].expires=int(time.time())-1
    assert (await a.get('/api/workspace')).status_code==401
    payload=base64.urlsafe_b64encode(json.dumps({'v':1,'exp':int(time.time())-1}).encode()).decode().rstrip('=')
    token=payload+'.'+digest(payload,settings.preview_secret)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_preview(settings)),base_url=settings.preview_origin) as p:
        assert (await p.get('/play/'+token)).status_code==403
