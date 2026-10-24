"""Exercise actual API and Vite processes with disposable data and credentials."""

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def request(base, path, method="GET", body=None, token=None, expected=200):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(
        base + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers=headers,
    )
    try:
        response = urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        assert response.status == expected, f"{method} {path}: {response.status}, expected {expected}"
        raw = response.read().decode()
        return json.loads(raw) if raw and "application/json" in response.headers.get("Content-Type", "") else raw


def wait_ready(process, url):
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("Server exited before becoming ready; inspect the subprocess log")
        try:
            urllib.request.urlopen(url, timeout=1).close()
            return
        except (OSError, urllib.error.URLError):
            time.sleep(0.1)
    raise TimeoutError("Server did not become ready: " + url)


def main():
    api_port, web_port = free_port(), free_port()
    api_base, web_base = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{web_port}"
    processes = []
    with tempfile.TemporaryDirectory(prefix="forecourt-smoke-") as directory:
        env = {
            **os.environ,
            "DATABASE_PATH": str(Path(directory) / "inventory.db"),
            "JWT_SECRET": secrets.token_hex(32),
            "ADMIN_EMAIL": "owner@example.com",
            "ADMIN_PASSWORD": secrets.token_urlsafe(24),
            "API_TARGET": api_base,
        }
        with open(Path(directory) / "servers.log", "w+") as log:
            try:
                python = str(ROOT / ".venv/bin/python")
                subprocess.run([python, "-m", "app.seed"], cwd=ROOT / "backend", env=env, check=True, stdout=log, stderr=log)
                processes.append(subprocess.Popen(
                    [python, "-m", "uvicorn", "app.main:production_app", "--factory", "--host", "127.0.0.1", "--port", str(api_port)],
                    cwd=ROOT / "backend", env=env, stdout=log, stderr=log,
                ))
                wait_ready(processes[-1], api_base + "/docs")
                # Invoke Vite directly so terminating the owned process leaves no npm child.
                processes.append(subprocess.Popen(
                    ["node", "node_modules/vite/bin/vite.js", "--host", "127.0.0.1", "--port", str(web_port), "--strictPort"],
                    cwd=ROOT / "frontend", env=env, stdout=log, stderr=log,
                ))
                wait_ready(processes[-1], web_base)
                assert 'id="root"' in request(web_base, "/")
                session = request(web_base, "/api/auth/login", "POST", {"email": env["ADMIN_EMAIL"], "password": env["ADMIN_PASSWORD"]})
                admin = session["access_token"]
                assert request(web_base, "/api/auth/me", token=admin)["role"] == "admin"
                assert len(request(web_base, "/api/vehicles", token=admin)) == 6
                buyer_session = request(web_base, "/api/auth/register", "POST", {"email": "buyer@example.com", "password": secrets.token_urlsafe(20)}, expected=201)
                buyer = buyer_session["access_token"]
                car = {"make": "Test", "model": "Smoke", "category": "Sedan", "price": "10.25", "quantity": 1}
                request(web_base, "/api/vehicles", "POST", car, buyer, 403)
                item = request(web_base, "/api/vehicles", "POST", car, admin, 201)
                path = f"/api/vehicles/{item['id']}"
                assert request(web_base, path + "/purchase", "POST", token=buyer)["quantity"] == 0
                request(web_base, path + "/purchase", "POST", token=buyer, expected=409)
                assert request(web_base, path + "/restock", "POST", {"quantity": 2}, admin)["quantity"] == 2
                request(web_base, path, "DELETE", token=admin, expected=204)
                assert len(request(web_base, "/api/vehicles", token=buyer)) == 6
                request(web_base, "/api/vehicles/archived", token=buyer, expected=403)
                request(web_base, path + "/restore", "POST", token=buyer, expected=403)
                request(web_base, path + "/purchase", "POST", token=buyer, expected=404)
                request(web_base, path + "/restock", "POST", {"quantity": 1}, admin, 404)
                request(web_base, path, "PUT", car, admin, 404)
                archived = request(web_base, "/api/vehicles/archived", token=admin)
                assert archived[0]['id'] == item['id'] and archived[0]['quantity'] == 2
                restored = request(web_base, path + "/restore", "POST", token=admin)
                assert restored['id'] == item['id'] and restored['quantity'] == 2 and restored['deleted_at'] is None
                request(web_base, f"/api/users/{buyer_session['user']['id']}/promote", "POST", token=admin)
                request(web_base, path, "PUT", {**car, "model": "Promoted"}, buyer)
                request(web_base, path, "DELETE", token=admin, expected=204)
                print("HTTP smoke passed: SPA, proxy, login, roles, purchase, restock, archive, blocked mutations, restore, promotion, update.")
            except Exception:
                log.flush()
                log.seek(0)
                print(log.read())
                raise
            finally:
                for process in reversed(processes):
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()


if __name__ == "__main__":
    main()
