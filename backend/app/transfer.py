"""Verified, non-destructive SQLite to PostgreSQL transfer.

Stop application writes for the final cutover. The source is always read-only;
this tool snapshots it to a temporary file and never overwrites a populated target.
"""
import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import time

from .analytics import workspace_analytics
from .database import Database

TABLES = ('workspaces', 'users', 'vehicles', 'purchases', 'inventory_events')


class MigrationError(ValueError):
    """A safe, credential-free error that may be displayed by the CLI."""


def _snapshot(source, destination):
    deadline = time.monotonic() + 60
    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise MigrationError('SQLite snapshot timed out; stop writes and retry')
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as original:
        with closing(sqlite3.connect(destination)) as snapshot:
            original.backup(snapshot, pages=256, progress=progress)
            if snapshot.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise MigrationError('SQLite integrity verification failed')
            if snapshot.execute('PRAGMA foreign_key_check').fetchone():
                raise MigrationError('SQLite contains invalid foreign-key references')


def _read_rows(db, table):
    return [dict(row) for row in db.execute(f'SELECT * FROM {table} ORDER BY id')]


def _signature(rows):
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode())
        digest.update(b'\n')
    return {'rows': len(rows), 'sha256': digest.hexdigest()}


def _analytics(db, workspaces):
    return {str(row['id']): workspace_analytics(db, row['id']) for row in workspaces}


def migrate_sqlite_to_postgres(source, target_url):
    """Copy all records atomically; verify raw rows and per-workspace analytics.

    ``DATABASE_URL``/credentials are never included in the returned report.
    A matching target is verified idempotently; a different nonempty target is
    refused. Source IDs/password hashes/JSON/timestamps are preserved verbatim.
    """
    if not target_url.startswith(('postgresql://', 'postgres://')):
        raise MigrationError('The target must be a PostgreSQL connection URL')
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise MigrationError('The SQLite source file does not exist')
    with tempfile.TemporaryDirectory(prefix='forecourt-transfer-') as directory:
        snapshot_path = Path(directory) / 'snapshot.db'
        _snapshot(source, snapshot_path)
        with closing(sqlite3.connect(snapshot_path)) as snapshot:
            snapshot.row_factory = sqlite3.Row
            try:
                rows = {table: _read_rows(snapshot, table) for table in TABLES}
                signatures = {table: _signature(values) for table, values in rows.items()}
                expected_analytics = _analytics(snapshot, rows['workspaces'])
            except sqlite3.Error as exc:
                raise MigrationError('Source schema is incomplete; upgrade it before transferring') from exc
            try:
                database = Database(target_url)
            except Exception as exc:
                raise MigrationError('Could not initialize PostgreSQL target; no application data was copied') from exc
            try:
                with database.connect() as target:
                    target.execute('BEGIN IMMEDIATE')
                    target.execute('LOCK TABLE ' + ','.join(TABLES) + ' IN ACCESS EXCLUSIVE MODE')
                    existing = {table: _read_rows(target, table) for table in TABLES}
                    existing_signatures = {table: _signature(values) for table, values in existing.items()}
                    if existing_signatures == signatures:
                        if _analytics(target, rows['workspaces']) != expected_analytics:
                            raise MigrationError('Existing target analytics do not match the source')
                        return {'status': 'already_verified', 'tables': signatures, 'analytics_verified': len(expected_analytics)}
                    nonempty = any(existing[table] for table in TABLES if table != 'workspaces')
                    workspaces = existing['workspaces']
                    placeholder = (len(workspaces) == 1 and workspaces[0]['id'] == 1
                                   and workspaces[0]['name'] == 'My dealership'
                                   and workspaces[0]['demo_seeded'] == 0)
                    if nonempty or (workspaces and not placeholder):
                        raise MigrationError('The PostgreSQL target is not empty; no records were replaced')
                    # Validate schemas before touching even the empty default workspace.
                    columns = {}
                    for table in TABLES:
                        columns[table] = [column[0] for column in snapshot.execute(f'SELECT * FROM {table} LIMIT 0').description]
                        target_columns = {column.name for column in target.execute(f'SELECT * FROM {table} LIMIT 0').description}
                        if set(columns[table]) != target_columns:
                            raise MigrationError(f'Source/target schema mismatch in {table}; transfer was cancelled')
                    target.execute('DELETE FROM workspaces')
                    for table in TABLES:
                        fields = columns[table]
                        slots = ','.join('?' for _ in fields)
                        sql = f'INSERT INTO {table} ({",".join(fields)}) VALUES ({slots})'
                        if rows[table]:
                            target.executemany(sql, [tuple(row[field] for field in fields) for row in rows[table]])
                    for table in TABLES:
                        if _signature(_read_rows(target, table)) != signatures[table]:
                            raise MigrationError(f'Row verification failed for {table}; target transaction rolled back')
                    if _analytics(target, rows['workspaces']) != expected_analytics:
                        raise MigrationError('Analytics verification failed; target transaction rolled back')
                    # Explicit imported IDs do not advance PostgreSQL sequences.
                    for table in TABLES:
                        maximum = max((row['id'] for row in rows[table]), default=0)
                        target.execute("SELECT setval(pg_get_serial_sequence(?, 'id'), ?, ?)", (table, max(1, maximum), maximum > 0))
                return {'status': 'migrated', 'tables': signatures, 'analytics_verified': len(expected_analytics)}
            except MigrationError:
                raise
            except Exception as exc:
                raise MigrationError('PostgreSQL transfer failed; target transaction was rolled back') from exc
