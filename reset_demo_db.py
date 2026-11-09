"""Clear the demo tables and restore the sample data."""
from config import SQLITE_PATH
from database import connect, create_schema, seed_sample_data


if __name__ == "__main__":
    with connect(write=True) as db:
        create_schema(db)
        db.execute("DELETE FROM shipments")
        db.execute("DELETE FROM orders")
        db.execute("DELETE FROM inventory")
        seed_sample_data(db)
    print(f"Restored sample data in {SQLITE_PATH.resolve()}")
