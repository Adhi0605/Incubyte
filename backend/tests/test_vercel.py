"""Deployment contracts: fail closed storage, CDN output, and safe SPA routing."""
import importlib.util
import json
from pathlib import Path
import runpy

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def main(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    from backend.app import main
    return main


@pytest.mark.parametrize('url', [None, '', 'sqlite:///tmp/demo.db', '/tmp/demo.db',
    'postgresql:/tmp/demo.db', 'POSTGRESQL://host/database', ' postgresql://host/database',
    'postgresql://', 'postgresql://host/', 'postgresql://[invalid/database'])
def test_vercel_entry_requires_postgres_before_factory(monkeypatch, url, main):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    if url is not None:
        monkeypatch.setenv('DATABASE_URL', url)
    monkeypatch.setattr(main, 'production_app', lambda: pytest.fail('factory called'))
    with pytest.raises(ValueError, match='DATABASE_URL.*PostgreSQL'):
        runpy.run_path(str(ROOT / 'app.py'))


@pytest.mark.parametrize('scheme', ['postgres', 'postgresql'])
def test_vercel_entry_uses_existing_factory_and_routes(tmp_path, monkeypatch, scheme, main):
    dist = tmp_path / 'dist'
    dist.mkdir()
    (dist / 'index.html').write_text('<html>Vercel SPA</html>')
    (dist / 'assets').mkdir()
    (dist / 'assets/app.js').write_text('console.log("cdn")')
    monkeypatch.setenv('FRONTEND_DIST', str(dist))
    monkeypatch.setenv('DATABASE_URL', f'{scheme}://unused.invalid/database')
    # No network/real credentials: exercise the real application with a test DB.
    application = main.create_app(str(tmp_path / 'test.db'), 'vercel-test-secret-at-least-32-characters')
    monkeypatch.setattr(main, 'production_app', lambda: application)
    namespace = runpy.run_path(str(ROOT / 'app.py'))
    assert namespace['app'] is application
    with TestClient(application) as client:
        assert client.get('/').text == '<html>Vercel SPA</html>'
        assert client.get('/inventory/details').status_code == 200
        assert client.get('/assets/app.js').status_code == 200
        assert client.get('/api/health').json() == {'status': 'ok'}
        for path in ['/api', '/api/unknown', '/api/unknown.js', '/assets/missing.js', '/..%2Fsecret']:
            response = client.get(path)
            assert response.status_code == 404
            assert 'Vercel SPA' not in response.text
        assert client.post('/inventory/details').status_code == 405


def build_module():
    spec = importlib.util.spec_from_file_location('build_vercel', ROOT / 'scripts/build_vercel.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_static_publish_replaces_stale_output_and_preserves_dist(tmp_path):
    dist, public = tmp_path / 'dist', tmp_path / 'public'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text('<html>built</html>')
    (dist / 'assets/app-hash.js').write_text('compiled')
    public.mkdir()
    (public / 'stale.js').write_text('old')
    build_module().publish_static(dist, public)
    assert (public / 'index.html').read_bytes() == (dist / 'index.html').read_bytes()
    assert (public / 'assets/app-hash.js').read_text() == 'compiled'
    assert not (public / 'stale.js').exists()
    assert (dist / 'index.html').exists()


@pytest.mark.parametrize('reserved', ['api/health', '.env', 'app.py'])
def test_static_publish_rejects_reserved_or_private_output(tmp_path, reserved):
    dist = tmp_path / 'dist'
    dist.mkdir()
    (dist / 'index.html').write_text('built')
    target = dist / reserved
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('must not publish')
    with pytest.raises(ValueError):
        build_module().publish_static(dist, tmp_path / 'public')


def test_native_configuration_has_no_spa_api_rewrite():
    config = json.loads((ROOT / 'vercel.json').read_text())
    assert config['framework'] == 'fastapi'
    assert config['buildCommand'] == 'python scripts/build_vercel.py'
    assert 0 < config['functions']['app.py']['maxDuration'] <= 60
    assert config['regions'] == ['iad1']
    assert not any(key in config for key in ['builds', 'routes', 'rewrites', 'services', 'outputDirectory'])
    assert (ROOT / 'requirements.txt').read_text().strip() == '-r backend/requirements.lock'
