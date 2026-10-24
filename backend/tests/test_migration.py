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
