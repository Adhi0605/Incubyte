"""Analytics contract tests independent of the concurrently evolving Database."""

import sqlite3
from datetime import datetime, timezone

import pytest

from app import analytics


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 25, 12, tzinfo=timezone.utc).astimezone(tz)


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(analytics, 'datetime', FixedDatetime)
    connection = sqlite3.connect(tmp_path / 'analytics.sqlite')
    connection.row_factory = sqlite3.Row
    connection.executescript('''
        CREATE TABLE vehicles (
            id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL,
            make TEXT NOT NULL, model TEXT NOT NULL, condition TEXT NOT NULL,
            fuel_type TEXT NOT NULL, price_cents INTEGER NOT NULL,
            quantity INTEGER NOT NULL, created_at TEXT NOT NULL,
            deleted_at TEXT
        );
        CREATE TABLE purchases (
            id INTEGER PRIMARY KEY, workspace_id INTEGER NOT NULL,
            vehicle_id INTEGER NOT NULL, make TEXT NOT NULL,
            model TEXT NOT NULL, condition TEXT NOT NULL,
            fuel_type TEXT NOT NULL, quantity INTEGER NOT NULL,
            unit_price_cents INTEGER NOT NULL, total_cents INTEGER NOT NULL,
            purchased_at TEXT NOT NULL, is_demo INTEGER NOT NULL
        );
    ''')
    try:
        yield connection
    finally:
        connection.close()


def vehicle(db, vehicle_id, *, workspace=1, make='Tata', model='Nexon',
            condition='new', fuel='Petrol', price=100_00, quantity=1,
            created='2026-10-01T00:00:00+00:00', archived=None):
    db.execute('INSERT INTO vehicles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
               (vehicle_id, workspace, make, model, condition, fuel, price,
                quantity, created, archived))


def purchase(db, purchase_id, *, workspace=1, vehicle_id=1, make='Tata',
             condition='new', fuel='Petrol', quantity=1, price=100_00,
             at='2026-10-10T12:00:00+00:00', demo=0):
    db.execute('INSERT INTO purchases VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
               (purchase_id, workspace, vehicle_id, make, 'Original model',
                condition, fuel, quantity, price, quantity * price, at, demo))


def test_empty_workspace_has_zero_money_and_twelve_zero_filled_months(db):
    result = analytics.workspace_analytics(db, 1)
    assert result['summary'] == {
        'recorded_sales': '0.00', 'units_sold': 0,
        'average_sale_price': '0.00', 'inventory_value': '0.00',
        'inventory_units': 0, 'active_listings': 0,
    }
    assert result['monthly_sales'] == [
        {'month': month, 'sales': '0.00', 'units': 0}
        for month in ['2025-11', '2025-12', '2026-01', '2026-02', '2026-03',
                      '2026-04', '2026-05', '2026-06', '2026-07', '2026-08',
                      '2026-09', '2026-10']
    ]
    for key in ('by_brand', 'by_condition', 'by_fuel', 'low_stock', 'aging_stock'):
        assert result[key] == []
    assert 'synthetic' in result['demo_notice'].lower()


def test_inventory_is_current_active_and_independent_of_sales_date_filter(db):
    vehicle(db, 1, quantity=3, price=10_01)
    vehicle(db, 2, quantity=0, condition='used', fuel='Diesel', price=500_00)
    vehicle(db, 3, quantity=1, condition='used', fuel='Diesel', price=20_02)
    vehicle(db, 4, quantity=50, archived='2026-10-20T00:00:00Z')
    vehicle(db, 5, workspace=2, quantity=90)
    purchase(db, 1, at='2026-10-01T00:00:00Z')

    result = analytics.workspace_analytics(db, 1, '2020-01-01', '2020-01-31')
    assert result['summary'] == {
        'recorded_sales': '0.00', 'units_sold': 0, 'average_sale_price': '0.00',
        'inventory_value': '50.05', 'inventory_units': 4, 'active_listings': 3,
    }
    assert result['by_fuel'] == [
        {'name': 'Diesel', 'units': 1}, {'name': 'Petrol', 'units': 3},
    ]
    assert {row['id'] for row in result['low_stock']} == {2, 3}


def test_sales_use_durable_snapshots_even_for_archived_or_missing_listings(db):
    vehicle(db, 1, make='Edited brand', price=999_00,
            archived='2026-10-11T00:00:00Z')
    purchase(db, 1, make='Original brand', condition='used', quantity=2,
             price=10_01, demo=1)
    purchase(db, 2, vehicle_id=999, make='Other brand', price=20_02)
    # An inconsistent foreign snapshot must still never leak through a join.
    purchase(db, 3, workspace=2, vehicle_id=1, price=900_00)
    result = analytics.workspace_analytics(db, 1)
    assert result['summary']['recorded_sales'] == '40.04'
    assert result['summary']['units_sold'] == 3
    assert result['summary']['average_sale_price'] == '13.35'
    assert result['summary']['active_listings'] == 0
    assert result['by_brand'] == [
        {'name': 'Original brand', 'sales': '20.02', 'units': 2},
        {'name': 'Other brand', 'sales': '20.02', 'units': 1},
    ]
    assert result['by_condition'] == [
        {'name': 'new', 'sales': '20.02', 'units': 1},
        {'name': 'used', 'sales': '20.02', 'units': 2},
    ]


