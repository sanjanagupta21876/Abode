"""
One-time migration script: creates menu_days, meal_types, hostel_menu tables
and seeds the lookup rows if they don't already exist.

Run from SHMM/ directory:
    python init_menu_tables.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'database', 'smart_hostel.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS menu_days (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL UNIQUE,
    display_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS meal_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meal TEXT NOT NULL UNIQUE,
    display_order INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS hostel_menu (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day_id INTEGER NOT NULL,
    meal_id INTEGER NOT NULL,
    items TEXT NOT NULL,
    calories INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (day_id) REFERENCES menu_days (id) ON DELETE CASCADE,
    FOREIGN KEY (meal_id) REFERENCES meal_types (id) ON DELETE CASCADE,
    UNIQUE(day_id, meal_id)
);
"""

DAYS = [
    (1, 'Monday',    1),
    (2, 'Tuesday',   2),
    (3, 'Wednesday', 3),
    (4, 'Thursday',  4),
    (5, 'Friday',    5),
    (6, 'Saturday',  6),
    (7, 'Sunday',    7),
]

MEALS = [
    (1, 'Breakfast', 1),
    (2, 'Lunch',     2),
    (3, 'Snacks',    3),
    (4, 'Dinner',    4),
]

def run():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    
    # Create tables
    conn.executescript(SCHEMA)
    
    # Seed days (ignore if already present)
    conn.executemany(
        "INSERT OR IGNORE INTO menu_days (id, day, display_order) VALUES (?, ?, ?)",
        DAYS
    )
    
    # Seed meal types (ignore if already present)
    conn.executemany(
        "INSERT OR IGNORE INTO meal_types (id, meal, display_order) VALUES (?, ?, ?)",
        MEALS
    )
    
    conn.commit()
    conn.close()
    print("✅  Menu tables created and seeded successfully.")
    print(f"   DB path: {DB_PATH}")

if __name__ == '__main__':
    run()
