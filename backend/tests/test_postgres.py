"""Optional real PostgreSQL integration: TEST_DATABASE_URL=postgresql://... pytest.

Use a test database with the application's schema. Existing workspaces may be
present; assertions and cleanup concern only this run's UUID-named accounts.
"""

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.database import Database
from app.main import create_app


pytestmark = pytest.mark.skipif(
    not os.environ.get('TEST_DATABASE_URL'),
    reason='TEST_DATABASE_URL is not configured; real PostgreSQL is optional',
)


def _json(client, method, path, *, status=200, **kwargs):
    response = client.request(method, path, **kwargs)
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture(scope='module')
def postgres_context():
    url = os.environ['TEST_DATABASE_URL']
    if not url.startswith(('postgres://', 'postgresql://')):
        pytest.fail('TEST_DATABASE_URL must be a PostgreSQL connection URL')
    database = Database(url)
    assert database.postgres
    with database.connect() as db:
        existing_workspaces = {row['id'] for row in db.execute('SELECT id FROM workspaces')}
        # Exercise the actual PostgreSQL connection and dictionary row factory.
        row = db.execute('SELECT current_database() AS database_name').fetchone()
        assert isinstance(row, dict) and row['database_name']

    emails = tuple(f'postgres-{uuid4().hex}@example.com' for _ in range(2))
    today = datetime.now(timezone.utc).date()
    try:
        app = create_app(url, 'postgres-integration-secret-at-least-32-characters')
        with TestClient(app) as client:
            accounts = []
            for email in emails:
                credentials = {'email': email, 'password': 'PostgresPassword123!'}
                session = _json(client, 'POST', '/api/auth/register',
                                status=201, json=credentials)
                assert session['user']['email'] == email
                assert session['user']['role'] == 'admin'
                assert session['user']['workspace_id'] not in existing_workspaces
                accounts.append(SimpleNamespace(
                    user=session['user'], credentials=credentials,
                    headers={'Authorization': f"Bearer {session['access_token']}"},
                ))
            assert accounts[0].user['workspace_id'] != accounts[1].user['workspace_id']
            yield SimpleNamespace(
                client=client, database=database, accounts=accounts,
                dates={'start_date': (today - timedelta(days=366)).isoformat(),
                       'end_date': (today + timedelta(days=2)).isoformat()},
            )
    finally:
        # Discover by our UUID emails even if a registration response/assertion
        # failed. Never delete a pre-existing workspace, even if isolation broke.
        with database.connect() as db:
            owned = {row['workspace_id'] for row in db.execute(
                'SELECT workspace_id FROM users WHERE email IN (?, ?)', emails,
            )} - existing_workspaces
            for workspace in owned:
                for table in ('purchases', 'inventory_events', 'vehicles', 'users'):
                    db.execute(f'DELETE FROM {table} WHERE workspace_id = ?', (workspace,))
                db.execute('DELETE FROM workspaces WHERE id = ?', (workspace,))


def _create(context, owner=0, **changes):
    data = {
        'make': f'PG-{uuid4().hex}', 'model': 'Integration car',
        'category': 'SUV', 'condition': 'new', 'fuel_type': 'Petrol',
        'price': '1234567.89', 'quantity': 2, **changes,
    }
    item = _json(context.client, 'POST', '/api/vehicles', status=201,
                 headers=context.accounts[owner].headers, json=data)
    return item, data


def _analytics(context, owner=0):
    return _json(context.client, 'GET', '/api/analytics', params=context.dates,
                 headers=context.accounts[owner].headers)


