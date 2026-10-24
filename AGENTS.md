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
- Preserve user changes. No publishing or remote push is part of this kata.

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

- [x] Backend red specification committed (`a170080`).
- [x] Backend green implementation committed (`a78a04f`); 19 tests passed.
- [x] Frontend red specification committed (`438ff30`).
- [x] Frontend implementation written and verified.
- [x] Frontend tests (8) and production build pass.
- [x] Review and regression fixes complete: bootstrap and stock-limit red/green
      commits `36d7fab` / `235333b`. Extracted authentication and reusable UI
      components and formatted the frontend for readability.
- [x] Documentation, environment example, idempotent sample data, dependency
      locks, and CI workflow implemented. Seed red/green: `c9373d8` / `051450b`.
- [x] Final verification: 25 backend tests, 97.64% statement coverage, 8 frontend
      tests, production build, dependency checks, and real HTTP smoke passed.
      Browser layout/end-to-end QA unavailable; GitHub CI has not run remotely.

## Soft deletion and restore extension

Confirmed: deletion archives a vehicle in its existing row using a UTC
`deleted_at` timestamp. Admins alone can view archived vehicles and restore them.
Archived vehicles must be absent from listings/search/statistics and cannot be
purchased, edited, or restocked. Restore preserves the original ID and stock.
Existing on-disk databases must migrate automatically without losing data.

1. [ ] Write/run failing API tests for archive persistence, authorization,
   forbidden archived mutations, restore conflicts, concurrency, and legacy DB migration.
2. [ ] Write/run failing React tests for admin-only archive navigation, restore
   confirmation, failure handling, and absence of purchase/edit/restock controls.
3. [ ] Implement an additive SQLite migration, soft DELETE, admin-only
   `GET /api/vehicles/archived` and `POST /api/vehicles/{id}/restore`, with atomic
   predicates protecting archived rows from inventory operations.
4. [ ] Add the admin archive screen and Restore action; update delete confirmation
   to explain recovery. Update API documentation and HTTP smoke coverage.
5. [ ] Run backend coverage, UI tests, production build, and HTTP smoke; restart
   the running API to apply the migration, verify local service readiness, commit
   with AI attribution, and push to the established remote as previously requested.
