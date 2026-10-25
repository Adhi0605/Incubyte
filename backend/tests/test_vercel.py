"""Deployment contracts: fail closed storage, CDN output, and safe SPA routing."""
import importlib.util
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess

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
    # The Vercel parser rejects the nested .lock include accepted by pip.
    requirements = (ROOT / 'requirements.txt').read_text().splitlines()
    lock = (ROOT / 'backend/requirements.lock').read_text().splitlines()
    assert requirements == lock
    assert all('==' in line and not line.startswith('-r') for line in requirements if line.strip())


def test_vercel_build_includes_dev_dependencies_and_emits_cdn_output(tmp_path, monkeypatch):
    module = build_module()
    (tmp_path / 'frontend/dist').mkdir(parents=True)
    (tmp_path / 'frontend/dist/index.html').write_text('built')
    calls = []
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(module.subprocess, 'run', lambda command, **kwargs: calls.append(command))
    module.main()
    assert '--include=dev' in calls[0]
    assert (tmp_path / 'public/index.html').read_text() == 'built'
    assert (tmp_path / '.vercel/output/static/index.html').read_text() == 'built'


@pytest.mark.skipif(os.environ.get('VERIFY_VERCEL_BUILD') != '1', reason='Requires an actual Vercel production build')
def test_actual_vercel_artifacts_preserve_api_and_cdn_without_private_files():
    output = ROOT / '.vercel/output'
    config = json.loads((output / 'config.json').read_text())
    function = json.loads((output / 'functions/fastapi.func/.vc-config.json').read_text())
    assert function['runtime'] == 'python3.12'
    assert function['maxDuration'] <= 60
    paths = function['filePathMap']
    for required in ['app.py', 'backend/app/main.py', 'backend/app/database.py',
                     'frontend/dist/index.html', '_vendor/fastapi/__init__.py']:
        assert required in paths
    for path in paths:
        if path.startswith('_vendor/'):
            continue
        assert not any('.env' in part or part.endswith(('.db', '.db-wal', '.db-shm', '.sqlite', '.sqlite3', '.dump', '.pem', '.key'))
                       for part in Path(path).parts), path
        assert not path.startswith(('.agents/', 'backend/tests/'))
    static = output / 'static'
    for path in (ROOT / 'public').rglob('*'):
        if path.is_file():
            assert (static / path.relative_to(ROOT / 'public')).read_bytes() == path.read_bytes()
    assert (static / 'index.html').is_file()
    assert list((static / 'assets').glob('*.js'))
    assert not (static / 'api').exists()
    assert config['routes'][-1]['dest'] == '/fastapi'
    assert config['routes'][-1]['transforms'][0]['type'] == 'request.path'


@pytest.mark.skipif(os.environ.get('VERIFY_VERCEL_BUILD') != '1', reason='Requires an actual Vercel production build')
def test_materialized_function_serves_spa_without_source_tree_or_cdn(tmp_path):
    function = ROOT / '.vercel/output/functions/fastapi.func'
    config = json.loads((function / '.vc-config.json').read_text())
    bundle = tmp_path / 'function'
    for relative, source in config['filePathMap'].items():
        target = bundle / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if relative.startswith('_vendor/'):
            target.symlink_to(ROOT / source)
        else:
            shutil.copy2(ROOT / source, target)
    # Only materialized function files are visible to the app: no CDN copy.
    environment = os.environ.copy()
    environment['DATABASE_URL'] = 'postgresql://unused.invalid/database'
    environment['TEST_DATABASE'] = str(tmp_path / 'routes.db')
    for name in ('FRONTEND_DIST', 'PYTHONPATH', 'ADMIN_EMAIL', 'ADMIN_PASSWORD'):
        environment.pop(name, None)
    script = '''
import os, pathlib, sys
root = pathlib.Path.cwd()
sys.path[:0] = [str(root), str(root / '_vendor')]
from backend.app import main
main.production_app = lambda: main.create_app(os.environ['TEST_DATABASE'], 'artifact-smoke-secret-at-least-32-characters')
import app
assert pathlib.Path(main.__file__).resolve().is_relative_to(root)
assert not (root / 'public').exists()
from fastapi.testclient import TestClient
with TestClient(app.app) as client:
    index = (root / 'frontend/dist/index.html').read_text()
    for path in ['/', '/inventory/details', '/analytics', '/archived']:
        assert client.get(path).status_code == 200, path
        assert client.get(path).text == index, path
    assert client.get('/api/health').json() == {'status': 'ok'}
    for path in ['/api', '/api/unknown', '/api/unknown.js', '/assets/missing.js', '/cars/missing.jpg']:
        response = client.get(path)
        assert response.status_code == 404, path
        assert '<html' not in response.text.lower(), path
'''
    python = (ROOT / '.vercel/python/.venv/bin/python').resolve()
    result = subprocess.run([str(python), '-S', '-c', script], cwd=bundle,
                            env=environment, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_vercel_source_upload_preserves_tracked_photos_and_favicon():
    # Vercel uses gitignore-style rules. Test which real source files survive
    # upload, rather than checking a particular spelling of an ignore rule.
    result = subprocess.run(
        ['git', '-c', 'core.excludesFile=.vercelignore', 'check-ignore', '--no-index',
         'frontend/public/cars/magnite.jpg', 'frontend/public/favicon.svg'],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 1, f'Required frontend assets are excluded from upload: {result.stdout}'
