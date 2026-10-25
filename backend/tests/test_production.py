from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from app.main import create_app, production_app


def test_same_origin_production_serves_spa_assets_but_never_api_fallback(tmp_path, monkeypatch):
    dist = tmp_path / 'dist'
    dist.mkdir()
    (dist / 'index.html').write_text('<!doctype html><div id="root">Forecourt</div>')
    (dist / 'cars').mkdir()
    (dist / 'cars/car.jpg').write_bytes(b'representative-photo')
    (tmp_path / 'secret').write_text('private')
    monkeypatch.setenv('FRONTEND_DIST', str(dist))
    with TestClient(create_app(str(tmp_path / 'static.db'), 'a-secret-that-is-longer-than-32-characters')) as client:
        assert client.get('/').status_code == 200
        assert 'Forecourt' in client.get('/inventory/detail').text
        assert client.get('/cars/car.jpg').content == b'representative-photo'
        assert client.get('/cars/missing.jpg').status_code == 404
        assert client.get('/api/not-an-endpoint').status_code == 404
        assert client.get('/api').status_code == 404
        assert client.get('/..%2Fsecret').status_code == 404
        assert client.get('/api/health').json() == {'status': 'ok'}


def test_auth_rate_limiting_does_not_limit_health_checks(tmp_path):
    with TestClient(create_app(str(tmp_path / 'limits.db'), 'a-secret-that-is-longer-than-32-characters')) as client:
        for _ in range(30):
            assert client.post('/api/auth/login', json={'email': 'nobody@example.com', 'password': 'wrong'}).status_code == 401
        response = client.post('/api/auth/login', json={'email': 'nobody@example.com', 'password': 'wrong'})
        assert response.status_code == 429
        assert response.headers['Retry-After'] == '60'
        assert client.get('/api/health').status_code == 200


def test_factory_accepts_registration_only_and_rejects_partial_bootstrap(tmp_path, monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'factory.db'))
    monkeypatch.setenv('JWT_SECRET', 'a-secret-that-is-longer-than-32-characters')
    monkeypatch.delenv('ADMIN_EMAIL', raising=False)
    monkeypatch.delenv('ADMIN_PASSWORD', raising=False)
    assert production_app() is not None
    monkeypatch.setenv('ADMIN_EMAIL', 'owner@example.com')
    with pytest.raises(ValueError, match='both ADMIN_EMAIL and ADMIN_PASSWORD'):
        production_app()


def test_absent_production_build_returns_404(tmp_path, monkeypatch):
    monkeypatch.setenv('FRONTEND_DIST', str(tmp_path / 'absent'))
    with TestClient(create_app(str(tmp_path / 'no-build.db'), 'a-secret-that-is-longer-than-32-characters')) as client:
        assert client.get('/').status_code == 404
