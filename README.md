# Incubyte

# Forecourt — Indian Car Dealership Portfolio

**Live website: [forecourt-inventory.vercel.app](https://forecourt-inventory.vercel.app)**

A full-stack dealership demo with **private persistent workspaces**, 200 Indian
new/used listings per account, attributed car photographs, and recorded-sales
analytics. Built with FastAPI, React, Tailwind, and PostgreSQL. SQLite remains
supported for isolated tests, local compatibility, and rollback snapshots.

Register and use the application normally. Your account automatically owns an
independent workspace: purchases, edits, archives, restores, imports, and charts
never affect another account. There is no demo-start gate or scheduled reset.

## PostgreSQL migration

The existing running application was migrated from SQLite to **persistent
PostgreSQL on 2026-10-25**, including its actual data; this is separate from the
earlier PostgreSQL compatibility work. At cutover, all 3 workspaces, 3 users,
605 vehicles, 723 purchases and 1,323 inventory events passed full row-hash
verification, and analytics matched for every workspace. IDs, password hashes,
archived rows, images and historical prices were retained. The existing admin
login was verified after switching the private runtime `DATABASE_URL`.

The data was then transferred to **Neon Free PostgreSQL 18**, verified again,
and the active runtime switched to its pooled TLS connection. The intermediate
local PostgreSQL service is retained privately as a rollback copy, with SCRAM
authentication and a dedicated non-superuser app role. SQLite snapshots and a
PostgreSQL dump were retained privately for rollback. Secrets and database files
are not committed. Fresh checkouts must supply their own PostgreSQL URL; fallback
SQLite selection does not automatically transfer data.

Use [docs/MIGRATION.md](docs/MIGRATION.md) for the verified transfer utility,
cutover/rollback procedure and migration checks. The production Vercel site uses the same hosted Neon database; localhost is
never used by the cloud app. The public release passed HTTPS checks for existing
admin login, photos, deep links, isolated registrations, purchase analytics,
archiving and restoration.

## What is included

- **Indian catalog:** 100 new and 100 individual used listings across 25 model
  families, with INR prices, year, trim, kilometres, fuel, transmission, colour,
  city, stock number and descriptions. Prices/specifications are synthetic.
- **Photographs:** 25 local representative photos from Wikimedia Commons,
  retained attribution and license metadata, a detail gallery, and manufacturer
  information links. See [ASSET_CREDITS.md](ASSET_CREDITS.md). A representative
  model image is not evidence of the condition/trim of a synthetic listing.
- **Search:** server pagination, sorting, make/model/category, new/used, fuel,
  transmission, city, price and year filters. Summary cards cover every match,
  independently of the current page. Admins can import validated CSV inventory.
- **Inventory:** add/edit, purchase one unit, restock, soft-delete and restore.
  Used listings hold at most one unit. Archived vehicles cannot be purchased,
  edited or restocked and are excluded from inventory totals.
- **Analytics:** twelve months of synthetic purchase history, date-filtered
  recorded sales/units/average price, monthly chart, brand and condition sales,
  fuel inventory, low stock and aging stock. Purchase snapshots survive later
  price changes and archiving. No payments are collected or implied.
- **Hosting:** native Vercel FastAPI deployment with built React/photos served
  from the same origin, Neon PostgreSQL integration, health checks, and generated
  static CDN assets. Docker/Compose and the previous Render blueprint remain
  alternative configurations. CI, backup and isolation checks are included.

## Run locally

Requires Python 3.13 and Node.js 22.12 or newer.

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock
npm ci --prefix frontend
cp backend/.env.example backend/.env
```

Edit `backend/.env` and replace `JWT_SECRET` with a unique secret. Generate one:

```sh
python3 -c 'import secrets; print(secrets.token_hex(32))'
```

Bootstrap credentials are optional. Registration automatically creates an admin
inside the new account's private workspace. To provision an initial owner, set
both `ADMIN_EMAIL` and `ADMIN_PASSWORD`; never commit actual credentials.

Start the API:

```sh
cd backend
set -a
source .env
set +a
../.venv/bin/uvicorn app.main:production_app --factory --reload --host 127.0.0.1 --port 8000
```

In another terminal, from the repository root:

```sh
npm run dev --prefix frontend
```

Open **http://127.0.0.1:5173** and register or log in. API docs:
**http://127.0.0.1:8000/docs**. Vite proxies `/api` to port 8000. For a custom
API development address, set `API_TARGET` when starting Vite.

The default database is `backend/inventory.db`. `DATABASE_PATH` overrides the
SQLite file; its parent directory must exist. `DATABASE_URL=postgresql://...`
(or `postgres://...`) takes precedence and selects PostgreSQL. Data persists
between visits and service restarts. Switching database engines starts from the
selected database; it does not automatically transfer the old database.

### Serve the production build locally

```sh
npm run build --prefix frontend
# Start the API as above; open http://127.0.0.1:8000 instead of the Vite URL.
```

FastAPI serves `frontend/dist` by default. `FRONTEND_DIST` can select an absolute
build directory. Missing API URLs return JSON errors rather than the SPA HTML.

## Workspace ownership and migration

Each normal registration creates a separate workspace and its owner-admin in
one transaction, along with the sample inventory and historical records.
No client can select a workspace ID at registration or in vehicle bodies.
The backend reads the user and workspace from the database on every request;
roles and workspace IDs supplied in a token payload are not used for access.
Every inventory and analytics operation includes that workspace restriction.

New account owners can manage only their own vehicles. Scoped user-list and
promotion endpoints remain available for regular members assigned to the same
workspace; independently registered accounts are not members of one another's
workspace and cannot be promoted or inspected by its owner. There is no global
"all users" admin console or workspace-sharing/invitation flow in this demo.

An existing SQLite database migrates additively on startup. The original owner
retains the original inventory in the legacy workspace. Other legacy accounts
receive separate owner workspaces. Existing email/password hashes, inventory,
archive timestamps and IDs are retained. Unseeded workspaces receive the Indian
catalog without overwriting custom listings or later owner edits; seeding is
idempotent. Old sample amounts are preserved as numeric values; this is not a
foreign-exchange conversion.

JWTs expire after eight hours and are stored in browser `sessionStorage`.
Logout discards the browser token; there is no server-side token revocation.
Passwords use Argon2. Login/registration share an in-process per-client rate
limit; public hosting should also apply appropriate host-level traffic controls.

## Inventory, money and historical data

Prices are INR, stored as integer paise and serialized as decimal strings.
Price range: ₹0–₹1,000,000,000, with at most two decimal places. Stock is an
integer from 0–1,000,000 for new listings and 0–1 for individual used listings.
Each purchase is a separate inventory purchase of exactly one unit. The atomic
stock update, purchase snapshot and inventory event commit together; a failed
record insert rolls the stock change back. Pending UI actions are disabled.

Deletion sets a UTC `deleted_at` timestamp. **Archived vehicles** is admin-only;
Restore clears the timestamp while preserving identity, details and stock.
Simultaneous restores succeed once; an active vehicle returns 409. Missing or
foreign-workspace IDs return 404. There is no permanent-delete endpoint.
Records permanently deleted before soft deletion cannot be recovered.

Seeded history ends yesterday; purchases made today are live demonstration
activity. All listings and historical activity are synthetic, not market quotes,
real vehicle availability, inspection reports or payment receipts. Dashboard
sales charts filter historical purchase snapshots; inventory cards, fuel units,
low stock (≤2), and aging stock (90+ days with stock) describe current inventory.

### CSV import

Use the Inventory **Import CSV** action. Up to 500 rows are validated before
anything is inserted. If any row fails, none of the rows are imported.

```csv
make,model,category,price,quantity,condition,year,mileage_km,fuel_type,transmission,city
Tata,Tiago,Hatchback,650000,3,new,2026,0,Petrol,Manual,Pune
Honda,City,Sedan,850000,1,used,2021,32000,Petrol,Automatic,Delhi
```

The gallery editor supports up to eight HTTPS image URLs or existing local
`/cars/` assets with alt text and optional credit/source/license metadata. Binary
uploads and external image-storage provisioning are not part of this version.
No third-party API key is required to browse the bundled catalog.

## API

Except health, registration and login, endpoints require
`Authorization: Bearer <access_token>`.

| Method | Endpoint                                | Behavior                                            |
| ------ | --------------------------------------- | --------------------------------------------------- |
| GET    | `/api/health`                           | Database readiness                                  |
| POST   | `/api/auth/register`                    | `{email,password}` → private owner session (201)    |
| POST   | `/api/auth/login`                       | `{email,password}` → session                        |
| GET    | `/api/auth/me`                          | Current user, role and workspace                    |
| GET    | `/api/vehicles`, `/api/vehicles/search` | Paginated active inventory                          |
| GET    | `/api/vehicles/{id}`                    | Active vehicle details                              |
| POST   | `/api/vehicles`                         | Admin: create (201)                                 |
| PUT    | `/api/vehicles/{id}`                    | Admin: replace editable fields                      |
| DELETE | `/api/vehicles/{id}`                    | Admin: archive (204)                                |
| GET    | `/api/vehicles/archived`                | Admin: own workspace's archive                      |
| POST   | `/api/vehicles/{id}/restore`            | Admin: restore                                      |
| POST   | `/api/vehicles/{id}/purchase`           | Buy one unit; no body                               |
| POST   | `/api/vehicles/{id}/restock`            | Admin: `{quantity}`                                 |
| POST   | `/api/vehicles/import`                  | Admin: `{csv: string}` (201)                        |
| GET    | `/api/analytics`                        | Admin: dashboard; optional `start_date`, `end_date` |
| GET    | `/api/users`                            | Admin: users in the same workspace                  |
| POST   | `/api/users/{id}/promote`               | Admin: promote same-workspace member                |

Inventory responses contain `items`, `total`, `page`, `page_size`, and
`summary: {listings,units,value}`. Page size defaults to 12 and is limited to 100.
Sorts: `newest`, `price_asc`, `price_desc`, `year_desc`, `mileage_asc`. Search
combines supplied filters with AND; text is case-insensitive literal substring
matching; price and year boundaries are inclusive. See `/docs` for full schemas.

Registration requires an email and a password of 10–128 characters. Responses
never include passwords/hashes. Errors: 401 invalid session/login; 403 insufficient
workspace role; 404 missing/foreign/archived active record; 409 duplicate account,
stock conflict or already-active restore; 422 input validation; 429 auth rate limit.

## Tests and verification

```sh
cd backend
../.venv/bin/pytest --cov=app --cov-report=term-missing
cd ..
npm test --prefix frontend
npm run build --prefix frontend
python3 scripts/smoke.py
```

Backend integration tests use temporary file-backed SQLite databases. The
PostgreSQL-specific cases skip when no test database is configured; CI enforces
a 95% statement-coverage floor with both database engines exercised. To exercise
real PostgreSQL too, set `TEST_DATABASE_URL` to a disposable database before
running pytest. If local PostgreSQL tools are installed, the following command
creates/removes its own temporary cluster and runs the whole coverage suite:

```sh
.venv/bin/python scripts/test_postgres.py
```

The HTTP smoke starts its own API/Vite processes, temporary SQLite database and
random credentials. It checks two isolated registrations, 200 vehicles each,
ID/user isolation, purchases, analytics, archive and restore through the proxy.
It never uses `DATABASE_URL` inherited from your shell. Processes/data are cleaned
up afterwards; it does not modify the running local app's database.

Measured local verification for this expansion: **99 backend, migration, hosting and artifact tests passed,
including actual PostgreSQL transfer checks, with 95.88% statement coverage; 29 frontend tests and
the production build passed.** HTTP smoke passed. See the final implementation
report and [deployment verification](docs/DEPLOYMENT.md#verification) for container
and browser checks; a committed workflow is not itself evidence of remote CI.

The real Chrome harness passed 11 end-to-end checks, including separate browser
contexts, archive/restore, purchase analytics and 390px layouts. It builds and
serves its own temporary copy and retains screenshots/report under `/tmp`:

```sh
npm ci --prefix scripts/browser --ignore-scripts
npm test --prefix scripts/browser
```

This optional harness requires `/usr/bin/google-chrome`, the backend `.venv`,
and frontend dependencies. It never uses the developer's running application or
database. The only incidental error in the initial run was a missing favicon;
a local SVG favicon has since been added and verified over HTTP.

The Git history retains actual red/green development stages. Original backend:
`2c509ca` → `6ed9283`; frontend: `47ba4c7` → `f9aa401`. Portfolio workspace specifications: `f31a0a5` and
`cd6377d` before the backend green implementation `4f616fb`; frontend `5f5995d`. The default analytics
calendar-window regression is recorded as `100bd62` → `4cf7728`. Later integration
checks validate already implemented behavior and are not claimed as tests-first.
See [AGENTS.md](AGENTS.md) for the complete implementation plan and agent ownership.

## Hosting

Use [docs/VERCEL.md](docs/VERCEL.md) for the selected **Vercel Hobby + Neon Free**
deployment. The repository root uses the FastAPI preset and the checked-in build
command; hosted startup rejects SQLite fallback. See
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for container alternatives, backup/restore
and migration details. Live Chrome also verified login, loaded car photos, analytics and the 390px
mobile layout against the public site. The public production deployment is live at
[forecourt-inventory.vercel.app](https://forecourt-inventory.vercel.app), on
Vercel Hobby with the linked Neon Free database. The GitHub repository is
connected to the Vercel project. No paid plans or custom-domain purchases were
used. Free-tier quotas and cold starts still apply.

## My AI Usage

**Tool:** ChatGPT, operating as the Codex coding agent, plus explicitly requested
Codex subagents. No other AI coding tool was used in this work. The Sites skill
was consulted for UI workflow guidance; Sites hosting was not used.

**Contributions:** the coordinator translated the requirements into `AGENTS.md`,
wrote API tests, implemented authentication/workspace isolation and migrations,
integrated and reviewed changes, ran cross-database and HTTP checks, and prepared
the documentation. Subagents handled the Indian catalog/photo provenance,
analytics and PostgreSQL tests, React interface/tests, and production container,
CI and backup tooling. Agents also exercised real browser and container flows.
The work includes substantial AI-written tests and implementation, rather than
only boilerplate. Images were downloaded from attributed licensed Commons
sources; they were not AI-generated. Original fallback illustrations are SVG code.

**Transparency and reflection:** each AI-assisted commit records its contribution
and includes the ChatGPT co-author trailer. The history records failing tests
before their implementations, later regression fixes, and separate integration
checks. Parallel work accelerated the feature slices, but shared API/schema
contracts and executed tests were essential: real PostgreSQL caught a parameter
escaping incompatibility that SQLite did not expose. UI component mocks, browser
checks, HTTP smoke and container checks each verify different behavior. No claim
is made that AI-written code received an independent human review or that remote
hosting was deployed merely because local verification passed. The later
PostgreSQL cutover and Vercel release were performed explicitly and verified
against the hosted database and public HTTPS endpoints, with private backups
and migration reports retained outside the repository.
