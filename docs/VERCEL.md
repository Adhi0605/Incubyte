# Vercel deployment

This deployment uses Vercel's native **FastAPI** framework preset, with one Python
function and a Vite frontend on the same origin. Root `app.py` exports the existing
`backend.app.main.production_app()` application. No Services beta, legacy
`builds`, extra API deployment, or SPA rewrite is required.

`vercel.json` explicitly caps the root `app.py` function at **60 seconds**.
This is within Hobby limits with or without Fluid compute. Current Fluid
compute Hobby permits 300 seconds; 60 seconds is our chosen cap, not its
current platform maximum. See [function duration configuration](https://vercel.com/docs/functions/configuring-functions/duration).

Vercel's [FastAPI documentation](https://vercel.com/docs/frameworks/backend/fastapi)
documents root `app.py`, custom build commands and CDN delivery from `public/**`.
The [configuration reference](https://vercel.com/docs/project-configuration/vercel-json)
documents the `fastapi` framework preset. Guidance checked on 2026-10-25.

## Current public release

**https://forecourt-inventory.vercel.app** is the verified production URL.
Project: `adhi-eee9/forecourt-inventory`; Vercel plan: **Hobby**. Database:
`forecourt-db`, **Neon Free**, region iad1. Managed Neon Auth is disabled because
the app retains its Argon2/JWT accounts. Production uses the pooled PostgreSQL
TLS URL; administration and transfer used the direct connection. `JWT_SECRET`
is a sensitive Vercel production secret.

The real data was migrated and verified; see [MIGRATION.md](MIGRATION.md).
Public HTTPS checks passed homepage, JS/CSS, favicon, photos, SPA deep links,
health and JSON API errors. Existing admin login and inventory were verified.
Two generated accounts then verified independent workspaces, purchase analytics,
archive and restore. Only those two UUID-named test workspaces were cleaned up;
original accounts and data were retained. Production alias requests were checked
without Vercel authentication. No paid plan or custom domain was purchased.

## Free plans and account setup

Use a personal **Vercel Hobby** project and **Neon Free** database only. Vercel
Hobby is restricted to personal, non-commercial use; this synthetic portfolio
demo is the intended use. Do not select Pro, a trial, paid database capacity,
paid add-ons, or a purchased domain. Use the provided `*.vercel.app` domain.
Free quotas can pause service, and Neon scale-to-zero can add cold-start latency.
See [Vercel Hobby](https://vercel.com/docs/plans/hobby) and
[Neon Marketplace listing](https://vercel.com/marketplace/neon).

1. Authenticate the Vercel CLI to the personal Hobby account, or import the
   repository in that account's dashboard. Set **Root Directory** to the repository
   root, **Framework Preset** to FastAPI and Node.js to **22.x**. Leave Output
   Directory unset and use the checked-in build command. The frontend's Vite 8
   build needs Node 22.12+ (local verification used Node 22.22).
2. Add Neon from Vercel Marketplace, explicitly selecting the **Free** plan.
   Connect it to this project and the required environments. Confirm the plan is
   free before provisioning. Do not reuse an existing production database.
3. Configure the secrets below in Vercel's environment settings. Complete and
   verify the coordinator's existing-data transfer before the public production
   cutover. This build script never copies, seeds, or migrates data.

## Environment variables

| Variable                        | Required value                                                                                                                                                                                                                     |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`                  | Neon PostgreSQL URL with TLS, normally the pooled connection string for runtime. Must begin with `postgres://` or `postgresql://`, with host and database name. Confirm the Marketplace integration populated this exact variable. |
| `JWT_SECRET`                    | Independently generated random secret, at least 32 characters. Set through Vercel, never commit it or put it in `VITE_*`.                                                                                                          |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Optional bootstrap pair only when deliberately creating an initial account. Omit both for registration-only operation or a transferred database. No defaults are supplied.                                                         |

Set `DATABASE_URL` and `JWT_SECRET` for **Production** and any deployed **Preview**
environment. Prefer a separate free database/branch for previews that permit
mutation. Redeploy after changing environment variables. Leave `DATABASE_PATH`
and `FRONTEND_DIST` unset on Vercel. The factory defaults to `frontend/dist`.

The Vercel entrypoint rejects missing, SQLite, and malformed database URLs
**before calling the factory**. There is no ephemeral SQLite fallback. The
existing factory owns schema initialization and seeding; cold starts invoke it.
Database migration compatibility and locking remain backend responsibilities.
The build itself does not import the application or need a database connection.
If Vercel's framework analysis imports the application, it will need the real
environment and database access; do not bypass the guard with dummy credentials.

## Build and routing

`requirements.txt` contains the same pinned dependencies as
`backend/requirements.lock`; the hosting test requires them to match. Vercel's
parser rejected a nested `-r backend/requirements.lock` include, so these pins
must be copied to root after any backend lock update. `.python-version` pins
Python **3.12**. The builder-generated root `pyproject.toml` and `uv.lock` are
local outputs, excluded from source upload, rather than maintained dependency
sources; the coordinator must also keep them Git-ignored.
Vercel installs the Python dependencies; `python scripts/build_vercel.py` runs
`npm ci --include=dev` and `npm run build` inside `frontend`, then copies the validated dist
tree into generated root `public/` and `.vercel/output/static/`. CLI 65's native
Python builder does not automatically collect this `public/` tree, so the build
script explicitly emits the standard static Build Output directory. Vercel
still generates the native FastAPI function. It retains `frontend/dist` so the existing
FastAPI factory can handle SPA routes locally and within the deployed function.
`public/` is generated output and is replaced on each build; do not hand edit it.

Vercel serves the published static files from its CDN. Requests without a static
match reach FastAPI: `/api/**` stays on the API, and extensionless frontend paths
can return the SPA. Missing API endpoints and missing asset files return 404.
There is deliberately no rewrite from every request to `index.html`, which would
turn API errors into HTML. Hashed `/assets/**` files get immutable caching;
the root/index HTML must revalidate.

Static publishing rejects symlinks, hidden paths, private file extensions, and
top-level API/OpenAPI documentation paths so static files cannot shadow those
backend endpoints. `.vercelignore` excludes local secrets, databases, backups,
dependencies and old build outputs from the source upload. Upload exclusions
alone do not protect a local prebuilt function: `functions.app.py.excludeFiles`
also excludes dotenv files, local databases, backups and installed skill files
from the native Python bundle. Both source upload and generated bundle must be
checked. New build output is created on the builder after upload.
Root `public/`, `.vercel/`, and build output
are also excluded by the repository's `.gitignore` (coordinator owned and
verified during this handoff).

## Verify and publish

Local checks, without any cloud credentials:

```sh
.venv/bin/pytest backend/tests/test_vercel.py backend/tests/test_production.py -q
.venv/bin/python scripts/build_vercel.py
```

Use Vercel CLI 48.1.8 or later. Once authenticated and linked to the intended
Hobby project, from the repository root:

```sh
npx vercel login
npx vercel link
npx vercel pull --yes --environment=production
npx vercel build --prod
npx vercel deploy --prebuilt --prod
```

The downloaded `.vercel/` environment contains secrets: keep it ignored and do
not paste its contents into logs. `vercel pull`/`build` require account and project
access; a passing Vite build alone does not prove Vercel bundling or CDN routing.
Sensitive variables can be downloaded as placeholders. The coordinator securely
prepared the local build's real JWT separately; do not pull again over that
prepared environment without restoring it. Runtime secrets remain configured
in Vercel, not in the function's source files.
After deployment, verify HTTPS `/`, a hashed `/assets/` URL, a `/cars/` image,
`/inventory/details` (SPA fallback), `/api/health`, and JSON 404s at `/api` and
`/api/not-an-endpoint`. Confirm a nonexistent asset returns 404, then check
registration/login, workspace isolation, mutation persistence across cold
starts, and transferred record counts against the actual Neon database.

## Verification evidence

The real `vercel build --prod` completed with CLI 65.2.0, Node 22.22 and pinned
Python 3.12. Output includes 30 CDN files (5,764,465 bytes), a `/fastapi` function
capped at 60 seconds in iad1, mapped SPA fallback, and no private dotenv/database
paths. The function map was materialized separately and exercised on Python 3.12
without relying on the source tree or CDN. Hosting/production checks passed
24 tests with artifact verification enabled.

The first prebuilt upload exposed collisions between upload exclusions and
native traced runtime files. Those rules were fixed while retaining secret,
database, key and backup exclusions. The next production deployment reached
READY (`dpl_A6k6mk8M3h9EDU5E7NZiLuXYzZ5t`) and received the public alias.
Vercel reports a 17.5 MB function in iad1. The public routing, login, photo,
workspace isolation, purchase analytics and archive/restore checks then passed.

The combined database, migration and hosting suite passed 95 tests with 95.88%
statement coverage before the final artifact cases were added. Artifact checks
are run separately against a real Vercel build; actual public HTTPS checks were
also performed. Upstream TestClient `httpx` and npm `whatwg-encoding` deprecation
warnings remain; no unrelated dependency upgrades were introduced.
