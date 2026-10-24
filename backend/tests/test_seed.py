from app.database import Database
from app.seed import seed_inventory


def test_seed_populates_empty_database_once_and_preserves_changes(tmp_path):
    path = str(tmp_path / 'seed.db')
    assert seed_inventory(path) == 6
    with Database(path).connect() as db:
        rows = db.execute('SELECT * FROM vehicles').fetchall()
        assert len(rows) == 6
        assert any(row['quantity'] == 0 for row in rows)
        db.execute("UPDATE vehicles SET model = 'Custom model' WHERE id = ?", (rows[0]['id'],))
    assert seed_inventory(path) == 0
    with Database(path).connect() as db:
        assert db.execute('SELECT model FROM vehicles WHERE id = ?', (rows[0]['id'],)).fetchone()['model'] == 'Custom model'
        assert db.execute('SELECT COUNT(*) FROM users').fetchone()[0] == 0
