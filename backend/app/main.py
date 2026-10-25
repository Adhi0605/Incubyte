"""Workspace-scoped inventory API. Ownership is always derived from the session."""
import csv
import io
import json
import os
import sqlite3
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path
from threading import Lock

import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from pwdlib import PasswordHash

from .database import Database, public_user, public_vehicle, utc_now
from .schemas import Credentials, Login, Restock, VehicleInput, CSVImport

passwords = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


def create_app(database_path: str, jwt_secret: str):
    if len(jwt_secret) < 32:
        raise ValueError('JWT_SECRET must have at least 32 characters')
    database = Database(database_path)
    app = FastAPI(title='Forecourt — Private Indian Dealership', version='2.0.0')
    app.state.database_path = database_path
    attempts, rate_lock = defaultdict(deque), Lock()

    def rate_limit(request: Request):
        host = request.client.host if request.client else 'unknown'
        now = datetime.now(timezone.utc).timestamp()
        with rate_lock:
            recent = attempts[host]
            while recent and recent[0] < now - 60:
                recent.popleft()
            if len(recent) >= 30:
                raise HTTPException(429, 'Too many sign-in attempts. Try again in a minute.', headers={'Retry-After': '60'})
            recent.append(now)
            # Do not retain old client buckets indefinitely in a long-running host.
            if len(attempts) > 10000:
                for key in list(attempts):
                    if not attempts[key] or attempts[key][-1] < now - 60:
                        del attempts[key]

    def populate(db, workspace_id):
        from .demo import populate_workspace
        populate_workspace(db, workspace_id)
        db.execute('UPDATE workspaces SET demo_seeded=1 WHERE id=?', (workspace_id,))

    def bootstrap_admin(email, password):
        credentials = Credentials(email=email, password=password)
        with database.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM users WHERE role='admin'").fetchone():
                return
            if db.execute('SELECT 1 FROM users WHERE email=?', (credentials.email,)).fetchone():
                raise ValueError('Bootstrap email already belongs to a registered user')
            db.execute("INSERT INTO users(email,password_hash,role,workspace_id) VALUES (?,?,'admin',1)",
                       (credentials.email, passwords.hash(credentials.password)))
    app.state.bootstrap_admin = bootstrap_admin

    def seed_existing_workspaces():
        with database.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows = db.execute('SELECT DISTINCT w.id FROM workspaces w JOIN users u ON u.workspace_id=w.id WHERE w.demo_seeded=0').fetchall()
            for row in rows:
                populate(db, row['id'])
    app.state.seed_existing_workspaces = seed_existing_workspaces

    def current_user(token: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if token is None:
            raise HTTPException(401, 'Sign in to continue', headers={'WWW-Authenticate': 'Bearer'})
        try:
            payload = jwt.decode(token.credentials, jwt_secret, algorithms=['HS256'], options={'require': ['exp', 'sub']})
            user_id = int(payload['sub'])
        except (jwt.InvalidTokenError, ValueError, TypeError):
            raise HTTPException(401, 'Invalid or expired session')
        with database.connect() as db:
            row = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        if row is None:
            raise HTTPException(401, 'Invalid session')
        return public_user(row)

    def admin_user(user=Depends(current_user)):
        if user['role'] != 'admin':
            raise HTTPException(403, 'Administrator access required')
        return user

    def session(row):
        user = public_user(row)
        token = jwt.encode({'sub': str(user['id']), 'exp': datetime.now(timezone.utc) + timedelta(hours=8)}, jwt_secret, algorithm='HS256')
        return {'access_token': token, 'token_type': 'bearer', 'user': user}

    def find_vehicle(db, vehicle_id, workspace_id, archived=False, lock=False):
        row = db.execute('SELECT * FROM vehicles WHERE id=? AND workspace_id=?' + ('' if archived else ' AND deleted_at IS NULL') + (' FOR UPDATE' if lock and database.postgres else ''), (vehicle_id, workspace_id)).fetchone()
        if row is None:
            raise HTTPException(404, 'Vehicle not found')
        return public_vehicle(row)

    def event(db, user, vehicle_id, kind, delta=0):
        db.execute('INSERT INTO inventory_events(workspace_id,vehicle_id,event_type,quantity_delta,created_at,is_demo) VALUES (?,?,?,?,?,0)',
                   (user['workspace_id'], vehicle_id, kind, delta, utc_now()))

    def vehicle_values(data):
        values = data.model_dump(exclude={'price', 'images'})
        values['price_cents'] = int(data.price * 100)
        values['images_json'] = json.dumps([image.model_dump() for image in data.images])
        return values

    def insert_vehicle(db, user, data):
        values = {**vehicle_values(data), 'workspace_id': user['workspace_id'], 'created_at': utc_now(), 'updated_at': utc_now()}
        fields = ','.join(values)
        slots = ','.join('?' for _ in values)
        row = db.execute(f'INSERT INTO vehicles({fields}) VALUES ({slots}) RETURNING id', tuple(values.values())).fetchone()
        event(db, user, row['id'], 'create', data.quantity)
        return find_vehicle(db, row['id'], user['workspace_id'])

    @app.get('/api/health')
    def health():
        with database.connect() as db:
            db.execute('SELECT 1').fetchone()
        return {'status': 'ok'}

    @app.post('/api/auth/register', status_code=201, dependencies=[Depends(rate_limit)])
    def register(data: Credentials):
        password_hash = passwords.hash(data.password)
        try:
            with database.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                workspace = db.execute('INSERT INTO workspaces(name,created_at) VALUES (?,?) RETURNING id', ('My dealership', utc_now())).fetchone()['id']
                row = db.execute("INSERT INTO users(email,password_hash,role,workspace_id) VALUES (?,?,'admin',?) RETURNING id", (data.email, password_hash, workspace)).fetchone()
                populate(db, workspace)
                return session(db.execute('SELECT * FROM users WHERE id=?', (row['id'],)).fetchone())
        except Exception as exc:
            if isinstance(exc, sqlite3.IntegrityError) or type(exc).__name__ == 'UniqueViolation':
                raise HTTPException(409, 'An account with that email already exists')
            raise

    @app.post('/api/auth/login', dependencies=[Depends(rate_limit)])
    def login(data: Login):
        with database.connect() as db:
            row = db.execute('SELECT * FROM users WHERE email=?', (data.email.strip().lower(),)).fetchone()
        if row is None or not passwords.verify(data.password, row['password_hash']):
            raise HTTPException(401, 'Incorrect email or password')
        return session(row)

    @app.get('/api/auth/me')
    def me(user=Depends(current_user)):
        return user

    @app.get('/api/users')
    def users(user=Depends(admin_user)):
        with database.connect() as db:
            return [public_user(r) for r in db.execute('SELECT * FROM users WHERE workspace_id=? ORDER BY email', (user['workspace_id'],))]

    @app.post('/api/users/{user_id}/promote')
    def promote(user_id: int, user=Depends(admin_user)):
        with database.connect() as db:
            if not db.execute("UPDATE users SET role='admin' WHERE id=? AND workspace_id=?", (user_id, user['workspace_id'])).rowcount:
                raise HTTPException(404, 'User not found')
            return public_user(db.execute('SELECT * FROM users WHERE id=? AND workspace_id=?', (user_id, user['workspace_id'])).fetchone())

    @app.get('/api/vehicles')
    @app.get('/api/vehicles/search')
    def vehicles(make: str = '', model: str = '', category: str = '', condition: str = '',
                 fuel_type: str = '', transmission: str = '', city: str = '',
                 min_price: Decimal | None = Query(None, ge=0, le=1000000000),
                 max_price: Decimal | None = Query(None, ge=0, le=1000000000),
                 min_year: int | None = Query(None, ge=1990, le=2100),
                 max_year: int | None = Query(None, ge=1990, le=2100),
                 page: int = Query(1, ge=1, le=1000000), page_size: int = Query(12, ge=1, le=100),
                 sort: str = 'newest', user=Depends(current_user)):
        if min_price is not None and max_price is not None and min_price > max_price:
            raise HTTPException(422, 'Minimum price must not exceed maximum price')
        if min_year is not None and max_year is not None and min_year > max_year:
            raise HTTPException(422, 'Minimum year must not exceed maximum year')
        orders = {'newest': 'id DESC', 'price_asc': 'price_cents ASC,id DESC', 'price_desc': 'price_cents DESC,id DESC', 'year_desc': 'year DESC,id DESC', 'mileage_asc': 'mileage_km ASC,id DESC'}
        if sort not in orders:
            raise HTTPException(422, 'Unknown inventory sort')
        clauses, params = ['workspace_id=?', 'deleted_at IS NULL'], [user['workspace_id']]
        for column, value in [('make', make), ('model', model), ('category', category), ('condition', condition), ('fuel_type', fuel_type), ('transmission', transmission), ('city', city)]:
            if value.strip():
                clauses.append(f'instr(lower({column}),lower(?))>0')
                params.append(value.strip())
        for column, op, value in [('price_cents', '>=', min_price), ('price_cents', '<=', max_price), ('year', '>=', min_year), ('year', '<=', max_year)]:
            if value is not None:
                clauses.append(f'{column}{op}?')
                params.append(int((value * 100).to_integral_value(rounding=ROUND_CEILING if op == '>=' else ROUND_FLOOR)) if column == 'price_cents' else value)
        where = ' AND '.join(clauses)
        with database.connect() as db:
            # Python integer aggregation avoids SQLite int64 overflow for large
            # collections while retaining exact paise on both database engines.
            summary = {'listings': 0, 'units': 0, 'value': 0}
            for row in db.execute(f'SELECT price_cents,quantity FROM vehicles WHERE {where}', tuple(params)):
                summary['listings'] += 1
                summary['units'] += row['quantity']
                summary['value'] += row['price_cents'] * row['quantity']
            items = db.execute(f'SELECT * FROM vehicles WHERE {where} ORDER BY {orders[sort]} LIMIT ? OFFSET ?', (*params, page_size, (page - 1) * page_size)).fetchall()
        return {'items': [public_vehicle(r) for r in items], 'total': summary['listings'], 'page': page, 'page_size': page_size,
                'summary': {'listings': summary['listings'], 'units': summary['units'], 'value': format(Decimal(summary['value']) / 100, '.2f')}}

    @app.get('/api/vehicles/archived')
    def archived_vehicles(user=Depends(admin_user)):
        with database.connect() as db:
            return [public_vehicle(r) for r in db.execute('SELECT * FROM vehicles WHERE workspace_id=? AND deleted_at IS NOT NULL ORDER BY deleted_at DESC,id DESC', (user['workspace_id'],))]

    @app.post('/api/vehicles/import', status_code=201)
    def import_vehicles(data: CSVImport, user=Depends(admin_user)):
        rows = csv.DictReader(io.StringIO(data.csv))
        if not rows.fieldnames or len(set(rows.fieldnames)) != len(rows.fieldnames):
            raise HTTPException(422, 'CSV needs unique column headings')
        validated = []
        try:
            for index, row in enumerate(rows, start=2):
                if index > 501:
                    raise ValueError('Import up to 500 vehicles at a time')
                clean = {k: v for k, v in row.items() if v not in ('', None)}
                if None in clean:
                    raise ValueError(f'Row {index} has too many values')
                for field in ('quantity', 'year', 'mileage_km'):
                    if field in clean:
                        clean[field] = int(clean[field])
                validated.append(VehicleInput.model_validate(clean))
        except (ValidationError, ValueError) as exc:
            raise HTTPException(422, f'Invalid CSV row {index}: {str(exc)[:500]}')
        if not validated:
            raise HTTPException(422, 'CSV must contain at least one vehicle')
        with database.connect() as db:
            for vehicle in validated:
                insert_vehicle(db, user, vehicle)
        return {'imported': len(validated)}

    @app.post('/api/vehicles', status_code=201)
    def create_vehicle(data: VehicleInput, user=Depends(admin_user)):
        with database.connect() as db:
            return insert_vehicle(db, user, data)

    @app.get('/api/vehicles/{vehicle_id}')
    def vehicle_detail(vehicle_id: int, user=Depends(current_user)):
        with database.connect() as db:
            return find_vehicle(db, vehicle_id, user['workspace_id'])

    @app.put('/api/vehicles/{vehicle_id}')
    def update_vehicle(vehicle_id: int, data: VehicleInput, user=Depends(admin_user)):
        with database.connect() as db:
            # Lock before reading previous quantity so adjustment history is accurate.
            db.execute('BEGIN IMMEDIATE')
            previous = find_vehicle(db, vehicle_id, user['workspace_id'], lock=True)
            values = {**vehicle_values(data), 'updated_at': utc_now()}
            assignments = ','.join(f'{key}=?' for key in values)
            db.execute(f'UPDATE vehicles SET {assignments} WHERE id=? AND workspace_id=? AND deleted_at IS NULL', (*values.values(), vehicle_id, user['workspace_id']))
            event(db, user, vehicle_id, 'adjustment', data.quantity - previous['quantity'])
            return find_vehicle(db, vehicle_id, user['workspace_id'])

    @app.delete('/api/vehicles/{vehicle_id}', status_code=204)
    def delete_vehicle(vehicle_id: int, user=Depends(admin_user)):
        with database.connect() as db:
            if not db.execute('UPDATE vehicles SET deleted_at=?,updated_at=? WHERE id=? AND workspace_id=? AND deleted_at IS NULL', (utc_now(), utc_now(), vehicle_id, user['workspace_id'])).rowcount:
                raise HTTPException(404, 'Vehicle not found')
            event(db, user, vehicle_id, 'archive')
        return Response(status_code=204)

    @app.post('/api/vehicles/{vehicle_id}/restore')
    def restore_vehicle(vehicle_id: int, user=Depends(admin_user)):
        with database.connect() as db:
            changed = db.execute('UPDATE vehicles SET deleted_at=NULL,updated_at=? WHERE id=? AND workspace_id=? AND deleted_at IS NOT NULL', (utc_now(), vehicle_id, user['workspace_id'])).rowcount
            item = find_vehicle(db, vehicle_id, user['workspace_id'])
            if not changed:
                raise HTTPException(409, 'Vehicle is already active')
            event(db, user, vehicle_id, 'restore')
            return item

    @app.post('/api/vehicles/{vehicle_id}/purchase')
    def purchase(vehicle_id: int, user=Depends(current_user)):
        with database.connect() as db:
            changed = db.execute('UPDATE vehicles SET quantity=quantity-1,updated_at=? WHERE id=? AND workspace_id=? AND quantity>0 AND deleted_at IS NULL', (utc_now(), vehicle_id, user['workspace_id'])).rowcount
            item = find_vehicle(db, vehicle_id, user['workspace_id'])
            if not changed:
                raise HTTPException(409, 'This vehicle is out of stock')
            cents = int(Decimal(item['price']) * 100)
            db.execute('INSERT INTO purchases(workspace_id,vehicle_id,make,model,condition,fuel_type,quantity,unit_price_cents,total_cents,purchased_at,is_demo) VALUES (?,?,?,?,?,?,1,?,?,?,0)',
                       (user['workspace_id'], vehicle_id, item['make'], item['model'], item['condition'], item['fuel_type'], cents, cents, utc_now()))
            event(db, user, vehicle_id, 'purchase', -1)
            return item

    @app.post('/api/vehicles/{vehicle_id}/restock')
    def restock(vehicle_id: int, data: Restock, user=Depends(admin_user)):
        with database.connect() as db:
            changed = db.execute("UPDATE vehicles SET quantity=quantity+?,updated_at=? WHERE id=? AND workspace_id=? AND deleted_at IS NULL AND quantity+?<=CASE WHEN condition='used' THEN 1 ELSE 1000000 END", (data.quantity, utc_now(), vehicle_id, user['workspace_id'], data.quantity)).rowcount
            item = find_vehicle(db, vehicle_id, user['workspace_id'])
            if not changed:
                raise HTTPException(409, 'Stock limit exceeded (used vehicles have at most one unit)')
            event(db, user, vehicle_id, 'restock', data.quantity)
            return item

    @app.get('/api/analytics')
    def analytics(start_date: date | None = None, end_date: date | None = None, user=Depends(admin_user)):
        from .analytics import workspace_analytics
        if start_date and end_date and start_date > end_date:
            raise HTTPException(422, 'Start date must not exceed end date')
        end = end_date or date.today()
        month_index = end.year * 12 + end.month - 12
        first_year, first_month = divmod(month_index, 12)
        if first_year < 1:
            raise HTTPException(422, 'Select dates between 1900 and 2100')
        start = start_date or date(first_year, first_month + 1, 1)
        if start.year < 1900 or end.year > 2100:
            raise HTTPException(422, 'Select dates between 1900 and 2100')
        if start > end or (end - start).days > 3660:
            raise HTTPException(422, 'Select an ordered date range of at most ten years')
        with database.connect() as db:
            return workspace_analytics(db, user['workspace_id'], start.isoformat(), end.isoformat())

    frontend = Path(os.environ.get('FRONTEND_DIST', str(Path(__file__).resolve().parents[2] / 'frontend/dist'))).resolve()
    @app.get('/{path:path}', include_in_schema=False)
    def frontend_file(path: str):
        if path == 'api' or path.startswith('api/'):
            raise HTTPException(404, 'API endpoint not found')
        candidate = (frontend / path).resolve()
        if not candidate.is_relative_to(frontend):
            raise HTTPException(404, 'Not found')
        if candidate.is_file():
            return FileResponse(candidate)
        if '.' not in Path(path).name and (frontend / 'index.html').is_file():
            return FileResponse(frontend / 'index.html')
        raise HTTPException(404, 'Not found')
    return app


def production_app():
    path = os.environ.get('DATABASE_URL') or os.environ.get('DATABASE_PATH') or str(Path(__file__).resolve().parents[1] / 'inventory.db')
    app = create_app(path, os.environ.get('JWT_SECRET', ''))
    email, password = os.environ.get('ADMIN_EMAIL'), os.environ.get('ADMIN_PASSWORD')
    if bool(email) != bool(password):
        raise ValueError('Supply both ADMIN_EMAIL and ADMIN_PASSWORD, or neither')
    if email and password:
        app.state.bootstrap_admin(email, password)
    app.state.seed_existing_workspaces()
    return app
