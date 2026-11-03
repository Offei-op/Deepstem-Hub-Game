import asyncio
import base64
import io
import json
import sqlite3
from pathlib import Path
from unittest.mock import AsyncMock, Mock
import pytest
from PIL import Image
from sqlalchemy import select
from app.db import Team, Event, Version, Generation, StyleReference, Database, Meta
from app.providers import MockProvider, OpenAIProvider, GeminiProvider, ProviderError, Result, classify
from app.references import ReferenceImage
from app.service import event_config, save_event
from conftest import admin_client, team_client, client_for, start, generate


def image_payload(colour='red', size=(1200, 800)):
    buffer = io.BytesIO()
    Image.new('RGB', size, colour).save(buffer, format='PNG')
    return {'name': 'style.png', 'base64': base64.b64encode(buffer.getvalue()).decode('ascii')}


def next_event(key='legacy'):
    return {'expected_event_key': key, 'confirmation': 'NEW EVENT', 'name': 'Fresh competition',
            'theme': 'Gravity', 'minutes': 90, 'budget_micro': 8_000_000,
            'initial_allowance': 10, 'emergency_allowance': 2, 'max_teams': 10}


async def test_references_are_private_resized_and_atomically_limited(app):
    admin = await admin_client(app)
    team, info = await team_client(app, admin)
    other, _ = await team_client(app, admin, 'Other team')
    responses = await asyncio.gather(*[team.post('/api/references', json=image_payload(colour))
                                      for colour in ['red', 'green', 'blue', 'orange']])
    assert sorted(r.status_code for r in responses) == [201, 201, 201, 409]
    references = (await team.get('/api/workspace')).json()['references']
    assert len(references) == 3
    first = references[0]
    assert max(first['width'], first['height']) == 768
    response = await team.get(first['url'])
    assert response.headers['content-type'] == 'image/jpeg'
    assert response.headers['cache-control'] == 'no-store'
    assert Image.open(io.BytesIO(response.content)).format == 'JPEG'
    assert (await other.get(first['url'])).status_code == 404
    assert (await other.request('DELETE', '/api/references/' + first['id'], json={})).status_code == 404
    async with client_for(app) as anonymous:
        assert (await anonymous.get(first['url'])).status_code == 401
    assert (await team.request('DELETE', '/api/references/' + first['id'], json={})).status_code == 200
    assert (await team.get(first['url'])).status_code == 404
    assert len((await team.get('/api/workspace')).json()['references']) == 2
    assert (await team.post('/api/references', json=image_payload('purple'))).status_code == 201
    await team.aclose(); await other.aclose(); await admin.aclose()


@pytest.mark.parametrize('payload', [
    {'name':'bad.png', 'base64':'this is not base64!'},
    {'name':'bad.jpg', 'base64':base64.b64encode(b'<svg onload="alert(1)"></svg>').decode()},
    {'name':'tiny.png', **{'base64':image_payload(size=(1,1))['base64']}},
])
async def test_invalid_images_never_enter_database(app, payload):
    admin = await admin_client(app)
    team, _ = await team_client(app, admin)
    assert (await team.post('/api/references', json=payload)).status_code == 422
    assert (await team.get('/api/workspace')).json()['references'] == []
    await team.aclose(); await admin.aclose()


async def test_images_reach_generation_and_request_identity_cannot_change(app):
    calls = []
    class RecordingProvider(MockProvider):
        async def generate(self, text, max_output, images=None):
            calls.append(images)
            return await super().generate(text, max_output, images)
    app.state.service.provider_factory = lambda *_: RecordingProvider()
    admin = await admin_client(app)
    team, _ = await team_client(app, admin)
    reference = (await team.post('/api/references', json=image_payload())).json()
    await start(admin)
    body = {'prompt':'Create a bright arcade game', 'key':'image-request-key-01', 'reference_ids':[reference['id']]}
    response = await team.post('/api/generations', json=body)
    assert response.status_code == 202, response.text
    await app.state.service.drain()
    assert len(calls) == 1 and len(calls[0]) == 1
    assert calls[0][0].mime_type == 'image/jpeg'
    assert calls[0][0].data == (await team.get(reference['url'])).content
    assert (await team.post('/api/generations', json=body)).json()['id'] == response.json()['id']
    assert (await team.post('/api/generations', json={**body,'reference_ids':[]})).status_code == 409
    assert (await team.get('/api/workspace')).json()['team']['used'] == 1
    request = (await team.get('/api/generations/' + response.json()['id'])).json()
    assert request['reference_ids'] == [reference['id']]
    await team.request('DELETE', '/api/references/' + reference['id'], json={})
    assert (await admin.get(reference['url'])).status_code == 200  # historical evidence retained
    await team.aclose(); await admin.aclose()


