"""Run backend checks against a disposable local PostgreSQL cluster, if installed."""
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    for program in ('initdb', 'postgres', 'pg_isready'):
        if not shutil.which(program):
            raise SystemExit(f'{program} is required; alternatively set TEST_DATABASE_URL and run pytest directly.')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix='forecourt-postgres-') as directory:
        data = str(Path(directory) / 'data')
        with open(Path(directory) / 'postgres.log', 'w+') as log:
            subprocess.run(['initdb', '-D', data, '-A', 'trust', '-U', 'forecourt_test', '--no-locale', '--encoding=UTF8'], check=True, stdout=log, stderr=log)
            process = subprocess.Popen(['postgres', '-D', data, '-h', '127.0.0.1', '-p', str(port), '-k', directory, '-F'], stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError('PostgreSQL exited before readiness')
                    ready = subprocess.run(['pg_isready', '-h', '127.0.0.1', '-p', str(port), '-U', 'forecourt_test', '-d', 'postgres'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    if ready.returncode == 0:
                        break
                    time.sleep(0.1)
                else:
                    raise TimeoutError('PostgreSQL readiness timed out')
                env = {**os.environ, 'TEST_DATABASE_URL': f'postgresql://forecourt_test@127.0.0.1:{port}/postgres'}
                result = subprocess.run([str(ROOT / '.venv/bin/python'), '-m', 'pytest', '--cov=app', '--cov-report=term-missing', '--cov-fail-under=95', '-q', '--tb=short'], cwd=ROOT / 'backend', env=env)
                return result.returncode
            except Exception:
                log.flush()
                log.seek(0)
                print(log.read())
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


if __name__ == '__main__':
    raise SystemExit(main())