def test_dates_include_both_whole_days_and_zero_fill_missing_months(db):
    for index, (at, price) in enumerate([
        ('2026-01-14T23:59:59.999999Z', 99_00),
        ('2026-01-15T00:00:00Z', 10_00),
        ('2026-03-03T23:59:59.999999+00:00', 20_00),
        ('2026-03-04T00:00:00Z', 99_00),
    ], start=1):
        purchase(db, index, at=at, price=price)
    result = analytics.workspace_analytics(db, 1, '2026-01-15', '2026-03-03')
    assert result['summary']['recorded_sales'] == '30.00'
    assert result['summary']['units_sold'] == 2
    assert result['by_brand'] == [{'name': 'Tata', 'sales': '30.00', 'units': 2}]
    assert result['monthly_sales'] == [
        {'month': '2026-01', 'sales': '10.00', 'units': 1},
        {'month': '2026-02', 'sales': '0.00', 'units': 0},
        {'month': '2026-03', 'sales': '20.00', 'units': 1},
    ]


def test_single_day_window_and_one_sided_filters(db):
    purchase(db, 1, at='2024-12-31T23:59:59Z', price=10_00)
    purchase(db, 2, at='2026-08-10T23:59:59Z', price=20_00)
    purchase(db, 3, at='2026-10-01T00:00:00Z', price=30_00)
    one_day = analytics.workspace_analytics(db, 1, '2026-08-10', '2026-08-10')
    assert one_day['monthly_sales'] == [
        {'month': '2026-08', 'sales': '20.00', 'units': 1},
    ]
    since = analytics.workspace_analytics(db, 1, start_date='2026-08-01')
    assert since['summary']['recorded_sales'] == '50.00'
    assert [row['month'] for row in since['monthly_sales']] == [
        '2026-08', '2026-09', '2026-10',
    ]
    until = analytics.workspace_analytics(db, 1, end_date='2026-08-31')
    assert until['summary']['recorded_sales'] == '30.00'
    assert len(until['monthly_sales']) == 12
    assert until['monthly_sales'][0]['month'] == '2025-09'
    assert until['monthly_sales'][-1]['month'] == '2026-08'


def test_unfiltered_summary_retains_older_history_outside_default_chart(db):
    purchase(db, 1, at='2020-01-01T00:00:00Z', price=10_00)
    purchase(db, 2, at='2026-10-01T00:00:00Z', price=20_00)
    result = analytics.workspace_analytics(db, 1)
    assert result['summary']['recorded_sales'] == '30.00'
    assert sum(row['units'] for row in result['monthly_sales']) == 1


def test_all_outputs_are_isolated_and_workspace_id_is_bound(db):
    vehicle(db, 1, quantity=1, created='2020-01-01T00:00:00Z')
    vehicle(db, 2, workspace=2, make='Foreign', fuel='Foreign fuel',
            quantity=1, created='2020-01-01T00:00:00Z')
    purchase(db, 1)
    purchase(db, 2, workspace=2, make='Foreign', condition='used')
    own = analytics.workspace_analytics(db, 1)
    assert own['summary']['inventory_units'] == own['summary']['units_sold'] == 1
    assert own['by_brand'] == [{'name': 'Tata', 'sales': '100.00', 'units': 1}]
    assert own['by_condition'] == [{'name': 'new', 'sales': '100.00', 'units': 1}]
    assert own['by_fuel'] == [{'name': 'Petrol', 'units': 1}]
    for key in ('low_stock', 'aging_stock'):
        assert [row['id'] for row in own[key]] == [1]
    missing = analytics.workspace_analytics(db, '1 OR 1 = 1')
    assert missing['summary']['active_listings'] == 0
    assert missing['summary']['units_sold'] == 0


def test_low_stock_and_aging_boundaries_and_vehicle_summary(db):
    vehicle(db, 1, quantity=0, created='2020-01-01T00:00:00Z')
    vehicle(db, 2, quantity=1, condition='used', price=123_45,
            created='2026-07-27T23:59:59Z')  # Exactly 90 calendar days.
    vehicle(db, 3, quantity=2, created='2026-07-28T00:00:00Z')
    vehicle(db, 4, quantity=3, created='2020-01-01T00:00:00Z')
    vehicle(db, 5, quantity=1, created='2020-01-01T00:00:00Z',
            archived='2026-10-01T00:00:00Z')
    result = analytics.workspace_analytics(db, 1)
    assert [row['id'] for row in result['low_stock']] == [1, 2, 3]
    assert [row['id'] for row in result['aging_stock']] == [4, 2]
    listing = result['aging_stock'][1]
    assert {key: listing[key] for key in (
        'id', 'make', 'model', 'condition', 'quantity', 'price', 'age_days',
    )} == {'id': 2, 'make': 'Tata', 'model': 'Nexon', 'condition': 'used',
           'quantity': 1, 'price': '123.45', 'age_days': 90}


def test_money_is_exact_beyond_float_precision_and_average_rounds_half_up(db):
    # Both SQLite integer aggregation and binary floating point can lose money.
    huge = 9_007_199_254_740_993
    vehicle(db, 1, quantity=2000, price=huge)
    purchase(db, 1, price=huge)
    purchase(db, 2, price=1)
    result = analytics.workspace_analytics(db, 1)
    assert result['summary']['inventory_value'] == '180143985094819860.00'
    assert result['summary']['recorded_sales'] == '90071992547409.94'
    assert result['summary']['average_sale_price'] == '45035996273704.97'
    assert result['monthly_sales'][-1]['sales'] == '90071992547409.94'
    db.execute('DELETE FROM purchases')
    purchase(db, 3, price=2)
    purchase(db, 4, price=3)
    assert analytics.workspace_analytics(db, 1)['summary']['average_sale_price'] == '0.03'


def test_analytics_does_not_mutate_or_commit_the_callers_transaction(db):
    vehicle(db, 1)
    purchase(db, 1)
    analytics.workspace_analytics(db, 1)
    assert db.in_transaction
    db.rollback()
    assert db.execute('SELECT COUNT(*) FROM vehicles').fetchone()[0] == 0
    assert db.execute('SELECT COUNT(*) FROM purchases').fetchone()[0] == 0
