# Car Dealership Inventory System — implementation plan

## Scope and confirmed decisions

- Build a local, reviewable full-stack kata in this repository using FastAPI,
  file-backed SQLite, React, HTML5, CSS3, and Tailwind.
- Registration always creates a regular user. Authentication uses expiring JWTs
  and Argon2 password hashes; read current roles from the database.
- Authenticated users can list, search, and purchase vehicles. Include vehicles
  with zero stock and disable their Purchase buttons.
- Only admins can create, update, delete, or restock vehicles, list users, and
  promote other users. Enforce this in the API and hide admin controls in React.
- Bootstrap one initial admin from environment configuration. Never ship a
  default password or permit registration to select a role. Bootstrap must be
  idempotent and must not create additional admins once an admin exists.
- Each purchase reduces quantity by exactly one. Use an atomic conditional SQL
  update so concurrent requests cannot oversell. Restocking accepts a positive
  integer quantity. Store money as integer cents.
- Preserve user changes. No deployment is part of this kata; the user has
  authorized pushing commits to the established Git remote.

## Implementation sequence

1. **Backend tests first (red).** Specify registration/login, duplicate accounts,
   input validation, authentication, every admin restriction, vehicle CRUD and
   search, purchase/restock, persistence, bootstrap, promotion, and concurrency.
   Run tests before implementing and commit the failing specification.
2. **Backend implementation (green).** Separate schemas, database access, and
   API setup. Implement the required REST endpoints, plus `GET /api/auth/me`,
   `GET /api/users`, and `POST /api/users/{id}/promote`. Run integration tests
   against temporary file-backed databases and commit the passing implementation.
3. **Frontend tests first (red).** Specify out-of-stock purchase disabling,
   purchase callbacks/pending states, and admin-only management controls. Run
   before implementation and commit the failing tests.
4. **Frontend implementation (green).** Implement registration/login, session
   recovery and logout, responsive inventory cards, search by all required
   fields, price filters, purchase confirmation, admin CRUD/restock forms, and
   user promotion. Include loading, empty, failure, and success states, labels,
   keyboard-accessible dialogs, and protection against repeated submissions.
   Run frontend tests and a production build before committing.
5. **Review and refactor.** Inspect edge cases, validation consistency, money
   precision, stale requests/session changes, and all permission checks. For
   discovered behavior defects, add a failing regression test, run it, fix it,
   and commit with the evidence. Refactor only after tests pass.
6. **Reproducibility and handoff.** Add safe environment examples, setup/run/test
   instructions, optional sample inventory, dependency locks, CI checks, an API
   summary, and the required detailed `My AI Usage` README section. Preserve the
   existing README content. Verify a clean installation/build path and report
   actual test/coverage results and any verification limits.

## Verification commands

