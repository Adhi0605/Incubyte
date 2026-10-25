import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.database import Database


@pytest.fixture
def private(tmp_path):
    app = create_app(str(tmp_path / 'private.db'), 'a-secret-that-is-longer-than-32-characters')
    with TestClient(app) as client:
        sessions = []
        for email in ['one@example.com', 'two@example.com']:
            response = client.post('/api/auth/register', json={'email': email, 'password': 'Password123!'})
            assert response.status_code == 201
            sessions.append(response.json())
        yield client, app, sessions


def header(session):
    return {'Authorization': 'Bearer ' + session['access_token']}


def test_registration_automatically_creates_private_admin_and_inventory(private):
    client, _, sessions = private
    assert sessions[0]['user']['role'] == 'admin'
    assert sessions[0]['user']['workspace_id'] != sessions[1]['user']['workspace_id']
    first = client.get('/api/vehicles', headers=header(sessions[0])).json()
    second = client.get('/api/vehicles', headers=header(sessions[1])).json()
    assert first['total'] == second['total'] == 200
    assert first['page_size'] == 12
    assert len(first['items']) == 12
    assert not {v['id'] for v in first['items']}.intersection(v['id'] for v in second['items'])
    assert all(v['currency'] == 'INR' for v in first['items'])


def test_foreign_vehicle_ids_are_inaccessible_for_every_operation(private):
    client, _, sessions = private
    own, other = map(header, sessions)
    vehicle = client.get('/api/vehicles', headers=own).json()['items'][0]
    path = f"/api/vehicles/{vehicle['id']}"
    body = {'make': 'Tata', 'model': 'Nexon', 'category': 'SUV', 'price': '1200000', 'quantity': 1}
    for method, suffix, data in [('GET', '', None), ('PUT', '', body), ('DELETE', '', None), ('POST', '/purchase', None), ('POST', '/restock', {'quantity': 1}), ('POST', '/restore', None)]:
        response = client.request(method, path + suffix, headers=other, **({'json': data} if data else {}))
        assert response.status_code == 404
    assert client.delete(path, headers=own).status_code == 204
    assert client.get('/api/vehicles/archived', headers=other).json() == []
    assert client.post(path + '/restore', headers=other).status_code == 404
    assert client.post(path + '/restore', headers=own).status_code == 200


def test_users_and_promotion_are_workspace_scoped(private):
    client, _, sessions = private
    users = client.get('/api/users', headers=header(sessions[0])).json()
    assert [u['email'] for u in users] == ['one@example.com']
    assert client.post(f"/api/users/{sessions[1]['user']['id']}/promote", headers=header(sessions[0])).status_code == 404


def test_purchase_history_is_atomic_scoped_and_uses_snapshot_price(private):
    client, app, sessions = private
    headers = header(sessions[0])
    item = client.post('/api/vehicles', headers=headers, json={'make': 'Tata', 'model': 'Tiago', 'category': 'Hatchback', 'condition': 'used', 'price': '500000.25', 'quantity': 1, 'mileage_km': 18000}).json()
    path = f"/api/vehicles/{item['id']}"
    assert client.post(path + '/purchase', headers=headers).json()['quantity'] == 0
    assert client.post(path + '/purchase', headers=headers).status_code == 409
    assert client.delete(path, headers=headers).status_code == 204
    with Database(app.state.database_path).connect() as db:
        rows = db.execute('SELECT * FROM purchases WHERE vehicle_id = ?', (item['id'],)).fetchall()
        assert len(rows) == 1
        assert rows[0]['total_cents'] == 50000025
        assert rows[0]['workspace_id'] == sessions[0]['user']['workspace_id']
    today = date.today().isoformat()
    stats = client.get(f'/api/analytics?start_date={today}&end_date={today}', headers=headers).json()
    assert stats['summary']['recorded_sales'] == '500000.25'
    other = client.get(f'/api/analytics?start_date={today}&end_date={today}', headers=header(sessions[1])).json()
    assert other['summary']['recorded_sales'] == '0.00'


