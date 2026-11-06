"""
Seeds the hostel_menu table with the default weekly menu from NSC Bose.
Uses INSERT OR REPLACE — runs safely multiple times (overwrites existing entries).

Run from SHMM/ directory:
    python seed_menu.py
"""
import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(__file__), 'database', 'smart_hostel.db')

# day_id: Monday=1 … Sunday=7  |  meal_id: Breakfast=1, Lunch=2, Snacks=3, Dinner=4
MENU_DATA = [
    # ── MONDAY ──────────────────────────────────────────────────────────────
    (1, 1, "Bread & Butter, Jam, Boil Egg, Aloo Paratha, Curd & Pickle, Coffee / Tea", 520),
    (1, 2, "Rice, Chapati, Mix Veg, Dal Masoor, Salad & Seasonal Fruits, Raita", 650),
    (1, 3, "Patties, Tea", 220),
    (1, 4, "Butter Chicken, Puri Sabji, Salad, Chapati", 720),

    # ── TUESDAY ─────────────────────────────────────────────────────────────
    (2, 1, "Bread & Butter, Jam, Idli Sambar, Tea & Coffee", 380),
    (2, 2, "Rice, Chapati, Dal Fry, Jeera Aloo, Raita, Salad & Fruits", 620),
    (2, 3, "Pizza, Tea", 350),
    (2, 4, "Jeera Rice, Dal, Palak Paneer, Chapati, Salad, Milk", 680),

    # ── WEDNESDAY ───────────────────────────────────────────────────────────
    (3, 1, "Steam Aloo / Puri Sabji, Boil Egg, Milk", 450),
    (3, 2, "Jeera Rice, Rajma Masala, Veg Jalfrezi, Salad, Papad, Seasonal Fruits, Raita", 700),
    (3, 3, "Brownie / Cupcake, Strong Coffee", 280),
    (3, 4, "Veg Fried Rice, Roti, Chilli Chicken, Chilli Paneer, Manchurian, Custard", 780),

    # ── THURSDAY ────────────────────────────────────────────────────────────
    (4, 1, "Bread & Butter, Jam, Oats & Milk, Boil Egg, Pav Bhaji", 550),
    (4, 2, "Kadhi Pakoda, Chapati, Seasonal Vegetable, Raita, Achar, Papad, Salad, Gulab Jamun", 720),
    (4, 3, "Lays, Grilled Sandwich (Cheese)", 320),
    (4, 4, "Dal Makhani, Jeera Rice, Aloo Gobhi, Chapati", 680),

    # ── FRIDAY ──────────────────────────────────────────────────────────────
    (5, 1, "Brown Bread, Jam, Paneer Pyas, Paratha, Boil Egg, Coffee", 480),
    (5, 2, "Chapati, Moong Dal, Masala Kala Chana, Raita, Fruits, Phirni", 650),
    (5, 3, "Maggi / Burger with Cheese, Banana Shake", 420),
    (5, 4, "Masala Chicken, Kadhi Paneer, Mix Dal, Rice, Chapati", 750),

    # ── SATURDAY ────────────────────────────────────────────────────────────
    (6, 1, "Methi Paratha / Simple Paratha, Aloo Sabzi, Raita & Jeera", 430),
    (6, 2, "Chole Bhature, Raita", 680),
    (6, 3, "Noodles, Cold Coffee", 380),
    (6, 4, "Jeera Rice, Chapati, Seasonal Vegetable / Dal, RasMalai / Ice Cream / Gajar Halwa", 720),

    # ── SUNDAY ──────────────────────────────────────────────────────────────
    (7, 1, "Bread & Butter, Jam, Omelette, Banana, Kachodi with Chutney", 500),
    (7, 2, "Chicken Biryani / Veg Biryani, Raita, Salad", 720),
    (7, 3, "Samosa & Green Chutni, Tea & Coffee", 250),
    (7, 4, "Egg Curry, Aloo Chaar, Chana Vegetable, Rice, Chapati, Salad, Raita", 700),
]

def run():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    conn.executemany("""
        INSERT OR REPLACE INTO hostel_menu (day_id, meal_id, items, calories, updated_at)
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
    """, MENU_DATA)

    conn.commit()
    print(f"✅  Seeded {len(MENU_DATA)} menu entries successfully.")
    conn.close()

if __name__ == '__main__':
    run()
