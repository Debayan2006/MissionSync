"""SQLite shared state. Events, audits and entities commit atomically."""
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

def now():
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

def uid(prefix):
    return f'{prefix}-{uuid4().hex[:12]}'

class Store:
    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.RLock()
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS entities(kind TEXT NOT NULL,id TEXT NOT NULL,scenario_id TEXT NOT NULL,data TEXT NOT NULL,PRIMARY KEY(kind,id));
            CREATE INDEX IF NOT EXISTS entity_scope ON entities(kind,scenario_id);
            CREATE TABLE IF NOT EXISTS metadata(key TEXT PRIMARY KEY,data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,type TEXT NOT NULL,data TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY,scenario_id TEXT,entity_id TEXT,data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS idempotency(key TEXT PRIMARY KEY,response TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,role TEXT NOT NULL,expires_at REAL NOT NULL);
            ''')

    @contextmanager
    def transaction(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=15)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA journal_mode=WAL')
            try:
                db.execute('BEGIN IMMEDIATE')
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise
            finally:
                db.close()

    def meta(self, db, key, default=None):
        row = db.execute('SELECT data FROM metadata WHERE key=?', (key,)).fetchone()
        return json.loads(row['data']) if row else default

    def set_meta(self, db, key, value):
        db.execute('INSERT OR REPLACE INTO metadata(key,data) VALUES(?,?)', (key, json.dumps(value)))

    def get(self, db, kind, entity_id):
        row = db.execute('SELECT data FROM entities WHERE kind=? AND id=?', (kind, entity_id)).fetchone()
        return json.loads(row['data']) if row else None

    def all(self, db, kind, scenario=None):
        rows = db.execute('SELECT data FROM entities WHERE kind=?' + (' AND scenario_id=?' if scenario else ''), (kind, scenario) if scenario else (kind,)).fetchall()
        return [json.loads(row['data']) for row in rows]

    def put(self, db, kind, item, scenario=None):
        db.execute('INSERT OR REPLACE INTO entities(kind,id,scenario_id,data) VALUES(?,?,?,?)', (kind, item['id'], scenario or item.get('scenario_id','global'), json.dumps(item)))

    def event(self, db, event_type, data):
        db.execute('INSERT INTO events(type,data,created_at) VALUES(?,?,?)', (event_type,json.dumps(data),now()))

    def audit(self, db, actor, action, kind, entity_id, before=None, after=None, reason=None, scenario=None):
        item = {'id':uid('audit'),'actor_id':actor,'action':action,'entity_type':kind,'entity_id':entity_id,'before_state':before,'after_state':after,'timestamp':now(),'reason':reason,'scenario_id':scenario}
        db.execute('INSERT INTO audit(id,scenario_id,entity_id,data) VALUES(?,?,?,?)', (item['id'],scenario,entity_id,json.dumps(item)))
        return item

    def audits(self, db, entity_id=None):
        rows = db.execute('SELECT data FROM audit' + (' WHERE entity_id=?' if entity_id else '') + ' ORDER BY rowid DESC', (entity_id,) if entity_id else ()).fetchall()
        return [json.loads(row['data']) for row in rows]

    def events_after(self, sequence, limit=200):
        with self.transaction() as db:
            rows = db.execute('SELECT id,type,data FROM events WHERE id>? ORDER BY id LIMIT ?', (sequence,limit)).fetchall()
            return [{'id':str(row['id']),'type':row['type'],'data':json.loads(row['data'])} for row in rows]
