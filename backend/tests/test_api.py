import concurrent.futures

import pytest
from fastapi.testclient import TestClient
from app.main import create_app


@pytest.fixture
def context(tmp_path):
    app = create_app(str(tmp_path / "test.db"), "test-secret-that-is-at-least-32-characters")
    app.state.bootstrap_admin("owner@example.com", "AdminPassword123!")
    with TestClient(app) as client:
        admin = client.post("/api/auth/login", json={"email": "owner@example.com", "password": "AdminPassword123!"}).json()["access_token"]
        user = client.post("/api/auth/register", json={"email": "buyer@example.com", "password": "BuyerPassword123!"}).json()["access_token"]
        yield client, {"Authorization": f"Bearer {admin}"}, {"Authorization": f"Bearer {user}"}, app


def vehicle(**changes):
    return {"make": "Toyota", "model": "Camry", "category": "Sedan", "price": "32000.50", "quantity": 2, **changes}


def add(context, **changes):
    client, admin, _, _ = context
    response = client.post("/api/vehicles", headers=admin, json=vehicle(**changes))
    assert response.status_code == 201
    return response.json()


def test_registration_login_and_duplicate(context):
    client, _, _, _ = context
    data = {"email": "NEW@EXAMPLE.COM", "password": "Password123!"}
    response = client.post("/api/auth/register", json=data)
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "user"
    assert "password" not in response.json()["user"]
    assert client.post("/api/auth/register", json=data).status_code == 409
    assert client.post("/api/auth/login", json={**data, "password": "wrong"}).status_code == 401
    assert client.post("/api/auth/login", json=data).status_code == 200


def test_registration_cannot_choose_role(context):
    client, _, _, _ = context
    assert client.post("/api/auth/register", json={"email": "evil@example.com", "password": "Password123!", "role": "admin"}).status_code == 422


@pytest.mark.parametrize("data", [{"email": "invalid", "password": "Password123!"}, {"email": "ok@example.com", "password": "short"}])
def test_invalid_registration(context, data):
    assert context[0].post("/api/auth/register", json=data).status_code == 422


def test_authentication_required(context):
    client, _, _, _ = context
    for path in ["/api/vehicles", "/api/vehicles/search", "/api/auth/me", "/api/users"]:
        assert client.get(path).status_code == 401
    assert client.get("/api/vehicles", headers={"Authorization": "Bearer forged"}).status_code == 401


def test_crud_and_search(context):
    client, admin, user, _ = context
    item = add(context)
    add(context, make="Ford", model="Bronco", category="SUV", price="50000", quantity=0)
    assert len(client.get("/api/vehicles", headers=user).json()) == 2
    for query in ["make=toy", "model=CAM", "category=sedan", "min_price=32000&max_price=33000", "make=toy&category=sedan"]:
        results = client.get(f"/api/vehicles/search?{query}", headers=user).json()
        assert [r["id"] for r in results] == [item["id"]]
    assert client.get("/api/vehicles/search?make=missing", headers=user).json() == []
    assert client.get("/api/vehicles/search?min_price=100&max_price=1", headers=user).status_code == 422
    updated = client.put(f"/api/vehicles/{item['id']}", headers=admin, json=vehicle(model="Corolla"))
    assert updated.json()["model"] == "Corolla"
    assert client.delete(f"/api/vehicles/{item['id']}", headers=admin).status_code == 204
    assert client.post(f"/api/vehicles/{item['id']}/purchase", headers=user).status_code == 404


def test_admin_permissions(context):
    client, _, user, _ = context
    item = add(context)
    for method, path, body in [("post", "/api/vehicles", vehicle()), ("put", f"/api/vehicles/{item['id']}", vehicle()), ("delete", f"/api/vehicles/{item['id']}", None), ("post", f"/api/vehicles/{item['id']}/restock", {"quantity": 2}), ("post", "/api/users/1/promote", None)]:
        assert client.request(method, path, headers=user, **({"json": body} if body else {})).status_code == 403
    assert client.get("/api/users", headers=user).status_code == 403


def test_promote_user_takes_effect_for_existing_token(context):
    client, admin, user, _ = context
    users = client.get("/api/users", headers=admin).json()
    buyer = next(u for u in users if u["email"] == "buyer@example.com")
    assert client.post(f"/api/users/{buyer['id']}/promote", headers=admin).json()["role"] == "admin"
    assert client.post("/api/vehicles", headers=user, json=vehicle()).status_code == 201
    assert client.post("/api/users/99999/promote", headers=admin).status_code == 404


def test_purchase_and_restock(context):
    client, admin, user, _ = context
    item = add(context, quantity=1)
    path = f"/api/vehicles/{item['id']}"
    assert client.post(path + "/purchase", headers=user).json()["quantity"] == 0
    assert client.post(path + "/purchase", headers=user).status_code == 409
    assert client.post(path + "/restock", headers=admin, json={"quantity": 4}).json()["quantity"] == 4
    for quantity in [0, -1, 1.5, True]:
        assert client.post(path + "/restock", headers=admin, json={"quantity": quantity}).status_code == 422


def test_concurrent_purchases_cannot_oversell(context):
    client, _, user, _ = context
    item = add(context, quantity=1)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        statuses = list(pool.map(lambda _: client.post(f"/api/vehicles/{item['id']}/purchase", headers=user).status_code, range(6)))
    assert statuses.count(200) == 1
    assert statuses.count(409) == 5
    assert client.get("/api/vehicles", headers=user).json()[0]["quantity"] == 0


@pytest.mark.parametrize("change", [{"price": "-1"}, {"price": "1.234"}, {"price": "NaN"}, {"quantity": -1}, {"quantity": 1.5}, {"quantity": True}, {"make": " "}])
def test_invalid_vehicle(context, change):
    client, admin, _, _ = context
    assert client.post("/api/vehicles", headers=admin, json=vehicle(**change)).status_code == 422


def test_missing_vehicle(context):
    client, admin, user, _ = context
    assert client.put("/api/vehicles/999", headers=admin, json=vehicle()).status_code == 404
    assert client.delete("/api/vehicles/999", headers=admin).status_code == 404
    assert client.post("/api/vehicles/999/restock", headers=admin, json={"quantity": 1}).status_code == 404


def test_database_persists_and_bootstrap_does_not_create_second_admin(context):
    client, _, _, app = context
    add(context)
    app.state.bootstrap_admin("second@example.com", "AnotherPassword123!")
    fresh = create_app(app.state.database_path, "test-secret-that-is-at-least-32-characters")
    with TestClient(fresh) as other:
        response = other.post("/api/auth/login", json={"email": "owner@example.com", "password": "AdminPassword123!"})
        headers = {"Authorization": "Bearer " + response.json()["access_token"]}
        assert len(other.get("/api/vehicles", headers=headers).json()) == 1
        assert len(other.get("/api/users", headers=headers).json()) == 2
