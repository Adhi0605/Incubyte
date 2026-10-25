"""Read-only, workspace-scoped recorded sales and current inventory analytics."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext


LOW_STOCK_THRESHOLD = 2
AGING_STOCK_DAYS = 90
DEMO_NOTICE = (
    'Inventory and seeded purchase history are synthetic demonstration data. '
    'Recorded sales describe purchase records; no payments or real revenue are implied.'
)


def _money(cents, units=1):
    """Format exact integer paise as INR, rounding averages to the nearest paise."""
    # Aggregate in Python integers: SQLite SUM/product can overflow signed int64.
    # Give Decimal enough precision for large totals as well as division/rounding.
    with localcontext() as context:
        context.prec = max(28, len(str(abs(cents))) + len(str(units)) + 6)
        amount = Decimal(cents) / Decimal(100) / Decimal(units)
        return format(amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), '.2f')


def _month_offset(month, offset):
    index = month.year * 12 + month.month - 1 + offset
    year, zero_based_month = divmod(index, 12)
    return date(year, zero_based_month + 1, 1)


def _sales_breakdown(purchases, field):
    totals = {}
    for row in purchases:
        name = row[field]
        entry = totals.setdefault(name, {'cents': 0, 'units': 0})
        entry['cents'] += row['total_cents']
        entry['units'] += row['quantity']
    return [
        {'name': name, 'sales': _money(totals[name]['cents']),
         'units': totals[name]['units']}
        for name in sorted(totals)
    ]


def workspace_analytics(db, workspace_id, start_date=None, end_date=None):
    """Return the analytics API contract using an existing caller-owned connection.

    The API validates and bounds ISO dates (or ``date`` objects) before calling.
    Optional bounds filter all historical sales metrics inclusively. Inventory
    always reflects current, nonarchived listings. Without bounds the summary
    includes all history and the chart covers the latest twelve calendar months.
    An end-only chart uses twelve months ending in that month; a start-only chart
    runs through the current month (or the start month when it is in the future).

    Brand/condition breakdowns use purchase snapshots. Fuel units, low stock
    (including sold-out listings), and aging stock (90+ calendar days with stock
    on hand) describe current inventory. This function never writes or commits.
    """
    today = datetime.now(timezone.utc).date()
    start = date.fromisoformat(start_date) if isinstance(start_date, str) else start_date
    end = date.fromisoformat(end_date) if isinstance(end_date, str) else end_date

    predicates = ['workspace_id = ?']
    parameters = [workspace_id]
    if start is not None:
        predicates.append('purchased_at >= ?')
        parameters.append(start.isoformat())
    if end is not None:
        predicates.append('purchased_at < ?')
        parameters.append((end + timedelta(days=1)).isoformat())
    purchases = list(db.execute(
        'SELECT make, condition, quantity, total_cents, purchased_at '
        'FROM purchases WHERE ' + ' AND '.join(predicates), tuple(parameters),
    ))
    inventory = list(db.execute(
        'SELECT id, make, model, condition, fuel_type, price_cents, quantity, created_at '
        'FROM vehicles WHERE workspace_id = ? AND deleted_at IS NULL',
        (workspace_id,),
    ))

    sales_cents = sum(row['total_cents'] for row in purchases)
    units_sold = sum(row['quantity'] for row in purchases)
    inventory_cents = sum(row['price_cents'] * row['quantity'] for row in inventory)

    last_month = (end or today).replace(day=1)
    first_month = start.replace(day=1) if start else _month_offset(last_month, -11)
    if start and end is None:
        last_month = max(last_month, first_month)
    monthly = {}
    month = first_month
    while month <= last_month:
        monthly[month.strftime('%Y-%m')] = {'cents': 0, 'units': 0}
        # Avoid stepping beyond the representable date at the end of the window.
        if month == last_month:
            break
        month = _month_offset(month, 1)
    for row in purchases:
        bucket = monthly.get(row['purchased_at'][:7])
        if bucket is not None:
            bucket['cents'] += row['total_cents']
            bucket['units'] += row['quantity']

    fuel_units = {}
    listings = []
    for row in inventory:
        fuel = row['fuel_type']
        fuel_units[fuel] = fuel_units.get(fuel, 0) + row['quantity']
        age_days = max(0, (today - date.fromisoformat(row['created_at'][:10])).days)
        listings.append({
            'id': row['id'], 'make': row['make'], 'model': row['model'],
            'condition': row['condition'], 'quantity': row['quantity'],
            'price': _money(row['price_cents']), 'created_at': row['created_at'],
            'age_days': age_days,
        })

    return {
        'summary': {
            'recorded_sales': _money(sales_cents), 'units_sold': units_sold,
            'average_sale_price': _money(sales_cents, units_sold) if units_sold else '0.00',
            'inventory_value': _money(inventory_cents),
            'inventory_units': sum(row['quantity'] for row in inventory),
            'active_listings': len(inventory),
        },
        'monthly_sales': [
            {'month': month, 'sales': _money(totals['cents']), 'units': totals['units']}
            for month, totals in monthly.items()
        ],
        'by_brand': _sales_breakdown(purchases, 'make'),
        'by_condition': _sales_breakdown(purchases, 'condition'),
        'by_fuel': [{'name': name, 'units': fuel_units[name]} for name in sorted(fuel_units)],
        'low_stock': sorted(
            (row for row in listings if row['quantity'] <= LOW_STOCK_THRESHOLD),
            key=lambda row: (row['quantity'], row['id']),
        ),
        'aging_stock': sorted(
            (row for row in listings if row['quantity'] > 0 and row['age_days'] >= AGING_STOCK_DAYS),
            key=lambda row: (-row['age_days'], row['id']),
        ),
        'demo_notice': DEMO_NOTICE,
    }
