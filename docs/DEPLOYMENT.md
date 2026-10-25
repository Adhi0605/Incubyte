# Production deployment

These artifacts prepare the repository for hosting. They do not provision or
publish anything. Review the selected plans, storage, region and current account
terms before applying the Render blueprint. No availability, pricing or backup
retention guarantee is implied.

## Runtime and integration contract

The multistage Dockerfile builds React with Node 22, installs the locked Python
dependencies with Python 3.13, and runs a single non-root Uvicorn worker. The
runtime serves the built React files and `/api` from the same origin; Node and
Vite are not runtime services. Static assets are read-only application files.
The SQLite Compose service additionally uses a read-only root filesystem.

The backend coordinator owns these required interfaces:

- `app.main:production_app` is a Uvicorn factory. Startup initializes/migrates
  the selected database and validates configuration before accepting requests.
- `FRONTEND_DIST` selects the React build. `/` and frontend routes serve its
  `index.html`; asset requests serve the built files. Missing `/api` paths stay
  JSON 404 responses, and fallback paths must remain inside the static directory.
- `GET /api/health` performs `SELECT 1` and returns `{"status":"ok"}` when ready.
- `Database` supports `postgres://` and `postgresql://` through
  `psycopg[binary]` version 3, included in `backend/requirements.lock`. SQLite
  remains supported through `DATABASE_PATH`.
- Registration creates a private, seeded workspace owned by its new admin.
  Initial administrator bootstrap is optional.

| Environment variable | Purpose |
| --- | --- |
| `JWT_SECRET` | Required private random value, at least 32 characters. Keep stable across restarts; rotating it invalidates existing tokens. |
| `DATABASE_URL` | PostgreSQL connection URL. Nonempty value takes precedence over `DATABASE_PATH`. Keep it private; use the host's internal URL on Render. |
| `DATABASE_PATH` | SQLite fallback. Container default `/data/inventory.db`; local backend default `backend/inventory.db`. Its directory must exist and be writable. |
| `FRONTEND_DIST` | Absolute built React directory; container default `/app/frontend/dist`. |
| `PORT` | Listening port, default `8000`; the container honors a hosting platform's supplied value. |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Optional private first-admin bootstrap. Supply both or neither; supplying only one fails startup. No default credentials. Bootstrap is idempotent and does not replace an existing admin's password. |
| `TEST_DATABASE_URL` | Tests only: opt into PostgreSQL integration checks against a disposable database. Never point this at production. |

Do not put secrets into the Dockerfile, frontend build variables, committed YAML,
or command logs. The build context excludes environment files and local databases.
Store production values in the host's secret configuration. Remove bootstrap
values after first use; normal registration needs neither value.

## Render with managed PostgreSQL

`render.yaml` defines one Docker web service and a managed PostgreSQL database
in the same region, linked through the database's private `connectionString`.
The web service has no SQLite disk requirement. `ipAllowList: []` restricts the
database to internal access. Automatic deploys are disabled in the blueprint.

When ready to host, connect the intended repository/account and review the
blueprint in Render before applying it. Render generates `JWT_SECRET` through
`generateValue: true`. The optional `ADMIN_EMAIL` and `ADMIN_PASSWORD` entries
use `sync: false`: supply them privately as a pair, or leave both absent/empty
and register normally. Render prompts for these entries at initial blueprint
creation; later changes must be made in the service's environment settings.
If the creation UI requires values for optional entries, remove both bootstrap
entries from your deployment copy of the blueprint.

The Dockerfile command is the production start command; no extra development
server or seed command is needed. Verify `/api/health`, `/`, a frontend route,
an asset and an unknown `/api` URL after deployment. Check private registration
and data persistence after restarting the service.

