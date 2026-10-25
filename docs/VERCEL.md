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

## Build evidence and deployment handoff

Local production Vite build succeeded and generated `public/` from `frontend/dist`:
30 byte-identical files totaling 5,764,465 bytes. All three root HTML asset
references loaded through the real FastAPI application, as did a generated
car image and SPA deep link; health and missing API/asset checks passed.
The hosting and existing production suite passed **23 tests**, including the
actual artifact check enabled with `VERIFY_VERCEL_BUILD=1`, after the initial
11 hosting tests failed before implementation.
Hosting regression tests cover URL validation before factory invocation, both
Postgres schemes, real FastAPI routes using a temporary test database, stale
asset removal, private/reserved output rejection, and native config contracts.
The regression tests use no hosted database credentials.

The real production build succeeded with Vercel CLI **65.2.0**, Node **22.22.0**,
Python **3.12**, scope `adhi-eee9`, and the prepared production environment.
The output contains the native `/fastapi` function, a 60-second duration cap,
30 CDN files, preserved request paths, and no local dotenv/database source files.
A separate smoke check materialized the actual function file map in a temporary
directory and ran it on Python **3.12.12** against the real Neon database:
health, required authentication, SPA deep links, compiled assets, unknown API
routes and missing assets passed. No API data mutations were exercised.

The only remaining build warning was:
`npm warn deprecated whatwg-encoding@3.1.1: Use @exodus/bytes instead for a more spec-conformant and faster implementation`.
The test suite also reports the existing Starlette TestClient warning that
`httpx` usage is deprecated in favor of `httpx2`. No dependency upgrade was
introduced for either warning.

The coordinator reports the local persistent PostgreSQL cutover is complete:
3 workspaces, 3 users, 605 vehicles, 723 purchases, and 1,323 inventory events;
all raw SHA comparisons and analytics for all 3 workspaces matched, and the
existing admin login was verified. The coordinator also reports 94 tests passing
with 95.86% coverage. The coordinator subsequently reports the **Neon Free**
restore complete with the same counts, SHA comparisons and analytics matches.
The runtime uses the pooled TLS URL in `iad1`. Local PostgreSQL also remains
available privately on port 55432; its
credentials remain outside Git and this guide. Transfer tooling is provided by
`backend/app/transfer.py` and `scripts/migrate_sqlite_to_postgres.py`.

The linked project is `adhi-eee9/forecourt-inventory` on personal Hobby, with
Neon Free connected and production secrets configured by the coordinator.
The coordinator owns project settings and public publishing. No deployment was
performed by the hosting agent; deployed HTTPS/CDN behavior still needs the
post-publication checks above. Do not configure the Vercel function to use the
private local PostgreSQL address.