def test_filters_pagination_summary_and_used_stock(private):
    client, _, sessions = private
    headers = header(sessions[0])
    response = client.get('/api/vehicles/search?condition=used&page_size=7&sort=price_asc', headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data['items']) == 7
    assert data['summary']['listings'] == data['total']
    assert all(item['condition'] == 'used' and item['quantity'] <= 1 for item in data['items'])
    assert [float(v['price']) for v in data['items']] == sorted(float(v['price']) for v in data['items'])
    assert client.get('/api/vehicles?page_size=101', headers=headers).status_code == 422
    assert client.get('/api/vehicles?min_year=2025&max_year=2000', headers=headers).status_code == 422
    assert client.get('/api/analytics?start_date=2026-12-31&end_date=2026-01-01', headers=headers).status_code == 422
    assert client.get('/api/analytics?start_date=invalid', headers=headers).status_code == 422
    item = client.post('/api/vehicles', headers=headers, json={'make': 'Honda', 'model': 'City', 'category': 'Sedan', 'condition': 'used', 'price': '800000', 'quantity': 1}).json()
    assert client.post(f"/api/vehicles/{item['id']}/restock", headers=headers, json={'quantity': 1}).status_code == 409
    invalid = {'make': 'Honda', 'model': 'City', 'category': 'Sedan', 'condition': 'used', 'price': '800000', 'quantity': 2}
    assert client.post('/api/vehicles', headers=headers, json=invalid).status_code == 422
    invalid['quantity'] = 1
    invalid['info_url'] = 'javascript:alert(1)'
    assert client.post('/api/vehicles', headers=headers, json=invalid).status_code == 422


def test_csv_import_validates_all_rows_and_stays_in_workspace(private):
    client, _, sessions = private
    headers = header(sessions[0])
    invalid = 'make,model,category,price,quantity,condition\nTata,Tiago,Hatchback,600000,1,new\nTata,Nexon,SUV,-1,1,new\n'
    assert client.post('/api/vehicles/import', headers=headers, json={'csv': invalid}).status_code == 422
    assert client.get('/api/vehicles', headers=headers).json()['total'] == 200
    valid = invalid.replace('-1,1,new', '1000000,1,new')
    assert client.post('/api/vehicles/import', headers=headers, json={'csv': valid}).json() == {'imported': 2}
    assert client.get('/api/vehicles', headers=headers).json()['total'] == 202
    assert client.get('/api/vehicles', headers=header(sessions[1])).json()['total'] == 200


def test_health_and_unknown_api_do_not_return_spa(private):
    client, _, _ = private
    assert client.get('/api/health').json() == {'status': 'ok'}
    assert client.get('/api/not-real').status_code == 404


def test_failed_purchase_record_rolls_back_stock_and_events(private):
    import sqlite3
    from contextlib import closing
    client, app, sessions = private
    headers = header(sessions[0])
    item = client.post('/api/vehicles', headers=headers, json={'make': 'Test', 'model': 'Atomic', 'category': 'Sedan', 'price': '10.25', 'quantity': 1}).json()
    with closing(sqlite3.connect(app.state.database_path)) as db:
        with db:
            db.execute("CREATE TRIGGER fail_live_purchase BEFORE INSERT ON purchases WHEN NEW.is_demo=0 BEGIN SELECT RAISE(ABORT,'record failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='record failure'):
        client.post(f"/api/vehicles/{item['id']}/purchase", headers=headers)
    assert client.get(f"/api/vehicles/{item['id']}", headers=headers).json()['quantity'] == 1
    with Database(app.state.database_path).connect() as db:
        assert db.execute('SELECT COUNT(*) FROM purchases WHERE vehicle_id=?', (item['id'],)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM inventory_events WHERE vehicle_id=? AND event_type='purchase'", (item['id'],)).fetchone()[0] == 0


def test_client_cannot_choose_workspace_or_inject_gallery_links(private):
    client, _, sessions = private
    headers = header(sessions[0])
    body = {'make': 'Test', 'model': 'Secure', 'category': 'Sedan', 'price': '10', 'quantity': 1, 'workspace_id': sessions[1]['user']['workspace_id']}
    assert client.post('/api/vehicles', headers=headers, json=body).status_code == 422
    del body['workspace_id']
    for url in ['javascript:alert(1)', 'http://example.com/image.jpg', '/cars/../secret.env']:
        assert client.post('/api/vehicles', headers=headers, json={**body, 'images': [{'url': url}]}).status_code == 422
    own = client.get(f"/api/vehicles?workspace_id={sessions[1]['user']['workspace_id']}", headers=headers).json()
    assert all(v['workspace_id'] == sessions[0]['user']['workspace_id'] for v in own['items'])


def test_default_analytics_chart_has_twelve_calendar_months(private):
    client, _, sessions = private
    headers = header(sessions[0])
    data = client.get('/api/analytics', headers=headers).json()
    assert len(data['monthly_sales']) == 12
    assert data['monthly_sales'][-1]['month'] == date.today().strftime('%Y-%m')
    historical = client.get('/api/analytics?end_date=2025-06-30', headers=headers)
    assert historical.status_code == 200
    assert len(historical.json()['monthly_sales']) == 12
    assert historical.json()['monthly_sales'][-1]['month'] == '2025-06'
    assert client.get('/api/analytics?start_date=9999-12-30&end_date=9999-12-31', headers=headers).status_code == 422