def test_postgres_registration_login_and_paging_are_workspace_scoped(postgres_context):
    context = postgres_context
    client, first, second = context.client, *context.accounts
    for account in context.accounts:
        session = _json(client, 'POST', '/api/auth/login', json=account.credentials)
        assert session['user'] == account.user
        users = _json(client, 'GET', '/api/users', headers=account.headers)
        assert [user['id'] for user in users] == [account.user['id']]

    make = f'PG-{uuid4().hex}'
    own = [_create(context, make=make, quantity=index, price=price)[0]
           for index, price in enumerate(('100.01', '200.02', '300.03'), start=1)]
    foreign, _ = _create(context, owner=1, make=make, price='200.02', quantity=9)
    # Search exercises instr -> strpos, numeric parameters, LIMIT and OFFSET.
    params = {'make': make.lower(), 'min_price': '100.01', 'max_price': '300.03',
              'page_size': 2, 'sort': 'price_asc'}
    for page, expected in ((1, own[:2]), (2, own[2:]), (3, [])):
        result = _json(client, 'GET', '/api/vehicles/search', headers=first.headers,
                       params={**params, 'page': page})
        assert [item['id'] for item in result['items']] == [item['id'] for item in expected]
        assert all(item['workspace_id'] == first.user['workspace_id'] for item in result['items'])
        assert (result['total'], result['page'], result['page_size']) == (3, page, 2)
        assert result['summary'] == {'listings': 3, 'units': 6, 'value': '1400.14'}
    other = _json(client, 'GET', '/api/vehicles', headers=second.headers, params=params)
    assert [item['id'] for item in other['items']] == [foreign['id']]
    assert other['summary'] == {'listings': 1, 'units': 9, 'value': '1800.18'}


def test_postgres_purchase_snapshot_survives_edits_and_archive(postgres_context):
    context = postgres_context
    client, first, second = context.client, *context.accounts
    item, data = _create(context)
    path = f"/api/vehicles/{item['id']}"
    price = Decimal(data['price'])
    foreign, _ = _create(context, owner=1, make=data['make'], price='7654321.98')
    _json(client, 'POST', f"/api/vehicles/{foreign['id']}/purchase", headers=second.headers)
    other_before = _analytics(context, owner=1)
    before = _analytics(context)
    assert all(row['name'] != data['make'] for row in before['by_brand'])

    bought = _json(client, 'POST', path + '/purchase', headers=first.headers)
    assert bought['quantity'] == item['quantity'] - 1
    after = _analytics(context)
    summary = after['summary']
    assert Decimal(summary['recorded_sales']) == Decimal(before['summary']['recorded_sales']) + price
    assert summary['units_sold'] == before['summary']['units_sold'] + 1
    assert Decimal(summary['inventory_value']) == Decimal(before['summary']['inventory_value']) - price
    assert summary['inventory_units'] == before['summary']['inventory_units'] - 1
    assert next(row for row in after['by_brand'] if row['name'] == data['make']) == {
        'name': data['make'], 'sales': data['price'], 'units': 1,
    }

    with context.database.connect() as db:
        rows = db.execute(
            'SELECT * FROM purchases WHERE workspace_id = ? AND vehicle_id = ? AND is_demo = ?',
            (first.user['workspace_id'], item['id'], 0),
        ).fetchall()
    assert len(rows) == 1
    snapshot = rows[0]
    assert {key: snapshot[key] for key in ('make', 'model', 'condition', 'fuel_type')} == {
        key: data[key] for key in ('make', 'model', 'condition', 'fuel_type')
    }
    assert snapshot['quantity'] == 1
    assert snapshot['unit_price_cents'] == snapshot['total_cents'] == int(price * 100)
    month = snapshot['purchased_at'][:7]
    old_month = next(row for row in before['monthly_sales'] if row['month'] == month)
    new_month = next(row for row in after['monthly_sales'] if row['month'] == month)
    assert Decimal(new_month['sales']) == Decimal(old_month['sales']) + price
    assert new_month['units'] == old_month['units'] + 1

    edited = {**data, 'make': f'Edited-{uuid4().hex}', 'condition': 'used',
              'fuel_type': 'Diesel', 'quantity': 1, 'price': '9999999.99'}
    _json(client, 'PUT', path, headers=first.headers, json=edited)
    assert client.delete(path, headers=first.headers).status_code == 204
    archived = _analytics(context)
    for key in ('recorded_sales', 'units_sold', 'average_sale_price'):
        assert archived['summary'][key] == after['summary'][key]
    for key in ('monthly_sales', 'by_brand', 'by_condition'):
        assert archived[key] == after[key]
    assert archived['summary']['active_listings'] == before['summary']['active_listings'] - 1
    assert archived['summary']['inventory_units'] == before['summary']['inventory_units'] - 2
    assert Decimal(archived['summary']['inventory_value']) == Decimal(before['summary']['inventory_value']) - 2 * price
    assert _analytics(context, owner=1) == other_before


