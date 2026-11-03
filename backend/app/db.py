import time
from pathlib import Path
from contextlib import contextmanager
from sqlalchemy import create_engine, event, Integer, String, Text, LargeBinary, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Meta(Base):
    __tablename__ = 'schema_version'
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    version: Mapped[int] = mapped_column(default=1)


class Event(Base):
    __tablename__ = 'event'
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    config: Mapped[str] = mapped_column(Text)


class Team(Base):
    __tablename__ = 'teams'
    __table_args__ = (UniqueConstraint('event_key', 'name'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    event_key: Mapped[str] = mapped_column(String(40), default='legacy', index=True)
    code_hash: Mapped[str] = mapped_column(String(128), unique=True)
    allowance: Mapped[int] = mapped_column(default=12)
    emergency: Mapped[int] = mapped_column(default=3)
    used: Mapped[int] = mapped_column(default=0)
    active_request: Mapped[str | None] = mapped_column(nullable=True)
    current_version: Mapped[int | None] = mapped_column(nullable=True)
    last_seen: Mapped[int] = mapped_column(default=0)
    created: Mapped[int] = mapped_column(default=lambda: int(time.time()))


class LoginSession(Base):
    __tablename__ = 'sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    role: Mapped[str] = mapped_column(String(10))
    team_id: Mapped[int | None] = mapped_column(ForeignKey('teams.id'), nullable=True)
    csrf: Mapped[str] = mapped_column(String(80))
    expires: Mapped[int] = mapped_column(Integer)


class Version(Base):
    __tablename__ = 'versions'
    __table_args__ = (UniqueConstraint('team_id', 'number'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey('teams.id'), index=True)
    number: Mapped[int]
    title: Mapped[str] = mapped_column(String(100))
    prompt: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    html: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default='ai')
    created: Mapped[int] = mapped_column(default=lambda: int(time.time()))


class Generation(Base):
    __tablename__ = 'generations'
    __table_args__ = (UniqueConstraint('team_id', 'idempotency_key'),)
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey('teams.id'), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    payload_hash: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(Text)
    reference_ids: Mapped[str] = mapped_column(Text, default='[]')
    status: Mapped[str] = mapped_column(default='running')
    reserved_micro: Mapped[int] = mapped_column(default=0)
    cost_micro: Mapped[int] = mapped_column(default=0)
    version_id: Mapped[int | None] = mapped_column(nullable=True)
    error: Mapped[str] = mapped_column(Text, default='')
    fallback: Mapped[int] = mapped_column(default=0)
    created: Mapped[int] = mapped_column(default=lambda: int(time.time()))
    duration_ms: Mapped[int] = mapped_column(default=0)


class Attempt(Base):
    __tablename__ = 'attempts'
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey('generations.id'), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey('teams.id'))
    provider: Mapped[str] = mapped_column(String(20))
    model: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30))
    input_tokens: Mapped[int | None] = mapped_column(nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(nullable=True)
    cost_micro: Mapped[int] = mapped_column(default=0)
    uncertain: Mapped[int] = mapped_column(default=0)
    provider_request_id: Mapped[str] = mapped_column(String(180), default='')
    error: Mapped[str] = mapped_column(Text, default='')
    created: Mapped[int] = mapped_column(default=lambda: int(time.time()))
    duration_ms: Mapped[int] = mapped_column(default=0)
    fallback: Mapped[int] = mapped_column(default=0)


class Submission(Base):
    __tablename__ = 'submissions'
    team_id: Mapped[int] = mapped_column(ForeignKey('teams.id'), primary_key=True)
    team_name: Mapped[str] = mapped_column(String(80))
    version_id: Mapped[int] = mapped_column(ForeignKey('versions.id'))
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text)
    prompt_history: Mapped[str] = mapped_column(Text)
    created: Mapped[int] = mapped_column(default=lambda: int(time.time()))


class RateBucket(Base):
    __tablename__ = 'rate_buckets'
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    window: Mapped[int]
    count: Mapped[int]


class Audit(Base):
    __tablename__ = 'audit'
    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(Text)
    created: Mapped[int] = mapped_column(default=lambda: int(time.time()))


class EventArchive(Base):
    __tablename__ = 'event_archives'
    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    config: Mapped[str] = mapped_column(Text)
    created: Mapped[int] = mapped_column(default=lambda: int(time.time()))


