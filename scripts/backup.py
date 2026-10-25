"""Create a verified, private SQLite snapshot, including committed WAL data."""

import argparse
from contextlib import closing
import math
import os
from pathlib import Path
import sqlite3
import tempfile
import time


def backup_sqlite(source: Path, destination: Path, timeout: float = 60) -> Path:
    """Publish a complete snapshot atomically without replacing an existing file."""
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Timeout must be a positive finite number")
    source = source.expanduser().resolve(strict=True)
    destination = destination.expanduser().absolute()
    if not source.is_file():
        raise ValueError("Source must be an existing SQLite file")
    if destination.resolve() == source:
        raise ValueError("Backup destination must differ from the source")
    if os.path.lexists(destination):
        raise FileExistsError("Backup destination already exists")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".sqlite-backup-", suffix=".db", dir=destination.parent,
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    deadline = time.monotonic() + timeout

    def progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError("SQLite backup timed out; retry when writes/locks subside")

    try:
        # mode=ro rejects absent sources and reads the live WAL; immutable would not.
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=timeout)) as src:
            with closing(sqlite3.connect(temporary)) as dst:
                src.backup(dst, pages=256, progress=progress, sleep=0.1)
                # Produce a standalone database, requiring no WAL/SHM sidecars.
                dst.execute("PRAGMA journal_mode=DELETE")
                result = dst.execute("PRAGMA integrity_check").fetchall()
                if result != [("ok",)]:
                    raise ValueError("SQLite backup failed its integrity check")
        with temporary.open("rb") as snapshot:
            os.fsync(snapshot.fileno())
        # Hard-link publication is atomic and fails if a destination appeared meanwhile.
        # Both names are in one directory, so this never crosses filesystems.
        os.link(temporary, destination)
        return destination
    finally:
        temporary.unlink(missing_ok=True)
        for suffix in ("-wal", "-shm", "-journal"):
            Path(str(temporary) + suffix).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="New backup file (never overwritten)")
    parser.add_argument("--source", type=Path, help="Defaults to DATABASE_PATH or backend/inventory.db")
    parser.add_argument("--timeout", type=float, default=60, help="Backup deadline in seconds (default: 60)")
    args = parser.parse_args()
    if args.source is None and os.environ.get("DATABASE_URL"):
        parser.error("DATABASE_URL is set; use pg_dump for PostgreSQL, or explicitly select a SQLite --source")
    source = args.source or Path(
        os.environ.get("DATABASE_PATH")
        or str(Path(__file__).resolve().parents[1] / "backend" / "inventory.db")
    )
    try:
        destination = backup_sqlite(source, args.destination, args.timeout)
    except (OSError, sqlite3.Error, ValueError, TimeoutError) as error:
        parser.exit(1, f"Backup failed: {error}\n")
    print(f"SQLite backup verified: {destination}")


if __name__ == "__main__":
    main()
