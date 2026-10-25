"""Real PostgreSQL migration checks; TEST_DATABASE_URL must be disposable."""
import os
from contextlib import closing
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.database import Database, utc_now
from app.main import create_app, passwords
from app.transfer import MigrationError, migrate_sqlite_to_postgres

SECRET = 'migration-test-secret-at-least-32-characters'


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'source.db'
    app = create_app(str(path), SECRET)
    app.state.bootstrap_admin('owner@example.com', 'OwnerPassword123!')
    with Database(str(path)).connect() as db:
        db.execute('INSERT INTO workspaces(id,name,created_at,demo_seeded) VALUES (2,?,?,1)', ('Second workspace', utc_now()))
        db.execute('UPDATE workspaces SET demo_seeded=1 WHERE id=1')
        db.execute("INSERT INTO users(id,email,password_hash,role,workspace_id) VALUES (2,?,?,'admin',2)", ('second@example.com', passwords.hash('SecondPassword123!')))
    with TestClient(app) as client:
        session = client.post('/api/auth/login', json={'email': 'owner@example.com', 'password': 'OwnerPassword123!'}).json()
        headers = {'Authorization': 'Bearer ' + session['access_token']}
        car = {'make': 'Tata', 'model': 'Tiago', 'category': 'Hatchback', 'price': '600000.25', 'quantity': 1, 'condition': 'used', 'images': [{'url': '/cars/tiago.jpg', 'alt': 'Representative Tiago', 'credit': 'Test author'}]}
        item = client.post('/api/vehicles', json=car, headers=headers).json()
        assert client.post(f"/api/vehicles/{item['id']}/purchase", headers=headers).status_code == 200
        assert client.delete(f"/api/vehicles/{item['id']}", headers=headers).status_code == 204
        client.post('/api/vehicles', json={**car, 'model': 'Nexon', 'quantity': 3, 'condition': 'new'}, headers=headers)
    yield path, session


@pytest.fixture
def postgres_url():
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.skip('TEST_DATABASE_URL is not configured')
    import psycopg
    from psycopg import sql
    schema = 'transfer_' + uuid4().hex
    with psycopg.connect(url, autocommit=True) as connection:
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
    split = urlsplit(url)
    query = dict(parse_qsl(split.query))
    query['options'] = '-c search_path=' + schema
    isolated = urlunsplit((split.scheme, split.netloc, split.path, urlencode(query, quote_via=quote), split.fragment))
    try:
        yield isolated
    finally:
        with psycopg.connect(url, autocommit=True) as connection:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))


def test_rejects_non_postgres_target_without_modifying_source(source):
    path, _ = source
    before = path.read_bytes()
    with pytest.raises(MigrationError, match='PostgreSQL'):
        migrate_sqlite_to_postgres(path, 'sqlite:///unwanted.db')
    assert path.read_bytes() == before


def test_transfer_preserves_all_rows_credentials_sessions_and_analytics(source, postgres_url):
    path, session = source
    result = migrate_sqlite_to_postgres(path, postgres_url)
    assert result['status'] == 'migrated'
    assert result['tables']['users']['rows'] == 2
    assert result['tables']['vehicles']['rows'] == 2
    assert result['tables']['purchases']['rows'] == 1
    assert all(entry['sha256'] for entry in result['tables'].values())
    for table in ('workspaces', 'users', 'vehicles', 'purchases', 'inventory_events'):
        with Database(str(path)).connect() as source_db, Database(postgres_url).connect() as target:
            assert [dict(row) for row in source_db.execute(f'SELECT * FROM {table} ORDER BY id')] == [dict(row) for row in target.execute(f'SELECT * FROM {table} ORDER BY id')]
    headers = {'Authorization': 'Bearer ' + session['access_token']}
    with TestClient(create_app(postgres_url, SECRET)) as client:
        assert client.get('/api/auth/me', headers=headers).json() == session['user']
        login = client.post('/api/auth/login', json={'email': 'owner@example.com', 'password': 'OwnerPassword123!'})
        assert login.status_code == 200
        assert client.get('/api/vehicles/archived', headers=headers).json()[0]['quantity'] == 0
        assert client.get('/api/vehicles', headers=headers).json()['total'] == 1
        assert client.get('/api/analytics', headers=headers).json()['summary']['recorded_sales'] == '600000.25'
        second = client.post('/api/auth/login', json={'email': 'second@example.com', 'password': 'SecondPassword123!'}).json()
        assert client.get('/api/vehicles', headers={'Authorization': 'Bearer ' + second['access_token']}).json()['total'] == 0


def test_identical_migration_can_be_verified_again_without_duplicates(source, postgres_url):
    path, _ = source
    first = migrate_sqlite_to_postgres(path, postgres_url)
    again = migrate_sqlite_to_postgres(path, postgres_url)
    assert again['status'] == 'already_verified'
    assert again['tables'] == first['tables']


def test_transfer_refuses_a_populated_different_target(source, postgres_url):
    path, _ = source
    target = Database(postgres_url)
    with target.connect() as db:
        db.execute("INSERT INTO users(email,password_hash,role,workspace_id) VALUES ('existing@example.com','existing-hash','admin',1)")
    with pytest.raises(MigrationError, match='not empty'):
        migrate_sqlite_to_postgres(path, postgres_url)
    with target.connect() as db:
        assert db.execute('SELECT COUNT(*) AS n FROM users').fetchone()['n'] == 1
        assert db.execute('SELECT email FROM users').fetchone()['email'] == 'existing@example.com'


def test_postgres_sequences_continue_after_imported_ids(source, postgres_url):
    path, session = source
    migrate_sqlite_to_postgres(path, postgres_url)
    with TestClient(create_app(postgres_url, SECRET)) as client:
        headers = {'Authorization': 'Bearer ' + session['access_token']}
        result = client.post('/api/vehicles', headers=headers, json={'make': 'Honda', 'model': 'City', 'category': 'Sedan', 'price': '1000000', 'quantity': 1})
        assert result.status_code == 201
        assert result.json()['id'] > 2
        registered = client.post('/api/auth/register', json={'email': 'new@example.com', 'password': 'Password123!'})
        assert registered.status_code == 201
        assert registered.json()['user']['id'] > 2
        assert registered.json()['user']['workspace_id'] > 2


def test_insert_failure_rolls_back_entire_target(source, postgres_url):
    import psycopg
    path, _ = source
    target = Database(postgres_url)
    with psycopg.connect(postgres_url) as db:
        db.execute("CREATE FUNCTION reject_purchase() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'forced migration failure'; END $$")
        db.execute('CREATE TRIGGER reject_purchase BEFORE INSERT ON purchases FOR EACH ROW EXECUTE FUNCTION reject_purchase()')
    with pytest.raises(MigrationError, match='rolled back'):
        migrate_sqlite_to_postgres(path, postgres_url)
    with target.connect() as db:
        for table in ('users', 'vehicles', 'purchases', 'inventory_events'):
            assert db.execute(f'SELECT COUNT(*) AS n FROM {table}').fetchone()['n'] == 0
        assert db.execute('SELECT COUNT(*) AS n FROM workspaces').fetchone()['n'] == 1


def test_connection_errors_do_not_expose_credentials(source, monkeypatch):
    path, _ = source
    def unavailable(_):
        raise RuntimeError('connection failed: postgres://user:private-password@host/db')
    monkeypatch.setattr('app.transfer.Database', unavailable)
    with pytest.raises(MigrationError, match='initialize PostgreSQL') as error:
        migrate_sqlite_to_postgres(path, 'postgresql://user:private-password@localhost/db')
    assert 'private-password' not in str(error.value)
