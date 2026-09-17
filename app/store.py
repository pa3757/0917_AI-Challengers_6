"""Anonymous browser state persisted in SQLite; no global mutable user session."""
import json
import os
import secrets
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def connect():
    path = Path(os.getenv('ENERGY_DB_PATH', str(ROOT / 'runtime/energy-coach.sqlite3')))
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.execute('CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, data TEXT NOT NULL)')
    return conn


def session_id(candidate):
    if candidate and len(candidate) == 64:
        with connect() as conn:
            if conn.execute('SELECT 1 FROM sessions WHERE id=?', (candidate,)).fetchone():
                return candidate
    key = secrets.token_hex(32)
    with connect() as conn:
        conn.execute('INSERT INTO sessions VALUES (?, ?)', (key, '{}'))
    return key


def read(key):
    with connect() as conn:
        row = conn.execute('SELECT data FROM sessions WHERE id=?', (key,)).fetchone()
    return json.loads(row[0]) if row else {}


def update(key, patch):
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT data FROM sessions WHERE id=?', (key,)).fetchone()
        data = json.loads(row[0]) if row else {}
        data.update(patch)
        conn.execute('UPDATE sessions SET data=? WHERE id=?', (json.dumps(data, ensure_ascii=False), key))
    return data


def set_mission(key, solution_id, completed):
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT data FROM sessions WHERE id=?', (key,)).fetchone()
        data = json.loads(row[0]) if row else {}
        recommendations = data.get('report', {}).get('ranking', {}).get('top_recommendations', [])
        if solution_id not in {s['solution_id'] for s in recommendations}:
            return None
        data.setdefault('missions', {})[solution_id] = completed
        conn.execute('UPDATE sessions SET data=? WHERE id=?', (json.dumps(data, ensure_ascii=False), key))
    return data
