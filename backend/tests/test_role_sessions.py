from conftest import admin_client, team_client


async def test_organizer_and_contestant_can_share_a_browser_without_replacing_sessions(app):
    browser=await admin_client(app)
    admin_csrf=browser.headers['X-CSRF-Token']
    created=await browser.post('/api/admin/teams',json={'name':'Contestant Preview'})
    code=created.json()['code']
    response=await browser.post('/api/auth/team',json={'code':code})
    team_csrf=response.json()['csrf']
    assert 'deepstem_admin_session' in browser.cookies and 'deepstem_team_session' in browser.cookies
    browser.headers['X-Studio-Role']='team'
    assert (await browser.get('/api/auth/session')).json()['role']=='team'
    assert (await browser.get('/api/workspace')).json()['team']['name']=='Contestant Preview'
    browser.headers['X-Studio-Role']='admin'
    assert (await browser.get('/api/auth/session')).json()['role']=='admin'
    assert (await browser.get('/api/admin/dashboard')).status_code==200
    # Logging out of the contestant view keeps the organizer signed in.
    browser.headers.update({'X-Studio-Role':'team','X-CSRF-Token':team_csrf})
    assert (await browser.post('/api/auth/logout',json={})).status_code==200
    browser.headers.update({'X-Studio-Role':'admin','X-CSRF-Token':admin_csrf})
    assert (await browser.get('/api/auth/session')).json()['role']=='admin'
    browser.headers['X-Studio-Role']='team'
    assert (await browser.get('/api/auth/session')).status_code==401


async def test_changing_role_header_cannot_grant_admin_access(app):
    admin=await admin_client(app)
    team,_=await team_client(app,admin)
    team.headers['X-Studio-Role']='admin'
    assert (await team.get('/api/auth/session')).status_code==401
    assert (await team.get('/api/admin/dashboard')).status_code==403


async def test_logout_revokes_same_role_legacy_cookie_too(app):
    import time
    from app.db import LoginSession
    from app.security import COOKIE, digest
    browser=await admin_client(app)
    with app.state.database.write() as db:
        db.add(LoginSession(token_hash=digest('old-legacy-admin-token'),role='admin',csrf='old-csrf',expires=int(time.time())+60))
    browser.cookies.set(COOKIE,'old-legacy-admin-token')
    browser.headers['X-Studio-Role']='admin'
    assert (await browser.post('/api/auth/logout',json={})).status_code==200
    assert (await browser.get('/api/auth/session')).status_code==401
