"""Transfer a stopped SQLite app to an empty PostgreSQL DB without losing IDs."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from app.transfer import MigrationError, migrate_sqlite_to_postgres


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Existing SQLite file or verified snapshot')
    parser.add_argument('--report', type=Path, help='New private JSON report file; never overwritten')
    parser.add_argument('--target-env', default='DATABASE_URL', help='Environment variable containing the target PostgreSQL URL')
    args = parser.parse_args()
    url = os.environ.get(args.target_env, '')
    if not url:
        parser.error(f'Set {args.target_env} privately to the target PostgreSQL URL')
    try:
        if args.report and args.report.exists():
            raise MigrationError('Report already exists; select a new report path')
        report = migrate_sqlite_to_postgres(args.source, url)
        if args.report:
            descriptor = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w') as file:
                json.dump(report, file, indent=2)
                file.write('\n')
    except (MigrationError, OSError) as exc:
        parser.exit(1, f'Migration failed: {exc}\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
