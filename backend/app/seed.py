"""Optional sample inventory; never replaces a nonempty collection."""

from .database import Database


SAMPLE_VEHICLES = [
    ("Toyota", "Camry Hybrid", "Sedan", 3250050, 8),
    ("Land Rover", "Defender 110", "SUV", 7290000, 3),
    ("BMW", "330i", "Sedan", 4620000, 5),
    ("Ford", "Bronco Sport", "SUV", 3499500, 4),
    ("Porsche", "718 Cayman", "Coupe", 7290000, 0),
    ("Volvo", "XC60", "SUV", 4890000, 6),
]


def seed_inventory(database_path):
    database = Database(database_path)
    with database.connect() as db:
        db.execute("BEGIN IMMEDIATE")
        if db.execute("SELECT 1 FROM vehicles LIMIT 1").fetchone():
            return 0
        db.executemany(
            "INSERT INTO vehicles(make, model, category, price_cents, quantity) VALUES (?, ?, ?, ?, ?)",
            SAMPLE_VEHICLES,
        )
    return len(SAMPLE_VEHICLES)


if __name__ == "__main__":
    from .main import production_app

    app = production_app()
    count = seed_inventory(app.state.database_path)
    print(f"Added {count} sample vehicles. Existing inventory was preserved.")
