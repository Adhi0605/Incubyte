"""Catalog and provisioning contracts, independent of API/schema migrations."""

from collections import Counter
from decimal import Decimal
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
from urllib.parse import urlparse

import pytest

from app.catalog import catalog_vehicles
from app.demo import populate_workspace
from app import demo
from app.database import Database


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def db(tmp_path):
    connection = sqlite3.connect(tmp_path / 'catalog.sqlite3')
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        PRAGMA foreign_keys = ON;
        CREATE TABLE workspaces (id INTEGER PRIMARY KEY, name TEXT, created_at TEXT);
        INSERT INTO workspaces VALUES (1, 'First', '2025-10-01T00:00:00Z');
        INSERT INTO workspaces VALUES (2, 'Second', '2025-10-01T00:00:00Z');
        CREATE TABLE vehicles (
            id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
            make TEXT NOT NULL, model TEXT NOT NULL, category TEXT NOT NULL,
            price_cents INTEGER NOT NULL CHECK(price_cents >= 0),
            quantity INTEGER NOT NULL CHECK(quantity >= 0), deleted_at TEXT,
            condition TEXT NOT NULL, year INTEGER NOT NULL, trim TEXT NOT NULL,
            mileage_km INTEGER NOT NULL, fuel_type TEXT NOT NULL,
            transmission TEXT NOT NULL, color TEXT NOT NULL, city TEXT NOT NULL,
            description TEXT NOT NULL, info_url TEXT NOT NULL, images_json TEXT NOT NULL,
            stock_number TEXT NOT NULL, vin TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            CHECK(condition != 'used' OR quantity <= 1),
            UNIQUE(workspace_id, stock_number)
        );
        CREATE TABLE purchases (
            id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
            vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
            make TEXT NOT NULL, model TEXT NOT NULL, condition TEXT NOT NULL,
            fuel_type TEXT NOT NULL, quantity INTEGER NOT NULL,
            unit_price_cents INTEGER NOT NULL, total_cents INTEGER NOT NULL,
            purchased_at TEXT NOT NULL, is_demo INTEGER NOT NULL
        );
        CREATE TABLE inventory_events (
            id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL REFERENCES workspaces(id),
            vehicle_id INTEGER NOT NULL REFERENCES vehicles(id),
            event_type TEXT NOT NULL, quantity_delta INTEGER NOT NULL,
            created_at TEXT NOT NULL, is_demo INTEGER NOT NULL
        );
    """)
    yield connection
    connection.close()


def test_catalog_is_deterministic_diverse_and_independently_mutable():
    first = catalog_vehicles()
    assert len(first) == 200
    assert first == catalog_vehicles()
    assert len({vehicle['stock_number'] for vehicle in first}) == 200
    assert Counter(vehicle['condition'] for vehicle in first) == {'new': 100, 'used': 100}
    assert len({vehicle['make'] for vehicle in first}) >= 10
    assert len({vehicle['city'] for vehicle in first}) >= 8
    assert len({vehicle['fuel_type'] for vehicle in first}) >= 4
    assert any(vehicle['quantity'] == 0 for vehicle in first)
    first[0]['images'][0]['alt'] = 'Changed'
    assert catalog_vehicles()[0]['images'][0]['alt'] != 'Changed'


def test_listings_have_rich_inr_fields_safe_links_and_licensed_local_photos():
    credits = (ROOT / 'ASSET_CREDITS.md').read_text()
    for vehicle in catalog_vehicles():
        assert 100_000 <= Decimal(vehicle['price']) <= 20_000_000
        assert Decimal(vehicle['price']) * 100 == int(Decimal(vehicle['price']) * 100)
        assert vehicle['condition'] in {'new', 'used'}
        assert vehicle['quantity'] >= 0
        assert 2015 <= vehicle['year'] <= 2026
        if vehicle['condition'] == 'used':
            assert vehicle['quantity'] <= 1
            assert vehicle['mileage_km'] > 0
        else:
            assert vehicle['mileage_km'] == 0
        for field in ('trim', 'transmission', 'color', 'city', 'description',
                      'stock_number', 'created_at', 'updated_at'):
            assert vehicle[field]
        assert 'synthetic' in vehicle['description'].lower()
        assert 'representative' in vehicle['description'].lower()
        assert urlparse(vehicle['info_url']).scheme == 'https'
        assert vehicle['created_at'].endswith('Z')
        assert vehicle['updated_at'] >= vehicle['created_at']
        assert vehicle['images']
        for image in vehicle['images']:
            assert set(image) == {'url', 'alt', 'credit', 'source_url', 'license'}
            assert image['url'].startswith('/cars/')
            asset = ROOT / 'frontend/public' / image['url'].lstrip('/')
            assert asset.is_file()
            assert asset.stat().st_size > 5000
            signature = asset.read_bytes()[:8]
            assert signature.startswith(b'\xff\xd8\xff') or signature == b'\x89PNG\r\n\x1a\n'
            assert 'representative' in image['alt'].lower()
            assert image['credit'] and image['license']
            assert urlparse(image['source_url']).scheme == 'https'
            assert image['source_url'] in credits
            assert asset.name in credits


def test_population_persists_all_fields_serializes_images_and_scopes_workspace(db):
    db.execute('BEGIN')
    populate_workspace(db, 1)
    assert db.in_transaction, 'Provisioning must leave commit to its caller'
    rows = db.execute('SELECT * FROM vehicles WHERE workspace_id = 1 ORDER BY id').fetchall()
    assert len(rows) == 200
    assert db.execute('SELECT COUNT(*) FROM vehicles WHERE workspace_id = 2').fetchone()[0] == 0
    for row, listing in zip(rows, catalog_vehicles()):
        assert row['price_cents'] == int(Decimal(listing['price']) * 100)
        assert json.loads(row['images_json']) == listing['images']
        for key in listing.keys() - {'price', 'images'}:
            assert row[key] == listing[key]
    db.rollback()
    for table in ('vehicles', 'purchases', 'inventory_events'):
        assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0


def test_twelve_months_of_consistent_synthetic_history_are_workspace_local(db):
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    populate_workspace(db, 1)
    purchases = db.execute('SELECT * FROM purchases ORDER BY purchased_at, id').fetchall()
    events = db.execute('SELECT * FROM inventory_events').fetchall()
    assert len({row['purchased_at'][:7] for row in purchases}) == 12
    assert max(row['purchased_at'][:10] for row in purchases) == yesterday.isoformat()
    assert all(row['purchased_at'][:10] <= yesterday.isoformat() for row in purchases)
    assert {row['condition'] for row in purchases} == {'new', 'used'}
    assert purchases and events
    for purchase in purchases:
        vehicle = db.execute('SELECT * FROM vehicles WHERE id = ?', (purchase['vehicle_id'],)).fetchone()
        assert purchase['workspace_id'] == vehicle['workspace_id'] == 1
        assert purchase['is_demo'] == 1
        assert purchase['quantity'] == 1
        assert purchase['unit_price_cents'] > 0
        assert purchase['total_cents'] == purchase['unit_price_cents'] * purchase['quantity']
        assert purchase['purchased_at'].endswith('Z')
        assert purchase['purchased_at'] >= vehicle['created_at']
        for key in ('make', 'model', 'condition', 'fuel_type'):
            assert purchase[key] == vehicle[key]
        if purchase['condition'] == 'used':
            assert vehicle['quantity'] == 0
    used_counts = Counter(row['vehicle_id'] for row in purchases if row['condition'] == 'used')
    assert max(used_counts.values()) == 1
    for event in events:
        assert event['workspace_id'] == 1
        assert event['is_demo'] == 1
        assert event['created_at'].endswith('Z')
    # Every stock movement, including opening stock and sales, reconciles.
    balances = Counter()
    for event in sorted(events, key=lambda row: (row['created_at'], row['id'])):
        balances[event['vehicle_id']] += event['quantity_delta']
        assert balances[event['vehicle_id']] >= 0
    for vehicle in db.execute('SELECT * FROM vehicles'):
        assert balances[vehicle['id']] == vehicle['quantity']
    populate_workspace(db, 2)
    assert db.execute('SELECT COUNT(*) FROM vehicles WHERE workspace_id = 2').fetchone()[0] == 200
    normalized = []
    for workspace_id in (1, 2):
        normalized.append([tuple(row) for row in db.execute('''
            SELECT v.stock_number, p.make, p.model, p.quantity, p.unit_price_cents,
                   p.total_cents, p.purchased_at, p.is_demo FROM purchases p
            JOIN vehicles v ON p.vehicle_id = v.id
            WHERE p.workspace_id = ? ORDER BY p.id
        ''', (workspace_id,))])
    assert normalized[0] == normalized[1]


def test_population_never_overwrites_existing_workspace_inventory(db):
    populate_workspace(db, 1)
    db.execute("UPDATE vehicles SET model = 'Owner edited car' WHERE id = 1")
    before = tuple(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                   for table in ('vehicles', 'purchases', 'inventory_events'))
    populate_workspace(db, 1)
    after = tuple(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
                  for table in ('vehicles', 'purchases', 'inventory_events'))
    assert after == before
    assert db.execute('SELECT model FROM vehicles WHERE id = 1').fetchone()[0] == 'Owner edited car'


def test_population_adds_catalog_alongside_existing_custom_vehicle(db):
    custom = {key: value for key, value in catalog_vehicles()[0].items()
              if key not in {'images', 'price'}}
    custom.update(workspace_id=1, model='Owner custom car', stock_number='CUSTOM-001',
                  price_cents=123456700, images_json='[]')
    db.execute(f"INSERT INTO vehicles ({', '.join(custom)}) VALUES ({', '.join('?' for _ in custom)})",
               tuple(custom.values()))
    before = dict(db.execute("SELECT * FROM vehicles WHERE stock_number = 'CUSTOM-001'").fetchone())
    assert populate_workspace(db, 1) == 200
    assert db.execute('SELECT COUNT(*) FROM vehicles WHERE workspace_id = 1').fetchone()[0] == 201
    assert dict(db.execute("SELECT * FROM vehicles WHERE stock_number = 'CUSTOM-001'").fetchone()) == before
    assert populate_workspace(db, 1) == 0
    assert db.execute('SELECT COUNT(*) FROM vehicles WHERE workspace_id = 1').fetchone()[0] == 201


def test_insert_failure_rolls_back_the_entire_callers_transaction(db):
    db.execute('''CREATE TRIGGER fail_demo_purchase BEFORE INSERT ON purchases
                  BEGIN SELECT RAISE(ABORT, 'simulated purchase failure'); END''')
    with pytest.raises(sqlite3.IntegrityError, match='simulated purchase failure'):
        with db:
            populate_workspace(db, 1)
    for table in ('vehicles', 'purchases', 'inventory_events'):
        assert db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0


def test_population_matches_real_migration_and_database_adapter(tmp_path):
    database = Database(tmp_path / 'real-schema.sqlite3')
    with database.connect() as connection:
        connection.execute('''
            INSERT INTO vehicles(workspace_id, make, model, category, price_cents, quantity)
            VALUES (1, 'Existing', 'Owner vehicle', 'Sedan', 10000000, 1)
        ''')
    with pytest.raises(RuntimeError, match='caller cancels'):
        with database.connect() as connection:
            assert populate_workspace(connection, 1) == 200
            assert connection.execute('SELECT COUNT(*) AS n FROM vehicles').fetchone()['n'] == 201
            assert connection.execute('SELECT COUNT(*) AS n FROM purchases').fetchone()['n'] > 0
            assert connection.execute('SELECT demo_seeded FROM workspaces WHERE id = 1').fetchone()['demo_seeded'] == 0
            raise RuntimeError('caller cancels')
    with database.connect() as connection:
        assert connection.execute('SELECT COUNT(*) AS n FROM vehicles').fetchone()['n'] == 1
        assert connection.execute('SELECT COUNT(*) AS n FROM purchases').fetchone()['n'] == 0
        assert populate_workspace(connection, 1) == 200
    with database.connect() as connection:
        assert connection.execute('SELECT COUNT(*) AS n FROM vehicles').fetchone()['n'] == 201
        assert populate_workspace(connection, 1) == 0


@pytest.mark.parametrize('today', ['2027-01-01', '2026-11-02', '2028-03-01'])
def test_history_cutoff_handles_year_month_and_leap_day_boundaries(db, monkeypatch, today):
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            assert tz == timezone.utc
            return cls.fromisoformat(f'{today}T12:00:00+00:00')

    monkeypatch.setattr(demo, 'datetime', FixedDatetime)
    populate_workspace(db, 1)
    dates = [row['purchased_at'][:10] for row in db.execute('SELECT purchased_at FROM purchases')]
    yesterday = (datetime.fromisoformat(today) - timedelta(days=1)).date().isoformat()
    assert max(dates) == yesterday
    assert all(day < today for day in dates)
    assert len({day[:7] for day in dates}) == 12
    assert all(row['purchased_at'] >= row['created_at'] for row in db.execute('''
        SELECT p.purchased_at, v.created_at FROM purchases p
        JOIN vehicles v ON p.vehicle_id = v.id
    '''))