async def test_reference_ownership_token_bound_and_generation_lock(app):
    gate = asyncio.Event()
    class WaitingProvider(MockProvider):
        async def generate(self, text, max_output, images=None):
            await gate.wait()
            return await super().generate(text, max_output, images)
    app.state.service.provider_factory = lambda *_: WaitingProvider()
    admin = await admin_client(app)
    team, _ = await team_client(app, admin)
    other, _ = await team_client(app, admin, 'Other team')
    reference = (await team.post('/api/references', json=image_payload())).json()
    await start(admin)
    body = {'prompt':'Create an arcade game', 'key':'locked-image-request', 'reference_ids':[reference['id']]}
    assert (await other.post('/api/generations', json=body)).status_code == 404
    await admin.patch('/api/admin/event', json={'max_input_tokens':2000})
    assert (await team.post('/api/generations', json=body)).status_code == 413
    assert not app.state.service.tasks
    await admin.patch('/api/admin/event', json={'max_input_tokens':55000})
    assert (await team.post('/api/generations', json=body)).status_code == 202
    assert (await team.request('DELETE', '/api/references/' + reference['id'], json={})).status_code == 409
    assert (await team.post('/api/references', json=image_payload('blue'))).status_code == 409
    assert (await admin.post('/api/admin/events', json=next_event())).status_code == 409
    gate.set(); await app.state.service.drain()
    await admin.post('/api/admin/timer', json={'action':'end'})
    assert (await team.request('DELETE', '/api/references/' + reference['id'], json={})).status_code == 409
    await admin.post('/api/admin/timer', json={'action':'reset','minutes':120,'reopen':True})
    dashboard = (await admin.get('/api/admin/dashboard')).json()
    assert not dashboard['event']['frozen'] and dashboard['event']['phase'] == 'ready'
    assert (await team.request('DELETE', '/api/references/' + reference['id'], json={})).status_code == 200
    await team.aclose(); await other.aclose(); await admin.aclose()


async def test_new_event_preserves_history_revokes_old_access_and_isolates_spending(app):
    admin = await admin_client(app)
    team, info = await team_client(app, admin, 'Team reusable name')
    reference = (await team.post('/api/references', json=image_payload())).json()
    await start(admin)
    result = await generate(app, team)
    version_id = result['version_id']
    await team.post('/api/submissions', json={'version_id':version_id,'title':'First event game','description':'A saved final entry.'})
    with app.state.database.write() as db:
        db.get(Generation, result['id']).cost_micro = 750_000
    before = (await admin.get('/api/admin/dashboard')).json()
    response = await admin.post('/api/admin/events', json=next_event())
    assert response.status_code == 201, response.text
    archive_id = response.json()['archived_event_id']
    assert (await admin.post('/api/admin/events', json=next_event())).status_code == 409
    assert (await team.get('/api/workspace')).status_code == 401
    assert (await team.post('/api/auth/team', json={'code':info['code']})).status_code == 401
    active = (await admin.get('/api/admin/dashboard')).json()
    assert active['metrics']['teams'] == active['metrics']['spent_micro'] == active['metrics']['requests'] == 0
    assert active['event']['remaining_seconds'] == 5400
    assert active['event']['phase'] == 'ready' and not active['event']['frozen']
    assert active['event']['primary'] == before['event']['primary']
    archived = (await admin.get(f'/api/admin/events/{archive_id}')).json()
    assert archived['archived'] and archived['metrics']['spent_micro'] == 750_000
    assert archived['submissions'][0]['title'] == 'First event game'
    assert (await admin.get(f'/api/versions/{version_id}/download')).status_code == 200
    assert (await admin.get(f'/api/versions/{version_id}/preview')).status_code == 200
    export = (await admin.get(f'/api/admin/events/{archive_id}/export')).json()
    assert export['references'][0]['id'] == reference['id'] and export['references'][0]['base64']
    assert 'code_hash' not in export['teams'][0]
    fresh, fresh_info = await team_client(app, admin, 'Team reusable name')
    assert fresh_info['id'] != info['id']
    assert (await fresh.get(f'/api/versions/{version_id}/preview')).status_code == 404
    assert (await fresh.get(reference['url'])).status_code == 404
    assert (await fresh.get(f'/api/admin/events/{archive_id}')).status_code == 403
    assert (await admin.post(f"/api/admin/teams/{info['id']}/allowance", json={'add':2})).status_code == 401
    assert (await admin.get('/api/admin/export')).json()['versions'] == []
    await fresh.aclose(); await team.aclose(); await admin.aclose()


async def test_new_event_confirmation_and_admin_authorization(app):
    admin = await admin_client(app)
    team, _ = await team_client(app, admin)
    assert (await team.post('/api/admin/events', json=next_event())).status_code == 403
    assert (await admin.post('/api/admin/events', json={**next_event(),'confirmation':'yes'})).status_code == 422
    responses = await asyncio.gather(*[admin.post('/api/admin/events', json=next_event()) for _ in range(2)])
    assert sorted(r.status_code for r in responses) == [201,409]
    assert len((await admin.get('/api/admin/events')).json()) == 1
    await team.aclose(); await admin.aclose()


