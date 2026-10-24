# Incubyte

# Forecourt — Car Dealership Inventory

A full-stack TDD kata with FastAPI, persistent SQLite, React, and Tailwind CSS.
Browse and filter inventory, purchase one vehicle at a time, and manage the
collection and team through an admin workspace.

## Run locally

Requires Python 3.13 and Node.js 22.12 or newer (Node 22.22 was used locally).
Run these commands from the repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock
npm ci --prefix frontend
cp backend/.env.example backend/.env
```

Edit `backend/.env`: replace `JWT_SECRET` and `ADMIN_PASSWORD` with unique values
and set `ADMIN_EMAIL` to your initial administrator's email. Generate a secret:

```sh
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Start the API in one terminal:

```sh
cd backend
set -a
source .env
set +a
../.venv/bin/uvicorn app.main:production_app --factory --reload --host 127.0.0.1 --port 8000
```

Start the frontend in another terminal, from the repository root:

```sh
npm run dev --prefix frontend
```

Open **http://127.0.0.1:5173**. Sign in with the administrator credentials you
configured, or register a regular account. API documentation is at
**http://127.0.0.1:8000/docs**. The Vite development server proxies `/api` to the
backend, so browser requests use the same origin.

SQLite is stored at `backend/inventory.db` by default. Override `DATABASE_PATH`
with an absolute file path whose parent directory exists. Data survives restarts.
No in-memory database is used by the app or integration tests.

### Optional sample inventory

After loading the environment variables as above, run from `backend`:

```sh
../.venv/bin/python -m app.seed
```

This adds six sample vehicles only when the collection is empty, including an
out-of-stock vehicle. It preserves existing vehicles and creates no sample users.

## Roles and inventory rules

| Action                                                | Member | Admin |
| ----------------------------------------------------- | ------ | ----- |
| List/search all vehicles, including sold-out listings | Yes    | Yes   |
| Purchase exactly one unit per request                 | Yes    | Yes   |
| Create, update, delete, and restock                   | No     | Yes   |
| View registered users and promote them to admin       | No     | Yes   |

The first startup requires `ADMIN_EMAIL` and `ADMIN_PASSWORD`. Bootstrap is
transactional and idempotent: once any admin exists, it never creates an
additional bootstrap account. Existing regular accounts cannot be taken over
through bootstrap. Subsequent administrators are promoted in **Team access**.
Public registration cannot accept a role. Roles are checked in the database on
each API request, so an existing token gains promoted permissions immediately.
Reload the frontend after promotion to display its admin controls.

Prices are USD and are stored as integer cents, with at most two decimal places.
Stock is an integer from 0 to 1,000,000; restocking cannot exceed that limit.
Price limits are $0–$1,000,000,000. Text search is case-insensitive and literal
substring matching; supplied filters are combined with AND. Price bounds are
inclusive. Inventory statistics reflect the currently filtered collection.

Purchases use one atomic conditional database update to prevent negative stock,
including concurrent requests for the last unit. Each request is an independent
purchase; the UI disables pending submission and asks for confirmation. This is
an inventory kata: it does not collect payments, reserve stock, or store orders.

Passwords use Argon2 hashes. JWTs expire after eight hours; sessions live in
`sessionStorage` and are cleared on logout or a 401 response. Logout discards the
browser token; server-side token revocation is outside this kata's scope. Deploy
behind HTTPS and configure a same-origin `/api` reverse proxy if hosting the
production frontend output. `npm run build --prefix frontend` produces
`frontend/dist`; no deployment is included.

## API

All endpoints except registration and login require
`Authorization: Bearer <access_token>`.

| Method | Endpoint                      | Access / behavior                                     |
| ------ | ----------------------------- | ----------------------------------------------------- |
| POST   | `/api/auth/register`          | Public; `{email, password}`; returns token/user (201) |
| POST   | `/api/auth/login`             | Public; `{email, password}`; returns token/user       |
| GET    | `/api/auth/me`                | Current user and role                                 |
| GET    | `/api/vehicles`               | All vehicles, newest first                            |
| GET    | `/api/vehicles/search`        | `make`, `model`, `category`, `min_price`, `max_price` |
| POST   | `/api/vehicles`               | Admin; create (201)                                   |
| PUT    | `/api/vehicles/{id}`          | Admin; replace all editable fields                    |
| DELETE | `/api/vehicles/{id}`          | Admin; delete (204)                                   |
| POST   | `/api/vehicles/{id}/purchase` | Purchase one; no request body                         |
| POST   | `/api/vehicles/{id}/restock`  | Admin; `{quantity: positive_integer}`                 |
| GET    | `/api/users`                  | Admin; list users without password hashes             |
| POST   | `/api/users/{id}/promote`     | Admin; promote; no request body                       |

