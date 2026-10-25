"""Persistent SQLite/PostgreSQL connections and additive legacy migrations."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Connection:
    """Keep parameter binding identical for local SQLite and hosted PostgreSQL."""
    def __init__(self, raw, postgres=False):
        self.raw = raw
        self.postgres = postgres

    def execute(self, sql, params=()):
        if self.postgres:
            if sql == 'BEGIN IMMEDIATE':
                return self.raw.execute('SELECT pg_advisory_xact_lock(694234)')
            sql = sql.replace('%', '%%').replace('?', '%s').replace('instr(', 'strpos(')
        return self.raw.execute(sql, params)

    def executemany(self, sql, rows):
        if self.postgres:
            with self.raw.cursor() as cursor:
                cursor.executemany(sql.replace('%', '%%').replace('?', '%s'), rows)
        else:
            return self.raw.executemany(sql, rows)


class Database:
    def __init__(self, path):
        self.path = str(path)
        self.postgres = self.path.startswith(('postgres://', 'postgresql://'))
        self._migrate()

    @contextmanager
    def connect(self):
        if self.postgres:
            import psycopg
            from psycopg.rows import dict_row
            connection = psycopg.connect(self.path, row_factory=dict_row, connect_timeout=10)
        else:
            connection = sqlite3.connect(self.path, timeout=30)
            connection.row_factory = sqlite3.Row
            connection.execute('PRAGMA foreign_keys=ON')
        try:
            with connection:
                yield Connection(connection, self.postgres)
        finally:
            connection.close()

    def _columns(self, db, table):
        if self.postgres:
            return {r['column_name'] for r in db.execute(
                'SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=?', (table,))}
        return {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}

    def _migrate(self):
        key = 'BIGSERIAL PRIMARY KEY' if self.postgres else 'INTEGER PRIMARY KEY AUTOINCREMENT'
        now = utc_now()
        with self.connect() as db:
            if self.postgres:
                db.execute('SELECT pg_advisory_xact_lock(694233)')
            else:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('BEGIN IMMEDIATE')
            db.execute(f'''CREATE TABLE IF NOT EXISTS workspaces (
                id {key}, name TEXT NOT NULL, created_at TEXT NOT NULL,
                demo_seeded INTEGER NOT NULL DEFAULT 0)''')
            if not db.execute('SELECT id FROM workspaces WHERE id=1').fetchone():
                db.execute('INSERT INTO workspaces(id,name,created_at) VALUES (1,?,?)', ('My dealership', now))
                if self.postgres:
                    db.execute("SELECT setval(pg_get_serial_sequence('workspaces','id'), (SELECT MAX(id) FROM workspaces))")
            db.execute(f'''CREATE TABLE IF NOT EXISTS users (
                id {key}, email TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','admin')),
                workspace_id BIGINT NOT NULL DEFAULT 1 REFERENCES workspaces(id))''')
            user_columns = self._columns(db, 'users')
            if 'workspace_id' not in user_columns:
                db.execute('ALTER TABLE users ADD COLUMN workspace_id BIGINT NOT NULL DEFAULT 1')
                # Preserve the original collection for the original owner. Other legacy
                # accounts become private owners instead of retaining shared access.
                users = db.execute("SELECT id, role FROM users ORDER BY CASE WHEN role='admin' THEN 0 ELSE 1 END,id").fetchall()
                for index, user in enumerate(users):
                    workspace = 1
                    if index:
                        workspace = db.execute('INSERT INTO workspaces(name,created_at) VALUES (?,?) RETURNING id', ('My dealership', now)).fetchone()['id']
                    db.execute("UPDATE users SET workspace_id=?, role='admin' WHERE id=?", (workspace, user['id']))
            db.execute(f'''CREATE TABLE IF NOT EXISTS vehicles (
                id {key}, make TEXT NOT NULL, model TEXT NOT NULL, category TEXT NOT NULL,
                price_cents BIGINT NOT NULL CHECK(price_cents>=0),
                quantity INTEGER NOT NULL CHECK(quantity>=0), deleted_at TEXT,
                workspace_id BIGINT NOT NULL DEFAULT 1 REFERENCES workspaces(id))''')
            columns = self._columns(db, 'vehicles')
            additions = {
                'deleted_at': 'TEXT', 'workspace_id': 'BIGINT NOT NULL DEFAULT 1',
                'condition': "TEXT NOT NULL DEFAULT 'new'", 'year': 'INTEGER NOT NULL DEFAULT 2025',
                'trim': "TEXT NOT NULL DEFAULT ''", 'mileage_km': 'INTEGER NOT NULL DEFAULT 0',
                'fuel_type': "TEXT NOT NULL DEFAULT 'Petrol'", 'transmission': "TEXT NOT NULL DEFAULT 'Manual'",
                'color': "TEXT NOT NULL DEFAULT 'White'", 'city': "TEXT NOT NULL DEFAULT 'Bengaluru'",
                'description': "TEXT NOT NULL DEFAULT ''", 'info_url': "TEXT NOT NULL DEFAULT ''",
                'images_json': "TEXT NOT NULL DEFAULT '[]'", 'stock_number': "TEXT NOT NULL DEFAULT ''",
                'vin': "TEXT NOT NULL DEFAULT ''", 'created_at': "TEXT NOT NULL DEFAULT ''",
                'updated_at': "TEXT NOT NULL DEFAULT ''",
            }
            for column, definition in additions.items():
                if column not in columns:
                    db.execute(f'ALTER TABLE vehicles ADD COLUMN {column} {definition}')
            db.execute("UPDATE vehicles SET created_at=? WHERE created_at=''", (now,))
            db.execute("UPDATE vehicles SET updated_at=? WHERE updated_at=''", (now,))
            db.execute(f'''CREATE TABLE IF NOT EXISTS purchases (
                id {key}, workspace_id BIGINT NOT NULL REFERENCES workspaces(id),
                vehicle_id BIGINT REFERENCES vehicles(id), make TEXT NOT NULL, model TEXT NOT NULL,
                condition TEXT NOT NULL, fuel_type TEXT NOT NULL, quantity INTEGER NOT NULL,
                unit_price_cents BIGINT NOT NULL, total_cents BIGINT NOT NULL,
                purchased_at TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0)''')
            db.execute(f'''CREATE TABLE IF NOT EXISTS inventory_events (
                id {key}, workspace_id BIGINT NOT NULL REFERENCES workspaces(id),
                vehicle_id BIGINT REFERENCES vehicles(id), event_type TEXT NOT NULL,
                quantity_delta INTEGER NOT NULL, created_at TEXT NOT NULL,
                is_demo INTEGER NOT NULL DEFAULT 0)''')
            for name, table, fields in [
                ('idx_vehicles_workspace', 'vehicles', 'workspace_id,deleted_at,id'),
                ('idx_vehicles_filters', 'vehicles', 'workspace_id,condition,price_cents'),
                ('idx_purchases_workspace_date', 'purchases', 'workspace_id,purchased_at'),
                ('idx_events_workspace', 'inventory_events', 'workspace_id,created_at'),
                ('idx_users_workspace', 'users', 'workspace_id'),
            ]:
                db.execute(f'CREATE INDEX IF NOT EXISTS {name} ON {table} ({fields})')


def public_user(row):
    return {key: row[key] for key in ('id', 'email', 'role', 'workspace_id')}


def public_vehicle(row):
    result = dict(row)
    result['price'] = format(Decimal(result.pop('price_cents')) / 100, '.2f')
    result['images'] = json.loads(result.pop('images_json'))
    result['currency'] = 'INR'
    return result
