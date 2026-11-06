import sqlite3
import os

db_path = r'c:\Users\Anika Bisht\abode\Abode\database\smart_hostel.db'
if os.path.exists(db_path):
    db = sqlite3.connect(db_path)
    print(db.execute("SELECT username, role, password FROM users WHERE role='warden'").fetchall())
else:
    print('DB not found at:', db_path)