Vehicle create/update bodies contain `make`, `model`, `category`, `price`, and
`quantity`. Responses add `id`, with `price` serialized as a decimal string.
Registration requires a valid email and a password of 10–128 characters.
Errors use 401 for invalid sessions/login, 403 for permission denial, 404 for
missing records, 409 for duplicates or stock conflicts, and 422 for validation.
Use the generated OpenAPI documentation for complete schemas and examples.

## Tests and TDD history

```sh
cd backend
../.venv/bin/pytest --cov=app --cov-report=term-missing --cov-fail-under=95
cd ..
npm test --prefix frontend
npm run build --prefix frontend
npm audit --prefix frontend
python3 scripts/smoke.py
```

Backend tests exercise the HTTP API with temporary file-backed SQLite databases:
authentication, validation, permissions, CRUD, filters, promotion, persistence,
bootstrap, limits, expired tokens, and six concurrent requests for the final
unit. Frontend tests use Vitest, React Testing Library, and jsdom for card
behavior and integrated login, search, purchase, restock, and promotion flows.
UI integration tests mock HTTP responses; they do not substitute for a real
browser end-to-end test. CI runs backend tests with a 95% statement coverage
floor, frontend tests, and the production build.

The smoke script starts real API and Vite processes on temporary ports, uses a
disposable SQLite database and generated credentials, exercises requests through
the Vite proxy, and shuts down its own servers. It requires the dependencies
installed above. For an API on a custom development port, set `API_TARGET` when
starting Vite; its default remains `http://127.0.0.1:8000`.

Local verification: **25 backend tests passed, 97.64% statement coverage; 8
frontend tests passed; production build and HTTP smoke passed; npm audit found
zero vulnerabilities.** No browser layout or browser end-to-end verification was
performed. The CI workflow is committed but has not been run on GitHub.

The Git history records actual red and green stages:

- `a170080` → `a78a04f`: backend specification before implementation.
- `438ff30` → `3b2c498`: frontend card specification before implementation.
- `36d7fab` → `235333b`: failing bootstrap/stock-limit regressions, then fixes.
- `c9373d8`: optional seed specification before its implementation.

Later integration tests validate existing behavior; they are not presented as
having preceded that implementation. See [AGENTS.md](AGENTS.md) for the detailed
implementation plan and tracked progress.

## Project layout

```text
backend/app/          API factory, database, schemas, optional sample data
backend/tests/        HTTP integration and sample-data tests
frontend/src/         React app, API client, cards, reusable form/dialog components
.github/workflows/    Backend and frontend CI jobs
AGENTS.md             Agreed requirements, implementation plan and verification
```

## My AI Usage

### Tools used

ChatGPT, operating as the Codex coding agent, assisted with this implementation.
No other AI coding tool was used in this session. The Sites skill was consulted
for frontend workflow guidance; no site was created or deployed through Sites.
The vehicle illustrations are original code-based SVGs, not AI image-generator
output.

### How AI contributed

I used ChatGPT/Codex to translate the kata into an implementation plan, write
backend tests before the API, implement JWT authentication and SQLite stock
updates, and build the React/Tailwind interface. It also authored frontend tests,
reviewed edge cases, reproduced and fixed bootstrap/restock defects, prepared
sample data and CI, and wrote setup and API documentation. The agent ran the
commands and checks documented in the Git history. AI assistance was substantial
across the project, rather than limited to boilerplate.

Every commit created during this work includes the ChatGPT co-author trailer
and a description of its contribution. Earlier repository commits predate this
implementation. No claim is made that the generated code was independently
reviewed by a human or exercised manually in a browser.

### Reflection

AI accelerated the first implementation and made it practical to test permission
and concurrency cases alongside the UI. Executing the tests was essential:
review exposed two inconsistencies that the initial implementation missed, and
their failing regression tests supplied concrete evidence for the fixes. The
workflow still requires checking generated code, reviewing dependency changes,
and distinguishing mocked component tests from real browser verification.
The explicit plan and small, attributable commits make those decisions and
limitations reviewable.
