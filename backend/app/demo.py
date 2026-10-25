"""Provision private sample inventory and labeled history in a caller transaction.

No connection, commit, rollback, schema changes, or workspace flags are owned by
this module. The coordinator sets demo_seeded in the same transaction. Existing
legacy/custom rows are retained alongside the catalog; seeded owner edits survive.
"""

import calendar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import json

from .catalog import catalog_vehicles


def _timestamp(day, hour=12):
    return f'{day.isoformat()}T{hour:02d}:00:00Z'


def _purchase_days(last_day):
    """Twelve calendar months, ending yesterday, with no future/today sales."""
    month_index = last_day.year * 12 + last_day.month - 1
    for month_offset in range(12):
        year, zero_month = divmod(month_index - 11 + month_offset, 12)
        month = zero_month + 1
        final_day = min(calendar.monthrange(year, month)[1],
                        last_day.day if month_offset == 11 else 31)
        # There is still one record in the final month when yesterday was day 1.
        days = sorted({min(day, final_day) for day in (3, 8, 13, 18, 23, 28)}
                      | ({last_day.day} if month_offset == 11 else set()))
        for day in days:
            yield date(year, month, day)


def populate_workspace(db, workspace_id):
    """Insert 200 vehicles and deterministic synthetic activity; return count.

    History is deterministic for a given UTC provisioning date. Its rolling
    twelve-month window ends yesterday, leaving today's analytics for live
    transactions. All records are inserted using the caller's DB connection
    and common SQLite/PostgreSQL SQL with dictionary-like RETURNING rows.
    """
    if db.execute('SELECT id FROM vehicles WHERE workspace_id = ? AND stock_number LIKE ? LIMIT 1',
                  (workspace_id, 'IN-%')).fetchone():
        return 0

    last_day = datetime.now(timezone.utc).date() - timedelta(days=1)
    sale_days = list(_purchase_days(last_day))
    vehicles = catalog_vehicles()
    new_indices = [i for i, vehicle in enumerate(vehicles) if vehicle['condition'] == 'new']
    sold_used_indices = [i for i, vehicle in enumerate(vehicles)
                        if vehicle['condition'] == 'used' and vehicle['quantity'] == 0]
    schedule = []
    # Stable variation by month/day gives trends and brand/fuel diversity.
    for index, day in enumerate(sale_days):
        for offset in range(2 + index % 3):
            schedule.append((new_indices[(index * 7 + offset * 13) % len(new_indices)], day))
    for index, vehicle_index in enumerate(sold_used_indices):
        schedule.append((vehicle_index, sale_days[(index * 11) % len(sale_days)]))
    schedule.sort(key=lambda entry: (entry[1], entry[0]))
    sale_counts = {}
    for vehicle_index, _ in schedule:
        sale_counts[vehicle_index] = sale_counts.get(vehicle_index, 0) + 1

    vehicle_ids = []
    first_day = sale_days[0] - timedelta(days=1)
    for index, vehicle in enumerate(vehicles):
        fields = {key: value for key, value in vehicle.items() if key not in {'price', 'images'}}
        fields['workspace_id'] = workspace_id
        fields['price_cents'] = int(Decimal(vehicle['price']) * 100)
        fields['images_json'] = json.dumps(vehicle['images'], ensure_ascii=False, separators=(',', ':'))
        # When running at a later date, keep opening stock before all sales.
        # Catalog timestamps stay deterministic; history never predates a row.
        fields['created_at'] = min(fields['created_at'], _timestamp(first_day, 9))
        fields['updated_at'] = fields['created_at']
        columns = ', '.join(fields)
        placeholders = ', '.join('?' for _ in fields)
        vehicle_id = db.execute(
            f'INSERT INTO vehicles ({columns}) VALUES ({placeholders}) RETURNING id',
            tuple(fields.values()),
        ).fetchone()['id']
        vehicle_ids.append(vehicle_id)
        opening_stock = vehicle['quantity'] + sale_counts.get(index, 0)
        if opening_stock:
            db.execute('''
                INSERT INTO inventory_events
                (workspace_id, vehicle_id, event_type, quantity_delta, created_at, is_demo)
                VALUES (?, ?, ?, ?, ?, ?) RETURNING id
            ''', (workspace_id, vehicle_id, 'restock', opening_stock, fields['created_at'], 1)).fetchone()['id']

    for index, day in schedule:
        vehicle = vehicles[index]
        # Snapshot historical prices independently from current asking prices.
        price_cents = int(Decimal(vehicle['price']) * 100)
        unit_price_cents = price_cents * (94 + day.month % 7) // 100
        purchased_at = _timestamp(day)
        db.execute('''
            INSERT INTO purchases
            (workspace_id, vehicle_id, make, model, condition, fuel_type, quantity,
             unit_price_cents, total_cents, purchased_at, is_demo)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id
        ''', (workspace_id, vehicle_ids[index], vehicle['make'], vehicle['model'],
              vehicle['condition'], vehicle['fuel_type'], 1, unit_price_cents,
              unit_price_cents, purchased_at, 1)).fetchone()['id']
        db.execute('''
            INSERT INTO inventory_events
            (workspace_id, vehicle_id, event_type, quantity_delta, created_at, is_demo)
            VALUES (?, ?, ?, ?, ?, ?) RETURNING id
        ''', (workspace_id, vehicle_ids[index], 'purchase', -1, purchased_at, 1)).fetchone()['id']
    return len(vehicles)