See Render's [blueprint reference](https://render.com/docs/blueprint-spec) and
[environment variable documentation](https://render.com/docs/configure-environment-variables)
for the configuration fields and secret lifecycle.

## Persistent SQLite with Docker Compose

Run from the repository root with Docker Engine and Compose v2. Generate a
secret into a private, ignored `.env` file; preserve it between invocations:

```sh
umask 077
python3 -c 'import secrets; print("JWT_SECRET=" + secrets.token_hex(32))' > .env
docker compose config --quiet
docker compose up --build -d
curl --fail http://127.0.0.1:8000/api/health
```

Create `.env` only on the first setup; overwriting it rotates the signing key.
Optional bootstrap variables may be added privately as a pair. Otherwise open
`http://127.0.0.1:8000` and register. `APP_PORT` changes the host port. Compose
deliberately sets `DATABASE_URL` empty to select SQLite.

The `inventory-data` named volume persists `/data` across container replacement
and `docker compose down`. `docker compose down --volumes` deletes it. Keep one
app instance/worker for this SQLite alternative. The port binds to loopback;
for public hosting, configure an HTTPS reverse proxy and its network access.
Do not put SQLite on a shared network filesystem or scale it across hosts.

```sh
docker compose logs --tail=100 app
docker compose up --build -d       # rebuild/recreate, retaining the named volume
docker compose stop app
docker compose start app
```

For a standalone container, use an equivalent persistent `/data` volume and
inject secrets from your environment. It runs as UID/GID `10001`; bind mounts
must be writable by that identity. The Docker health check uses `/api/health`
and the configured `PORT` without requiring curl.

## Schema migrations and upgrades

Take and verify a backup before an upgrade. Database initialization applies
additive schema migrations at application startup, including legacy SQLite
inventory retention in its legacy workspace. Image rebuilds do not move data
between database engines. For a controlled migration-only pass while the
Compose service is stopped:

```sh
docker compose stop app
docker compose run --rm --no-deps app python -c 'import os; from app.database import Database; Database(os.environ.get("DATABASE_URL") or os.environ["DATABASE_PATH"])'
docker compose up -d
```

For PostgreSQL, the equivalent initialization command in the application image
with its configured environment is:

```sh
python -c 'import os; from app.database import Database; Database(os.environ["DATABASE_URL"])'
```

Run schema changes once before accepting traffic, then verify health,
registration/login, workspace isolation, inventory and purchase history. Keep
the previous image/revision and its matching backup for rollback; a code
rollback alone does not undo database changes.

There is no automatic SQLite-to-PostgreSQL data importer. A fresh PostgreSQL URL
starts a separate database. To retain existing data, first take a SQLite backup,
stop writes, and validate an explicit transfer in staging: preserve workspace
and row IDs, password hashes, integer money, JSON and timestamps across
workspaces, users, vehicles, purchases and inventory events; reset PostgreSQL
sequences after loading IDs. Compare per-workspace counts, roles, stock and
historical totals before switching `DATABASE_URL`. Keep the source until the
transfer and restore have been verified. A SQLite `.dump` is not a PostgreSQL
migration script.

## SQLite backups and restore

`scripts/backup.py` uses the standard-library
[SQLite backup API](https://docs.python.org/3.13/library/sqlite3.html#sqlite3.Connection.backup)
to include committed WAL contents while the app is running. It opens an
existing source read-only, writes a private temporary file, checks integrity
and atomically publishes a standalone snapshot. It refuses to overwrite a
destination and never creates a missing source. A deadline limits retries
under sustained write contention. Retry a timed-out backup during quieter use.

```sh
python3 scripts/backup.py --source backend/inventory.db /secure/backups/inventory-2026-10-25.db
# DATABASE_PATH is used when --source is omitted.
```

For Compose, create the snapshot inside the volume and copy it out. Choose a
new filename for every backup; the following names are examples:

```sh
umask 077
mkdir -p backups
docker compose exec -T app python /app/scripts/backup.py /data/inventory-2026-10-25.db
docker compose cp app:/data/inventory-2026-10-25.db backups/inventory-2026-10-25.db
chmod 600 backups/inventory-2026-10-25.db
```

Copy verified snapshots to protected storage on a different host and establish
retention/scheduling appropriate to your data. Backups contain private accounts
and workspace data; keep them out of Git and the frontend. Raw copies of a live
SQLite main file can miss WAL transactions. When `DATABASE_URL` is set, the
script refuses implicit SQLite selection; use PostgreSQL tools instead.

To restore, preserve a current backup first, then stop all application writers.
This example replaces the Compose database with the selected verified snapshot:

```sh
docker compose stop app
docker compose run --rm --no-deps -v "$PWD/backups:/restore:ro" app python /app/scripts/backup.py --source /restore/inventory-2026-10-25.db /data/restore.db
docker compose run --rm --no-deps app python -c 'import os; from pathlib import Path; p = Path("/data/inventory.db"); [Path(str(p) + suffix).unlink(missing_ok=True) for suffix in ("-wal", "-shm", "-journal")]; os.replace("/data/restore.db", p)'
docker compose up -d
curl --fail http://127.0.0.1:8000/api/health
```

Keep the signing key if existing sessions should continue working. Verify login,
workspace ownership, stock, archived listings and recorded purchases after any
restore. Test recovery in an isolated environment regularly.

## PostgreSQL backups and restore

Use PostgreSQL client tools compatible with the server version from a trusted
environment with database network access. The app image does not bundle these
administrative tools. Keep connection URLs in private environment variables:

```sh
umask 077
pg_dump --dbname="$DATABASE_URL" --format=custom --no-owner --no-acl --file=inventory.dump
pg_restore --list inventory.dump
# RESTORE_DATABASE_URL must point at a separate, empty recovery database.
pg_restore --exit-on-error --no-owner --no-acl --dbname="$RESTORE_DATABASE_URL" inventory.dump
```

Listing a dump is not a restore test. Start the matching application revision
against the recovery database and verify data and permissions before switching
traffic. Review host-managed backup/restore settings in your actual account;
this repository does not configure or promise their retention.

## Verification

```sh
(cd backend && ../.venv/bin/pytest --cov=app --cov-report=term-missing)
npm test --prefix frontend
npm run build --prefix frontend
docker compose config --quiet
docker build --tag forecourt:check .
```

For opt-in PostgreSQL checks set `TEST_DATABASE_URL` to a disposable
database and run the same backend suite. CI provisions a temporary PostgreSQL
test service, runs backend coverage and frontend tests/build, then tests the
production container with SQLite and PostgreSQL: health, HTML, a built JS asset,
frontend fallback, API 404s, registration and restart persistence. CI creates
disposable secrets; it does not need deployment credentials or deploy the app.

Podman can also build the image with its Docker health check preserved:

```sh
podman build --format docker --tag forecourt-portfolio .
```

Only a completed build and smoke run count as container verification. Remote
GitHub/Render results require an actual run.

Local authoring verification on 2026-10-25: the Podman production build succeeded
with locked psycopg 3.3.6. HTTP smoke verified health, static assets, frontend
fallback, API 404s, two isolated seeded registrations, non-root execution,
read-only assets, the image health check and a live SQLite backup. Sessions and
inventory survived container replacement using the same volume. Direct Podman
restart hit a host-port bind error, so replacement was used for persistence
verification. Render, Compose and workflow schemas validated; no Compose
provider was installed for an actual Compose run. No hosted service or remote
CI run was performed.

Final coordinated test results: 71 backend tests passed, including four actual
PostgreSQL integration tests, with 96.05% backend coverage; 29 frontend tests
passed. The default twelve-month and end-date-only analytics regression checks
passed. The locking-fix commit records the same 71-test, 96.05% backend result.
Backend revision: `ff8ba09`; frontend app revision: `5f5995d`, plus the final
favicon asset and index link. The coordinator's final browser QA passed 11 checks.

The final cached production rebuild produced `forecourt-portfolio` with image ID
`d91755e153c5cbeb3d050d6e7ac7de85b77b9eb7ba5a293607c47de0f60d6e03`.
This rebuild includes the PostgreSQL row lock before reading an admin edit's
previous quantity and the final favicon. Its `backend/app/main.py` SHA-256
matched the current workspace:
`4a18897bff87de2b9523bcc9397db0ea659dd0da820963c3d0ab686bece8badb`.

Focused smoke on this final image passed root HTML, its favicon link and SVG,
`/api/health`, private registration and authenticated `/api/analytics`, returning
exactly twelve monthly buckets. The owned smoke container and temporary database
volume were removed. Broader isolation, backup and replacement-persistence
checks are the earlier production smoke results described above.
