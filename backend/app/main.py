import os
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash

from .database import Database, public_user, public_vehicle
from .schemas import Credentials, Login, Restock, VehicleInput

passwords = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def create_app(database_path: str, jwt_secret: str):
    if len(jwt_secret) < 32:
        raise ValueError("JWT_SECRET must have at least 32 characters")
    database = Database(database_path)
    app = FastAPI(title="Forecourt Inventory API", version="1.0.0")
    app.state.database_path = database_path

    def bootstrap_admin(email, password):
        credentials = Credentials(email=email, password=password)
        with database.connect() as db:
            # Serialize the check and insert, including when multiple workers start.
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM users WHERE role = 'admin'").fetchone():
                return
            if db.execute("SELECT 1 FROM users WHERE email = ?", (credentials.email,)).fetchone():
                raise ValueError("Bootstrap email already belongs to a registered user")
            db.execute("INSERT INTO users(email, password_hash, role) VALUES (?, ?, 'admin')",
                       (credentials.email, passwords.hash(credentials.password)))

    app.state.bootstrap_admin = bootstrap_admin

    def current_user(token: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if token is None:
            raise HTTPException(401, "Sign in to continue", headers={"WWW-Authenticate": "Bearer"})
        try:
            payload = jwt.decode(token.credentials, jwt_secret, algorithms=["HS256"],
                                 options={"require": ["exp", "sub"]})
            user_id = int(payload["sub"])
        except (jwt.InvalidTokenError, ValueError, TypeError):
            raise HTTPException(401, "Invalid or expired session")
        with database.connect() as db:
            user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if user is None:
            raise HTTPException(401, "Invalid session")
        return public_user(user)

    def admin_user(user=Depends(current_user)):
        if user["role"] != "admin":
            raise HTTPException(403, "Administrator access required")
        return user

    def session(row):
        user = public_user(row)
        token = jwt.encode({"sub": str(user["id"]), "exp": datetime.now(timezone.utc) + timedelta(hours=8)},
                           jwt_secret, algorithm="HS256")
        return {"access_token": token, "token_type": "bearer", "user": user}

    def find_vehicle(db, vehicle_id):
        row = db.execute("SELECT * FROM vehicles WHERE id = ? AND deleted_at IS NULL", (vehicle_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Vehicle not found")
        return public_vehicle(row)

    @app.post("/api/auth/register", status_code=201)
    def register(data: Credentials):
        try:
            with database.connect() as db:
                result = db.execute("INSERT INTO users(email, password_hash) VALUES (?, ?)",
                                    (data.email, passwords.hash(data.password)))
                return session(db.execute("SELECT * FROM users WHERE id = ?", (result.lastrowid,)).fetchone())
        except sqlite3.IntegrityError:
            raise HTTPException(409, "An account with that email already exists")

    @app.post("/api/auth/login")
    def login(data: Login):
        with database.connect() as db:
            row = db.execute("SELECT * FROM users WHERE email = ?", (data.email.strip().lower(),)).fetchone()
        if row is None or not passwords.verify(data.password, row["password_hash"]):
            raise HTTPException(401, "Incorrect email or password")
        return session(row)

    @app.get("/api/auth/me")
    def me(user=Depends(current_user)):
        return user

    @app.get("/api/users", dependencies=[Depends(admin_user)])
    def users():
        with database.connect() as db:
            return [public_user(row) for row in db.execute("SELECT * FROM users ORDER BY email")]

    @app.post("/api/users/{user_id}/promote", dependencies=[Depends(admin_user)])
    def promote(user_id: int):
        with database.connect() as db:
            if not db.execute("UPDATE users SET role = 'admin' WHERE id = ?", (user_id,)).rowcount:
                raise HTTPException(404, "User not found")
            return public_user(db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())

    @app.get("/api/vehicles", dependencies=[Depends(current_user)])
    @app.get("/api/vehicles/search", dependencies=[Depends(current_user)])
    def vehicles(make: str = "", model: str = "", category: str = "",
                 min_price: Decimal | None = Query(default=None, ge=0, le=1000000000),
                 max_price: Decimal | None = Query(default=None, ge=0, le=1000000000)):
        if min_price is not None and max_price is not None and min_price > max_price:
            raise HTTPException(422, "Minimum price must not exceed maximum price")
        clauses, values = ["deleted_at IS NULL"], []
        for column, value in (("make", make), ("model", model), ("category", category)):
            if value:
                # instr treats wildcard characters as literal search text.
                clauses.append(f"instr(lower({column}), lower(?)) > 0")
                values.append(value.strip())
        if min_price is not None:
            clauses.append("price_cents >= ?")
            values.append(str(min_price * 100))
        if max_price is not None:
            clauses.append("price_cents <= ?")
            values.append(str(max_price * 100))
        sql = "SELECT * FROM vehicles" + (" WHERE " + " AND ".join(clauses) if clauses else "") + " ORDER BY id DESC"
        with database.connect() as db:
            return [public_vehicle(row) for row in db.execute(sql, values)]

    @app.post("/api/vehicles", status_code=201, dependencies=[Depends(admin_user)])
    def create_vehicle(data: VehicleInput):
        with database.connect() as db:
            result = db.execute("INSERT INTO vehicles(make, model, category, price_cents, quantity) VALUES (?, ?, ?, ?, ?)",
                                (data.make, data.model, data.category, int(data.price * 100), data.quantity))
            return find_vehicle(db, result.lastrowid)

    @app.get("/api/vehicles/archived", dependencies=[Depends(admin_user)])
    def archived_vehicles():
        with database.connect() as db:
            return [public_vehicle(row) for row in db.execute(
                "SELECT * FROM vehicles WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC, id DESC"
            )]

    @app.post("/api/vehicles/{vehicle_id}/restore", dependencies=[Depends(admin_user)])
    def restore_vehicle(vehicle_id: int):
        with database.connect() as db:
            changed = db.execute(
                "UPDATE vehicles SET deleted_at = NULL WHERE id = ? AND deleted_at IS NOT NULL",
                (vehicle_id,),
            ).rowcount
            item = find_vehicle(db, vehicle_id)
            if not changed:
                raise HTTPException(409, "Vehicle is already active")
            return item

    @app.put("/api/vehicles/{vehicle_id}", dependencies=[Depends(admin_user)])
    def update_vehicle(vehicle_id: int, data: VehicleInput):
        with database.connect() as db:
            if not db.execute("UPDATE vehicles SET make=?, model=?, category=?, price_cents=?, quantity=? WHERE id=? AND deleted_at IS NULL",
                              (data.make, data.model, data.category, int(data.price * 100), data.quantity, vehicle_id)).rowcount:
                raise HTTPException(404, "Vehicle not found")
            return find_vehicle(db, vehicle_id)

    @app.delete("/api/vehicles/{vehicle_id}", status_code=204, dependencies=[Depends(admin_user)])
    def delete_vehicle(vehicle_id: int):
        with database.connect() as db:
            if not db.execute(
                "UPDATE vehicles SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
                (datetime.now(timezone.utc).isoformat(), vehicle_id),
            ).rowcount:
                raise HTTPException(404, "Vehicle not found")
        return Response(status_code=204)

    @app.post("/api/vehicles/{vehicle_id}/purchase", dependencies=[Depends(current_user)])
    def purchase(vehicle_id: int):
        with database.connect() as db:
            # One conditional SQL update makes the stock check and decrement atomic.
            changed = db.execute("UPDATE vehicles SET quantity = quantity - 1 WHERE id = ? AND quantity > 0 AND deleted_at IS NULL", (vehicle_id,)).rowcount
            item = find_vehicle(db, vehicle_id)
            if not changed:
                raise HTTPException(409, "This vehicle is out of stock")
            return item

    @app.post("/api/vehicles/{vehicle_id}/restock", dependencies=[Depends(admin_user)])
    def restock(vehicle_id: int, data: Restock):
        with database.connect() as db:
            changed = db.execute(
                "UPDATE vehicles SET quantity = quantity + ? WHERE id = ? AND quantity + ? <= 1000000 AND deleted_at IS NULL",
                (data.quantity, vehicle_id, data.quantity),
            ).rowcount
            item = find_vehicle(db, vehicle_id)
            if not changed:
                raise HTTPException(409, "Stock cannot exceed 1,000,000 units")
            return item

    return app


def production_app():
    secret = os.environ.get("JWT_SECRET", "")
    path = os.environ.get("DATABASE_PATH", str(Path(__file__).resolve().parents[1] / "inventory.db"))
    app = create_app(path, secret)
    email, password = os.environ.get("ADMIN_EMAIL"), os.environ.get("ADMIN_PASSWORD")
    if email and password:
        app.state.bootstrap_admin(email, password)
    with Database(path).connect() as db:
        if not db.execute("SELECT 1 FROM users WHERE role = 'admin'").fetchone():
            raise ValueError("Set ADMIN_EMAIL and ADMIN_PASSWORD to bootstrap the initial admin")
    return app
