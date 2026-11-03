"""Read-only event archives; historical team/version IDs are never recycled."""
import base64
import json
import time
import uuid
from typing import Literal
from fastapi import Request, Response, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func, delete
from .db import Team, Generation, Attempt, Submission, Version, EventArchive, LoginSession, Audit, StyleReference
from .service import event_config, save_event, active_key, totals, remaining, team_dict, request_dict


class NewEvent(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    expected_event_key: str = Field(min_length=1, max_length=40)
    confirmation: Literal['NEW EVENT']
    name: str = Field(min_length=2, max_length=120)
    theme: str = Field(min_length=1, max_length=120)
    minutes: int = Field(default=120, ge=1, le=480)
    budget_micro: int = Field(default=20_000_000, ge=0, le=1_000_000_000)
    initial_allowance: int = Field(default=12, ge=1, le=100)
    emergency_allowance: int = Field(default=3, ge=0, le=100)
    max_teams: int = Field(default=10, ge=1, le=10)


def dashboard_data(db, config=None):
    config = config or event_config(db)
    key = config.get('event_key', 'legacy')
    team_ids = select(Team.id).where(Team.event_key == key)
    teams = list(db.scalars(select(Team).where(Team.event_key == key).order_by(Team.id)))
    requests = list(db.scalars(select(Generation).where(Generation.team_id.in_(team_ids)).order_by(Generation.created.desc()).limit(300)))
    spent, held = totals(db, key)
    statuses = dict(db.execute(select(Generation.status, func.count()).where(
        Generation.team_id.in_(team_ids)).group_by(Generation.status)).all())
    submissions = [{k: getattr(s, k) for k in ['team_id', 'team_name', 'version_id', 'title', 'description', 'created']}
                   for s in db.scalars(select(Submission).where(Submission.team_id.in_(team_ids)))]
    attempts = [{k: getattr(a, k) for k in ['id', 'request_id', 'team_id', 'provider', 'model', 'status',
        'input_tokens', 'output_tokens', 'cost_micro', 'uncertain', 'duration_ms', 'fallback',
        'provider_request_id', 'error', 'created']}
        for a in db.scalars(select(Attempt).where(Attempt.team_id.in_(team_ids)).order_by(Attempt.id.desc()).limit(500))]
    archived = key != active_key(db)
    return {'event': config, 'archived': archived, 'server_time': int(time.time()),
        'remaining_seconds': remaining(config), 'teams': [team_dict(t) for t in teams],
        'requests': [request_dict(r) for r in requests], 'attempts': attempts, 'submissions': submissions,
        'metrics': {'teams': len(teams), 'active': 0 if archived else sum(t.last_seen > time.time() - 300 for t in teams),
            'requests': sum(statuses.values()), 'success': statuses.get('success', 0),
            'failed': statuses.get('failed', 0), 'running': statuses.get('running', 0),
            'spent_micro': spent, 'reserved_micro': held, 'remaining_micro': max(0, config['budget_micro'] - spent - held)}}


def export_event(db, config):
    ids = select(Team.id).where(Team.event_key == config.get('event_key', 'legacy'))
    def rows(cls, excluded=()):
        return [{col.name: getattr(row, col.name) for col in cls.__table__.columns if col.name not in excluded}
                for row in db.scalars(select(cls).where(cls.team_id.in_(ids)))]
    teams = [{col.name: getattr(t, col.name) for col in Team.__table__.columns if col.name != 'code_hash'}
             for t in db.scalars(select(Team).where(Team.id.in_(ids)))]
    references = rows(StyleReference, ('data',))
    image_rows = {r.id: r for r in db.scalars(select(StyleReference).where(StyleReference.team_id.in_(ids)))}
    for reference in references:
        reference['mime_type'] = 'image/jpeg'
        reference['base64'] = base64.b64encode(image_rows[reference['id']].data).decode('ascii')
    return {'exported_at': int(time.time()), 'event': config, 'teams': teams,
            'versions': rows(Version), 'submissions': rows(Submission),
            'requests': rows(Generation, ('payload_hash', 'idempotency_key')), 'attempts': rows(Attempt),
            'references': references}


def install_event_routes(app, database, auth):
    @app.get('/api/admin/events')
    def events(request: Request):
        auth(request, 'admin')
        with database.read() as db:
            return [{'id': row.id, 'name': row.name, 'theme': json.loads(row.config)['theme'], 'created': row.created,
                     'teams': db.scalar(select(func.count()).select_from(Team).where(Team.event_key == row.event_key))}
                    for row in db.scalars(select(EventArchive).order_by(EventArchive.created.desc(), EventArchive.id.desc()))]

    @app.post('/api/admin/events', status_code=201)
    def new_event(body: NewEvent, request: Request):
        auth(request, 'admin')
        with database.write() as db:
            config = event_config(db)
            if body.expected_event_key != config.get('event_key', 'legacy'):
                raise HTTPException(409, 'The active event changed. Refresh before creating another event.')
            if db.scalar(select(func.count()).select_from(Generation).where(Generation.status == 'running')):
                raise HTTPException(409, 'Wait for all active generations to finish before starting a new event.')
            if db.scalar(select(func.count()).select_from(Team).where(Team.active_request.is_not(None))):
                raise HTTPException(409, 'A team still has an active request. Finish or recover it before creating an event.')
            now = int(time.time())
            snapshot = dict(config, phase='ended', frozen=True, paused=True, ends_at=None,
                            remaining_seconds=0, archived_at=now)
            archived = EventArchive(event_key=config.get('event_key', 'legacy'),
                                    name=config.get('name', 'Game Jam'), config=json.dumps(snapshot), created=now)
            db.add(archived)
            # Keeping historical rows also preserves old preview capabilities and version IDs.
            config.update(name=body.name, event_key=uuid.uuid4().hex, theme=body.theme,
                          announcement='', phase='ready', remaining_seconds=body.minutes * 60, ends_at=None,
                          paused=False, emergency_mode=False, frozen=False, created_at=now,
                          budget_micro=body.budget_micro, initial_allowance=body.initial_allowance,
                          emergency_allowance=body.emergency_allowance, max_teams=body.max_teams)
            config.pop('archived_at', None)
            save_event(db, config)
            db.execute(delete(LoginSession).where(LoginSession.role == 'team'))
            db.flush()
            db.add(Audit(action=f'Archived event {archived.id}; created event {config["event_key"]}'))
            return {'event': config, 'archived_event_id': archived.id}

    @app.get('/api/admin/events/{archive_id}')
    def archived_event(archive_id: int, request: Request):
        auth(request, 'admin')
        with database.read() as db:
            archived = db.get(EventArchive, archive_id)
            if not archived:
                raise HTTPException(404, 'Archived event not found.')
            return dashboard_data(db, json.loads(archived.config))

    @app.get('/api/admin/events/{archive_id}/export')
    def archived_export(archive_id: int, request: Request):
        auth(request, 'admin')
        with database.read() as db:
            archived = db.get(EventArchive, archive_id)
            if not archived:
                raise HTTPException(404, 'Archived event not found.')
            return Response(json.dumps(export_event(db, json.loads(archived.config)), indent=2), media_type='application/json',
                headers={'Content-Disposition': f'attachment; filename="deepstem-archived-event-{archive_id}.json"'})
