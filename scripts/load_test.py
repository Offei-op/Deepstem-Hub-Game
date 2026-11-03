"""Opt-in HTTP rehearsal against a running studio in MOCK MODE; creates 10 persistent teams.
Usage: python scripts/load_test.py --base-url http://localhost:8080
Password is read interactively (or from LOAD_TEST_ADMIN_PASSWORD); never put it in shell history.
"""
import argparse
import asyncio
import getpass
import os
import time
import uuid
import httpx


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',default='http://localhost:8080')
    parser.add_argument('--origin',help='Application origin for direct-API rehearsal; defaults to base URL')
    parser.add_argument('--allow-paid',action='store_true',help='Explicitly permit spending: up to 10 game generations')
    args=parser.parse_args()
    password=os.getenv('LOAD_TEST_ADMIN_PASSWORD') or getpass.getpass('Organizer password: ')
    clients=[]
    origin=args.origin or args.base_url
    async with httpx.AsyncClient(base_url=args.base_url,headers={'Origin':origin},timeout=30) as admin:
        r=await admin.post('/api/auth/admin',json={'password':password});r.raise_for_status()
        admin.headers['X-CSRF-Token']=r.json()['csrf']
        d=(await admin.get('/api/admin/dashboard')).json()
        if d['event']['primary']!='mock' and not args.allow_paid:
            raise SystemExit('Refusing to spend credits. Select mock provider or explicitly use --allow-paid.')
        if d['teams']:
            raise SystemExit('Use a fresh rehearsal database. This script creates exactly 10 teams.')
        for i in range(10):
            r=await admin.post('/api/admin/teams',json={'name':f'Rehearsal {i+1:02}'});r.raise_for_status()
            c=httpx.AsyncClient(base_url=args.base_url,headers={'Origin':origin},timeout=30)
            auth=await c.post('/api/auth/team',json={'code':r.json()['code']});auth.raise_for_status()
            c.headers['X-CSRF-Token']=auth.json()['csrf'];clients.append(c)
        (await admin.post('/api/admin/timer',json={'action':'start'})).raise_for_status()
        async def run(index,c):
            begin=time.monotonic()
            r=await c.post('/api/generations',json={'prompt':'Create a simple arcade game with arrow keys and stars.',
                                                   'key':uuid.uuid4().hex});r.raise_for_status()
            request_id=r.json()['id']
            for _ in range(360):
                state=await c.get('/api/generations/'+request_id);state.raise_for_status()
                if state.json()['status']!='running':
                    assert state.json()['status']=='success', state.text
                    w=(await c.get('/api/workspace')).json()
                    assert w['team']['used']==1 and len(w['versions'])==1
                    print(f'Team {index+1:02}: saved, {time.monotonic()-begin:.2f}s')
                    return
                await asyncio.sleep(1)
            raise AssertionError('Generation did not settle within 6 minutes')
        try:
            await asyncio.gather(*(run(i,c) for i,c in enumerate(clients)))
            d=(await admin.get('/api/admin/dashboard')).json()
            assert d['metrics']['success']==10 and d['metrics']['reserved_micro']==0
            print('PASS: 10 concurrent teams, 10 saved games, one request used per team, no leaked reservations.')
        finally:
            await asyncio.gather(*(c.aclose() for c in clients))


if __name__=='__main__':asyncio.run(main())