From the repository root:

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock
cd backend
../.venv/bin/pytest --cov=app --cov-report=term-missing
cd ..
npm ci --prefix frontend
npm test --prefix frontend
npm run build --prefix frontend
npm audit --prefix frontend
python3 scripts/smoke.py
```

Run the API using `uvicorn app.main:production_app --factory` from `backend`
with the documented environment variables, and the SPA using
`npm run dev --prefix frontend`. Verify representative HTTP responses. Use a
browser for interactive QA if browser tooling is available; otherwise explicitly
report that browser layout and end-to-end behavior were not verified.

## Development and commit rules

- Keep meaningful red/green/refactor history; do not fabricate earlier TDD work.
- Every AI-assisted commit must explain the contribution and end with an AI
  co-author trailer separated from the body by two empty lines:
  `Co-authored-by: ChatGPT <chatgpt@users.noreply.github.com>`.
- Never commit credentials, local databases, virtual environments, dependencies,
  build output, or coverage artifacts. Use placeholders in examples.
- Prefer tests of observable API/UI behavior over tests mirroring internals.
- Keep this plan's progress section accurate as work completes. Do not call
  unrun checks passing or imply a deployment occurred.

## Progress

- [x] Backend red specification committed (`2c509ca`).
- [x] Backend green implementation committed (`6ed9283`); 19 tests passed.
- [x] Frontend red specification committed (`47ba4c7`).
- [x] Frontend implementation written and verified.
- [x] Frontend tests (8) and production build pass.
- [x] Review and regression fixes complete: bootstrap and stock-limit red/green
      commits `704e76b` / `5c6c349`. Extracted authentication and reusable UI
      components and formatted the frontend for readability.
- [x] Documentation, environment example, idempotent sample data, dependency
      locks, and CI workflow implemented. Seed red/green: `30cf58f` / `fec3fae`.
- [x] Final verification: 25 backend tests, 97.64% statement coverage, 8 frontend
      tests, production build, dependency checks, and real HTTP smoke passed.
      Browser layout/end-to-end QA unavailable; GitHub CI has not run remotely.

## Soft deletion and restore extension

Confirmed: deletion archives a vehicle in its existing row using a UTC
`deleted_at` timestamp. Admins alone can view archived vehicles and restore them.
Archived vehicles must be absent from listings/search/statistics and cannot be
purchased, edited, or restocked. Restore preserves the original ID and stock.
Existing on-disk databases must migrate automatically without losing data.

1. [x] Write/run failing API tests for archive persistence, authorization,
       forbidden archived mutations, restore conflicts, concurrency, and legacy DB migration.
2. [x] Write/run failing React tests for admin-only archive navigation, restore
       confirmation, failure handling, and absence of purchase/edit/restock controls.
3. [x] Implement an additive SQLite migration, soft DELETE, admin-only
       `GET /api/vehicles/archived` and `POST /api/vehicles/{id}/restore`, with atomic
       predicates protecting archived rows from inventory operations.
4. [x] Add the admin archive screen and Restore action; update delete confirmation
       to explain recovery. Update API documentation and HTTP smoke coverage.
5. [x] Run backend coverage, UI tests, production build, and HTTP smoke; restart
       the running API to apply the migration, verify local service readiness, commit
       with AI attribution, and push to the established remote as previously requested.

Soft-delete verification: 31 backend tests, 97.81% statement coverage, 12 frontend
tests, production build, and real HTTP smoke passed. The local API was restarted
and the existing admin login plus active/archive endpoints were verified through
the frontend proxy. Browser layout testing remains unavailable.

## Portfolio expansion: automatic private workspaces (active plan)

This section supersedes the original registration rule for this portfolio mode.
The app will still look and behave like a normal dealership application. There
will be no "Start my demo" gate, automatic resets, or shared editable inventory.

### What will work and how

1. **Automatic isolation.** Registration creates an owner-admin and a private
   workspace in the same transaction, populated with Indian sample inventory and
   synthetic history. Login returns that workspace's session. Every inventory,
   archive, restore, purchase, user, and analytics query is restricted by the
   workspace from the authenticated database user, never a client-supplied ID.
   Existing accounts keep working; existing inventory is retained in the legacy
   workspace. Subsequent independent registrations cannot promote/access users
   in other workspaces. Workspace roles remain separate from global access.
2. **Indian new/used inventory.** Create 200 deterministic synthetic listings,
   with year, condition (`new`/`used`), trim, mileage in km, fuel, transmission,
   colour, city, description, INR price, timestamps, stock number and optional
   VIN. Each used listing represents one car (quantity 0 or 1). Add database
   pagination, sorting, filters, a detail endpoint, and bulk CSV import. Prices,
   inventory and histories are explicitly synthetic and are not market quotes.
3. **Images and information.** Listings have gallery image objects (`url`,
   `alt`, `credit`, `source_url`, `license`) plus an HTTPS manufacturer/model
   information link. Use shared local licensed/attributed car photographs where
   obtainable, labeled representative imagery. Never claim a photograph is of
   the physical synthetic listing. Provide a fallback and lazy loading. Vehicle
   details show gallery, full specifications, source credit and external link.
4. **Transactional history and analytics.** Every purchase atomically decreases
   stock by exactly one and inserts a durable purchase snapshot with the price
   at purchase time. Inventory events record restocks, quantity adjustments,
   archives and restores. Seed 12 months of labeled synthetic transactions per
   workspace. Admin dashboard includes date-filtered recorded sales, units sold,
   average sale price, inventory value, new/used and fuel/brand breakdowns,
   monthly trends, low stock and aging stock. Historical records survive edits
   and archiving. No payments or real revenue are implied.
5. **Normal interface.** Keep login/registration; explain private persistent
   data briefly on registration. Add Inventory / Analytics / Archived vehicles
   navigation, INR/lakh/crore formatting, rich search with server pagination,
   detail/gallery screen and expanded vehicle forms. A user immediately has
   admin capabilities in their own automatically created workspace.
6. **Hosting.** Provide a reproducible production container that builds React
   and serves it alongside `/api` from FastAPI, a health endpoint, environment
   configuration, and a Render blueprint. Keep SQLite supported for local use
   and a persistent-disk single-instance demo; add PostgreSQL support for a
   managed production database where practical. Include backups/migration and
   secret instructions; never provision paid services or publish without the
   actual host/account configuration. The deliverable is hosting-ready code.
7. **Verification and delivery.** Write failing tests before changes, commit
   meaningful red/green/refactor stages with AI attribution, verify isolation
   for every endpoint with two users, test pagination and filters, transaction
   atomicity, used-stock limits, image/link validation, legacy migration and
   analytics. Run frontend tests/build and actual HTTP smoke. Update README and
   plan with measured outcomes. Restart the local app and push the completed
   work to the established remote. No browser verification claim without a run.

### Parallel ownership and shared contracts

The coordinator owns `backend/app/database.py`, `main.py`, `schemas.py`, workspace
provisioning/auth, endpoint integration and cross-workspace regression tests.
Agents edit only assigned paths and do not commit, push or edit this plan.

- **Catalog agent:** `backend/app/catalog.py`, `backend/app/demo.py`,
  `backend/tests/test_catalog.py`, `frontend/public/cars/`, `ASSET_CREDITS.md`.
  Export `catalog_vehicles()` -> list of 200 dictionaries. Dictionaries use
  vehicle input fields and `images` metadata. Export
  `populate_workspace(db, workspace_id)` from demo.py, inserting vehicles,
  purchases and events inside the caller's transaction, no own commits.
- **Analytics agent:** `backend/app/analytics.py`,
  `backend/tests/test_analytics.py`. Export `workspace_analytics(db,
workspace_id, start_date=None, end_date=None)`. SQL connection provides
  `execute(sql, tuple_params)` and dictionary-like rows. Use tables below.
- **Frontend agent:** all `frontend/src/` except existing CarArt and assets;
  own frontend tests; coordinate against contracts below. No backend edits.
- **Hosting agent:** `Dockerfile`, `.dockerignore`, `render.yaml`,
  `compose.yaml`, `.github/workflows/ci.yml`, `docs/DEPLOYMENT.md` and
  `scripts/backup.py`. Do not edit main.py; specify required static integration.

Database contract: `workspaces(id,name,created_at)`,
`users(...,workspace_id)`, `vehicles(...,workspace_id,condition,year,trim,
 mileage_km,fuel_type,transmission,color,city,description,info_url,images_json,
 stock_number,vin,created_at,updated_at)`. All money columns remain integer
`price_cents` (INR paise). `purchases(id,workspace_id,vehicle_id,make,model,
 condition,fuel_type,quantity,unit_price_cents,total_cents,purchased_at,is_demo)`;
`inventory_events(id,workspace_id,vehicle_id,event_type,quantity_delta,
 created_at,is_demo)`. SQL uses `?` parameters, common SQLite/Postgres syntax,
`INSERT ... RETURNING id`; timestamps are UTC ISO text, booleans integer 0/1.

API contract:

- Auth sessions retain `{access_token,token_type,user}`; user includes
  `workspace_id`. Registration produces `role: admin` for its own new workspace.
- `GET /api/vehicles` and `/search`: return `{items,total,page,page_size,
summary:{listings,units,value}}`; pagination defaults page=1,page_size=12,
  maximum 100. Filters: make,model,category,condition,fuel_type,transmission,
  city,min_price,max_price,min_year,max_year. Sort: newest,price_asc,price_desc,
  year_desc,mileage_asc. Summary covers all matches, excluding archived rows.
- `GET /api/vehicles/{id}` returns expanded vehicle, with `images` parsed from
  JSON, `currency: INR`, and optional timestamp `deleted_at`.
- Existing mutation routes keep their methods. Archived endpoint remains an
  admin-only array. Purchase/restock/restore return the expanded vehicle.
- `GET /api/analytics?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`: admin-only
  returns `summary` (recorded_sales,units_sold,average_sale_price,inventory_value,
  inventory_units,active_listings), `monthly_sales` [{month,sales,units}],
  `by_brand` [{name,sales,units}], `by_condition` [{name,sales,units}],
  `by_fuel` [{name,units}], `low_stock` and `aging_stock` vehicle summaries,
  and `demo_notice`. Money values are decimal strings in INR. Sales date bounds
  are inclusive; inventory statistics describe current active inventory.
- `POST /api/vehicles/import`: admin-only `{csv: string}`, validates all rows
  before inserting, returns `{imported: number}`. Image gallery editing may
  accept HTTPS URLs; locally seeded images use `/cars/...`.
- `GET /api/health` returns `{status: ok}`. Production fallback serves React
  routes, never masks missing `/api` endpoints with HTML.

### Expansion progress

- [x] Requirements, sequencing, ownership and contracts documented before work.
- [x] Failing isolation/rich-inventory/analytics tests recorded (`f31a0a5`,
      `cd6377d`); subagents supplied their red-run evidence.
- [x] Workspace migration and automatic owner provisioning implemented, retaining
      legacy rows and preventing cross-workspace reads/writes/promotions.
- [x] Indian catalog: 200 listings, 25 attributed local photos, 241 synthetic
      purchases over 12 months, no automatic resets.
- [x] Scoped inventory, atomic purchase snapshots, CSV import and analytics
      integrated; SQLite plus real PostgreSQL integration suite passes.
- [x] Frontend inventory/details/gallery/forms/import and analytics integrated:
      29 component/integration tests and production build pass.
- [x] Hosting artifacts and production serving verified with Podman build,
      HTTP, private registration, replacement persistence and live backup checks.
- [x] Browser artifacts reviewed: 11 real Chrome checks, including 390px layouts,
      isolated accounts, purchase analytics and archive/restore.
- [x] Final local restart and existing-account/photo/API checks passed.
- [x] Documentation and all changes prepared for the final GitHub push.

### Coordination and verification record

Four subagents implemented disjoint catalog/assets, analytics/tests, frontend,
and hosting slices. The catalog agent then supplied a reusable real-browser
harness. The coordinator owned schema/auth/scoping, reviewed/integrated all
changes, ran actual PostgreSQL and HTTP smoke, and retained TDD commits.

Live integration exposed a 13th empty chart month. A failing regression was
committed (`100bd62`), followed by the calendar-window correction (`4cf7728`).
Existing local SQLite data was backed up privately before migration; the old
account's inventory and login were retained. No hosted service was provisioned.
The single-origin production container is ready for deployment using the
separate deployment guide; local verification does not imply remote deployment.

Final measured verification: 71 backend tests including four actual PostgreSQL
integration tests, 96.05% backend statement coverage, 29 frontend tests, browser
QA and HTTP smoke. The production image was built and smoke-tested locally;
remote hosting and remote CI are separate actions/results.