def test_postgres_foreign_vehicle_and_user_operations_return_404(postgres_context):
    context = postgres_context
    client, first, second = context.client, *context.accounts
    item, data = _create(context)
    path = f"/api/vehicles/{item['id']}"
    for method, suffix, body in (
        ('GET', '', None), ('PUT', '', data), ('DELETE', '', None),
        ('POST', '/purchase', None), ('POST', '/restock', {'quantity': 1}),
        ('POST', '/restore', None),
    ):
        response = client.request(method, path + suffix, headers=second.headers,
                                  **({'json': body} if body is not None else {}))
        assert response.status_code == 404, response.text
    response = client.post(f"/api/users/{first.user['id']}/promote", headers=second.headers)
    assert response.status_code == 404, response.text
    unchanged = _json(client, 'GET', path, headers=first.headers)
    assert unchanged == item
    with context.database.connect() as db:
        # Failed foreign operations must roll back without snapshots/events.
        events = db.execute(
            'SELECT event_type FROM inventory_events WHERE workspace_id = ? AND vehicle_id = ?',
            (first.user['workspace_id'], item['id']),
        ).fetchall()
        sales = db.execute(
            'SELECT id FROM purchases WHERE vehicle_id = ?', (item['id'],),
        ).fetchall()
    assert [row['event_type'] for row in events] == ['create']
    assert sales == []
    assert client.delete(path, headers=first.headers).status_code == 204
    assert client.post(path + '/restore', headers=second.headers).status_code == 404
    foreign_archive = _json(client, 'GET', '/api/vehicles/archived', headers=second.headers)
    assert item['id'] not in {row['id'] for row in foreign_archive}


def test_postgres_archive_restore_preserves_identity_stock_and_history(postgres_context):
    context = postgres_context
    client, first = context.client, context.accounts[0]
    item, _ = _create(context, quantity=3)
    path = f"/api/vehicles/{item['id']}"
    assert client.delete(path, headers=first.headers).status_code == 204
    with context.database.connect() as db:
        row = db.execute('SELECT quantity, deleted_at FROM vehicles WHERE id = ? AND workspace_id = ?',
                         (item['id'], first.user['workspace_id'])).fetchone()
    assert row['quantity'] == 3
    assert datetime.fromisoformat(row['deleted_at']).utcoffset() == timedelta(0)
    assert client.get(path, headers=first.headers).status_code == 404
    assert client.post(path + '/purchase', headers=first.headers).status_code == 404
    archived = _json(client, 'GET', '/api/vehicles/archived', headers=first.headers)
    assert next(row for row in archived if row['id'] == item['id'])['quantity'] == 3
    restored = _json(client, 'POST', path + '/restore', headers=first.headers)
    assert (restored['id'], restored['quantity'], restored['deleted_at']) == (item['id'], 3, None)
    assert _json(client, 'GET', path, headers=first.headers) == restored
    assert client.post(path + '/restore', headers=first.headers).status_code == 409
    archived = _json(client, 'GET', '/api/vehicles/archived', headers=first.headers)
    assert item['id'] not in {row['id'] for row in archived}
    with context.database.connect() as db:
        events = db.execute(
            'SELECT event_type, quantity_delta FROM inventory_events '
            'WHERE workspace_id = ? AND vehicle_id = ? ORDER BY id',
            (first.user['workspace_id'], item['id']),
        ).fetchall()
    assert [(row['event_type'], row['quantity_delta']) for row in events] == [
        ('create', 3), ('archive', 0), ('restore', 0),
    ]
