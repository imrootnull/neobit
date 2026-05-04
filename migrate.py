"""
SQLite migration script — run once when DB schema changes.
Usage: python3 migrate.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "neobit.db")

MIGRATIONS = [
    # (table, column, typedef)
    ("cameras", "resolution_w",  "INTEGER DEFAULT 0"),
    ("cameras", "resolution_h",  "INTEGER DEFAULT 0"),
    ("cameras", "fps",           "REAL    DEFAULT 0.0"),
    ("cameras", "audio_enabled", "INTEGER DEFAULT 0"),
]

def run():
    if not os.path.exists(DB_PATH):
        print(f"DB not found at {DB_PATH} — will be created on first run.")
        return

    db  = sqlite3.connect(DB_PATH)
    cur = db.cursor()

    for table, col, typedef in MIGRATIONS:
        existing = [r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        if col not in existing:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
            print(f"✅  {table}.{col} added")
        else:
            print(f"✔   {table}.{col} already exists")

    db.commit()
    db.close()
    print("Migration complete.")

if __name__ == "__main__":
    run()
