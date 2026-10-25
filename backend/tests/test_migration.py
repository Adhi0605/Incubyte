import sqlite3
from contextlib import closing
from app.database import Database


def test_legacy_database_migrates_without_losing_inventory(tmp_path):
    path = str(tmp_path / 'legacy.db')
    with closing(sqlite3.connect(path)) as db:
        with db:
            db.execute('CREATE TABLE vehicles (id INTEGER PRIMARY KEY, make TEXT, model TEXT, category TEXT, price_cents INTEGER, quantity INTEGER)')
            db.execute("INSERT INTO vehicles VALUES (42, 'Toyota', 'Camry', 'Sedan', 3200050, 3)")
    for _ in range(2):
        with Database(path).connect() as db:
            row = db.execute('SELECT * FROM vehicles WHERE id=42').fetchone()
            assert row['deleted_at'] is None
            assert row['quantity'] == 3
            assert row['price_cents'] == 3200050


def test_legacy_users_get_independent_owner_workspaces_without_moving_original_stock(tmp_path):
    path = str(tmp_path / 'users.db')
    with closing(sqlite3.connect(path)) as db:
        with db:
            db.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, email TEXT UNIQUE, password_hash TEXT, role TEXT)")
            db.execute("INSERT INTO users VALUES (1,'owner@example.com','existing-hash','admin')")
            db.execute("INSERT INTO users VALUES (2,'member@example.com','existing-hash','user')")
            db.execute('CREATE TABLE vehicles (id INTEGER PRIMARY KEY, make TEXT, model TEXT, category TEXT, price_cents INTEGER, quantity INTEGER)')
            db.execute("INSERT INTO vehicles VALUES (42,'Honda','City','Sedan',80000000,1)")
    for _ in range(2):
        with Database(path).connect() as db:
            users = db.execute('SELECT * FROM users ORDER BY id').fetchall()
            assert [u['role'] for u in users] == ['admin', 'admin']
            assert users[0]['workspace_id'] != users[1]['workspace_id']
            assert db.execute('SELECT workspace_id FROM vehicles WHERE id=42').fetchone()['workspace_id'] == users[0]['workspace_id']
            assert users[1]['password_hash'] == 'existing-hash'
            assert db.execute('SELECT COUNT(*) FROM workspaces').fetchone()[0] == 2