async def test_openai_and_gemini_send_real_image_content_without_network():
    image = ReferenceImage(b'test-image-bytes')
    provider = object.__new__(OpenAIProvider)
    provider.model = 'configured-model'
    parsed = Mock(output_parsed=None, usage=Mock(input_tokens=123,output_tokens=456), id='mock-result')
    parse = AsyncMock(return_value=parsed)
    provider.client = Mock(responses=Mock(parse=parse))
    await provider.generate('game prompt', 1000, images=[image])
    kwargs = parse.call_args.kwargs
    content = kwargs['input'][0]['content']
    assert content[1]['type'] == 'input_image' and content[1]['detail'] == 'low'
    assert base64.b64decode(content[1]['image_url'].split(',')[1]) == image.data
    gemini = object.__new__(GeminiProvider)
    gemini.model = 'configured-fallback-model'
    call = AsyncMock(return_value=Mock(usage_metadata=None,text='',response_id='mock-fallback'))
    gemini.client = Mock(models=Mock(generate_content=call))
    await gemini.generate('game prompt', 1000, images=[image])
    part = call.call_args.kwargs['contents'][1]
    assert part.inline_data.data == image.data and part.inline_data.mime_type == 'image/jpeg'


async def test_fallback_receives_same_references_and_image_usage_is_accounted(app):
    calls = []
    class Primary(MockProvider):
        model = 'primary-vision-test'
        input_price = output_price = 1.0
        async def generate(self, text, max_output, images=None):
            calls.append(('primary', images))
            raise ProviderError('rate_limit', 'Temporarily rate limited')
    class Fallback(MockProvider):
        model = 'fallback-vision-test'
        input_price = output_price = 1.0
        async def generate(self, text, max_output, images=None):
            calls.append(('fallback', images))
            output = await super().generate(text, max_output, images)
            return Result(output.game, 1234, 456, 'mock-vision-request')
    app.state.service.provider_factory = lambda _, name: Primary() if name == 'openai' else Fallback()
    admin = await admin_client(app)
    team, _ = await team_client(app, admin)
    await team.post('/api/references', json=image_payload())
    await admin.patch('/api/admin/event', json={'primary':'openai','fallback':'gemini'})
    await start(admin)
    result = await generate(app, team)
    assert result['status'] == 'success' and result['fallback']
    assert calls[0][1] == calls[1][1] and len(calls[0][1]) == 1
    ledger = (await admin.get('/api/admin/dashboard')).json()
    assert ledger['metrics']['spent_micro'] == 1690
    assert ledger['attempts'][0]['input_tokens'] == 1234
    await team.aclose(); await admin.aclose()


def test_nonvision_model_has_an_understandable_error():
    error = Mock(status_code=400, body={'message':'Image inputs are not supported by this model.'}, request_id='mock-only')
    assert 'vision-capable model' in str(classify(error))


def test_v1_migration_preserves_ids_foreign_keys_and_allows_same_team_name(settings, tmp_path):
    path = tmp_path / 'legacy.db'
    with sqlite3.connect(path) as db:
        db.executescript('''CREATE TABLE schema_version(id INTEGER PRIMARY KEY,version INTEGER NOT NULL);
            INSERT INTO schema_version VALUES(1,1);
            CREATE TABLE teams(id INTEGER PRIMARY KEY,name VARCHAR(80) NOT NULL UNIQUE,code_hash VARCHAR(128) NOT NULL UNIQUE,
                allowance INTEGER NOT NULL,emergency INTEGER NOT NULL,used INTEGER NOT NULL,active_request VARCHAR,
                current_version INTEGER,last_seen INTEGER NOT NULL,created INTEGER NOT NULL);
            INSERT INTO teams VALUES(42,'Preserved team','old-code-hash',12,3,1,NULL,50,0,123);
            CREATE TABLE generations(id VARCHAR(40) PRIMARY KEY,team_id INTEGER REFERENCES teams(id),
                idempotency_key VARCHAR(80),payload_hash VARCHAR(64),prompt TEXT,status VARCHAR,reserved_micro INTEGER,
                cost_micro INTEGER,version_id INTEGER,error TEXT,fallback INTEGER,created INTEGER,duration_ms INTEGER);
            CREATE TABLE versions(id INTEGER PRIMARY KEY,team_id INTEGER NOT NULL REFERENCES teams(id),number INTEGER,
                title VARCHAR(100),prompt TEXT,explanation TEXT,html TEXT,source VARCHAR(20),created INTEGER);
            INSERT INTO versions VALUES(50,42,1,'Saved game','Old prompt','Saved explanation','<!doctype html>saved','ai',123);
        ''')
    settings.database_url = 'sqlite:///' + path.as_posix()
    database = Database(settings.database_url)
    database.initialize(settings)
    database.initialize(settings)  # migration is repeatable
    with database.read() as db:
        assert db.get(Meta,1).version == 2
        assert db.get(Version,50).team_id == 42 and db.get(Version,50).html == '<!doctype html>saved'
        assert db.get(Team,42).event_key == 'legacy'
    with database.write() as db:
        db.add(Team(name='Preserved team',event_key='another-event',code_hash='different-code-hash'))
    with database.engine.connect() as conn:
        assert conn.exec_driver_sql('PRAGMA foreign_key_check').all() == []
    database.engine.dispose()
