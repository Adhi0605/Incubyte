# SQLite to PostgreSQL migration

## Completed PostgreSQL and hosted Neon cutover

On 2026-10-25 the running app's existing SQLite data was transferred to persistent
PostgreSQL, and the private `backend/.env` was switched to `DATABASE_URL`.
The original SQLite application writer was stopped before the snapshot. The
verified PostgreSQL database was subsequently transferred to **Neon Free in
region iad1**, using a fresh transactional dump/restore and the direct TLS
connection. Every table and all workspace analytics were compared again. The
running app now selects Neon’s pooled TLS connection, matching the hosted
Vercel production configuration.

| Table            | Verified records |
| ---------------- | ---------------: |
| workspaces       |                3 |
| users            |                3 |
| vehicles         |              605 |
| purchases        |              723 |
| inventory_events |            1,323 |

Every table passed a SHA-256 comparison of its complete ordered records. Both
engines produced identical analytics for all three workspaces. Accounts, hashes,
IDs, archive timestamps, image JSON, exact integer money and historical sales
were retained. Existing admin login, inventory, archive, and twelve-month
analytics were verified through the running frontend's API proxy after cutover.

The dedicated local database is `forecourt`, accessed by a non-superuser
application role. PostgreSQL uses SCRAM authentication, loopback-only access,
and storage outside the repository. A user service keeps it running:

```sh
systemctl --user status forecourt-postgres.service
systemctl --user restart forecourt-postgres.service
```

Its service starts with the user's systemd session. It is retained as a private
local rollback copy. The active runtime now uses hosted Neon rather than this
loopback instance; the laptop database is never exposed to Vercel.
Project DB credentials, SQLite snapshots, row-verification reports, and the
post-migration PostgreSQL dump are private files outside Git. Native service
configuration is machine-local, not a cloud deployment artifact.

## Transfer another SQLite database

Prepare an empty PostgreSQL database whose role can create its schema. Set the
real URL privately in `DATABASE_URL` or another environment variable. Do not
paste passwords into commands, commit them, or publish them in a report.
Install the locked dependencies first, and stop all source application writers.

```sh
# Create a verified SQLite snapshot (choose a new destination).
python3 scripts/backup.py --source backend/inventory.db /private/backups/before-postgres.db

# DATABASE_URL must point at the EMPTY target.
.venv/bin/python scripts/migrate_sqlite_to_postgres.py \
  --source /private/backups/before-postgres.db \
  --report /private/backups/postgres-verification.json
```

The utility snapshots the source read-only, checks SQLite integrity/foreign
keys, initializes the target schema, locks the target tables, and copies the
records in one transaction. It verifies complete ordered row hashes and
per-workspace analytics before committing, then repairs PostgreSQL identity
sequences so future registrations and purchases do not collide with imported
IDs. Source and target schemas must match; upgrade legacy schemas with the app
before transferring. The only replaceable target row is the app's unused default
workspace; real populated targets are never overwritten.

An exactly matching target returns `already_verified` without duplicating rows.
A populated, different target is refused. Insert/verification failures roll back
the copied data. Connection errors are summarized without exposing connection
secrets. The optional JSON report is created with mode 0600 and is never
overwritten. It contains counts/hashes, not password hashes or connection URLs.

Configure the runtime to use the verified target URL, retaining the existing
`JWT_SECRET` if existing tokens should remain valid. Restart the app, verify
health, existing login, workspace isolation and historical totals, then resume
writes. A URL change alone does not migrate any records.

## Subsequent transfer to hosted PostgreSQL

Once the live source is PostgreSQL, use a fresh PostgreSQL dump and restore into
an empty hosted target instead of the older SQLite snapshot. Freeze writes for
the final snapshot, and use PostgreSQL client tools compatible with the servers.
Connection settings belong in private environment variables.

```sh
# PGHOST, PGPORT, PGUSER, PGPASSWORD and PGDATABASE select the source privately.
umask 077
pg_dump --format=custom --no-owner --no-acl --file=/private/backups/hosted-cutover.dump
pg_restore --list /private/backups/hosted-cutover.dump
# Configure the same PG* variables for the EMPTY hosted target, with TLS.
pg_restore --exit-on-error --single-transaction --no-owner --no-acl \
  --dbname="$PGDATABASE" /private/backups/hosted-cutover.dump
```

Do not restore into an initialized/mutated target or use destructive clean flags.
Compare every table and workspace analytics with the frozen source before
pointing Vercel at the hosted database. Use the host's direct connection for
administration/migration and its pooled TLS URL for the runtime when recommended.
Never put a laptop's localhost connection string in Vercel.

## Rollback

Keep the source database and signing key until the target and its backup have
been verified. Before switching back, stop app writes and snapshot the current
PostgreSQL database. Returning to the pre-migration SQLite snapshot discards
later PostgreSQL-only changes unless those changes are explicitly transferred;
there is no automatic reverse sync. Restore the old private environment without
`DATABASE_URL` only if that data-loss implication is acceptable. Verify accounts,
stock, archives and purchase totals before accepting writes again.

## Verification

```sh
.venv/bin/python scripts/test_postgres.py
```

The migration checks run against their own isolated PostgreSQL schemas. They
cover exact records/passwords/sessions, archive/history retention, scoped
analytics, refusal of populated targets, idempotent verification, post-import
identity sequences, rollback on an injected insert failure and safe error output.
The test script creates and removes a temporary PostgreSQL cluster; it never
uses the running local database or the hosted production database.
