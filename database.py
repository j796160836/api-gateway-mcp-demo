"""SQLite schema and sample data for the REST service."""
import sqlite3
from contextlib import closing, contextmanager

from config import SQLITE_PATH


@contextmanager
def connect(*, write=False):
    with closing(sqlite3.connect(SQLITE_PATH)) as db, db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        if write:
            db.execute("BEGIN IMMEDIATE")
        yield db


def create_schema(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            sku TEXT PRIMARY KEY,
            available INTEGER NOT NULL CHECK (available >= 0)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            orderId TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            sku TEXT NOT NULL REFERENCES inventory(sku),
            quantity INTEGER NOT NULL,
            cancellationReason TEXT
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS shipments (
            id INTEGER PRIMARY KEY,
            orderId TEXT NOT NULL UNIQUE REFERENCES orders(orderId),
            status TEXT NOT NULL
        )
    """)


def seed_sample_data(db):
    db.execute("INSERT INTO inventory VALUES ('SKU-A01', 8)")
    db.execute("""
        INSERT INTO orders (orderId, status, sku, quantity) VALUES
            ('ORD-1001', 'PAID', 'SKU-A01', 2),
            ('ORD-1002', 'PAID', 'SKU-A01', 2)
    """)


def initialize():
    with connect(write=True) as db:
        create_schema(db)
        has_data = db.execute("""
            SELECT EXISTS (SELECT 1 FROM inventory)
                OR EXISTS (SELECT 1 FROM orders)
                OR EXISTS (SELECT 1 FROM shipments)
        """).fetchone()[0]
        if not has_data:
            seed_sample_data(db)