class StyleReference(Base):
    __tablename__ = 'style_references'
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    team_id: Mapped[int] = mapped_column(ForeignKey('teams.id'), index=True)
    name: Mapped[str] = mapped_column(String(100))
    data: Mapped[bytes] = mapped_column(LargeBinary)
    width: Mapped[int]
    height: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    removed: Mapped[int] = mapped_column(default=0)
    created: Mapped[int] = mapped_column(default=lambda: int(time.time()))


DEFAULT_EVENT = dict(name='Game Jam', event_key='legacy', theme='Unexpected Heroes', announcement='', paused=False, emergency_mode=False,
                     frozen=False, phase='ready', remaining_seconds=7200, ends_at=None,
                     max_teams=10, initial_allowance=12, emergency_allowance=3,
                     budget_micro=20_000_000, max_concurrent=10, max_input_tokens=55_000,
                     max_output_tokens=12_000, primary='mock', fallback='')


class Database:
    def __init__(self, url):
        if url.startswith('sqlite:///') and ':memory:' not in url:
            Path(url.removeprefix('sqlite:///')).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 30})

        @event.listens_for(self.engine, 'connect')
        def pragmas(conn, _):
            conn.execute('PRAGMA foreign_keys=ON')
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA busy_timeout=30000')
        self.session = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self, settings):
        Base.metadata.create_all(self.engine)
        self.migrate()
        with self.write() as db:
            meta = db.get(Meta, 1)
            if meta and meta.version != 2:
                raise RuntimeError('Unsupported database schema. Restore matching application or migrate.')
            if not meta:
                db.add(Meta(id=1, version=2))
            if not db.get(Event, 1):
                import json
                config = dict(DEFAULT_EVENT, primary=settings.primary_ai_provider, fallback=settings.fallback_ai_provider)
                db.add(Event(id=1, config=json.dumps(config)))

    def migrate(self):
        """Atomic SQLite v1→v2 migration; IDs and all historical games stay intact.

        Run with application services stopped and a SQLite backup already made.
        Rebuilding teams removes its global name constraint in favour of event scope.
        """
        connection = self.engine.raw_connection()
        try:
            cursor = connection.cursor()
            version = cursor.execute('SELECT version FROM schema_version WHERE id=1').fetchone()
            if not version or version[0] == 2:
                return
            if version[0] != 1:
                raise RuntimeError('Unsupported database schema.')
            cursor.execute('PRAGMA foreign_keys=OFF')
            cursor.execute('BEGIN IMMEDIATE')
            columns = {r[1] for r in cursor.execute('PRAGMA table_info(teams)')}
            if 'event_key' not in columns:
                cursor.execute('''CREATE TABLE teams_v2 (
                    id INTEGER PRIMARY KEY, name VARCHAR(80) NOT NULL,
                    event_key VARCHAR(40) NOT NULL DEFAULT 'legacy',
                    code_hash VARCHAR(128) NOT NULL UNIQUE, allowance INTEGER NOT NULL,
                    emergency INTEGER NOT NULL, used INTEGER NOT NULL, active_request VARCHAR,
                    current_version INTEGER, last_seen INTEGER NOT NULL, created INTEGER NOT NULL,
                    UNIQUE(event_key, name))''')
                old = 'id,name,code_hash,allowance,emergency,used,active_request,current_version,last_seen,created'
                cursor.execute(f'INSERT INTO teams_v2 ({old}) SELECT {old} FROM teams')
                cursor.execute('DROP TABLE teams')
                cursor.execute('ALTER TABLE teams_v2 RENAME TO teams')
                cursor.execute('CREATE INDEX ix_teams_event_key ON teams(event_key)')
            columns = {r[1] for r in cursor.execute('PRAGMA table_info(generations)')}
            if 'reference_ids' not in columns:
                cursor.execute("ALTER TABLE generations ADD COLUMN reference_ids TEXT NOT NULL DEFAULT '[]'")
            import json
            row = cursor.execute('SELECT config FROM event WHERE id=1').fetchone()
            if row:
                config = json.loads(row[0])
                config.setdefault('event_key', 'legacy')
                config.setdefault('name', 'Game Jam')
                cursor.execute('UPDATE event SET config=? WHERE id=1', (json.dumps(config),))
            if cursor.execute('PRAGMA foreign_key_check').fetchone():
                raise RuntimeError('Migration failed a foreign key check; changes were rolled back.')
            cursor.execute('UPDATE schema_version SET version=2 WHERE id=1')
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.close()

    @contextmanager
    def read(self):
        with self.session() as db:
            yield db

    @contextmanager
    def write(self):
        # Serializes checks + reservations across processes; never held during a network call.
        with self.session() as db:
            db.connection().exec_driver_sql('BEGIN IMMEDIATE')
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
