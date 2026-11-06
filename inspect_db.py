import sqlite3

conn = sqlite3.connect('database/smart_hostel.db')
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in cursor.fetchall()]
print('TABLES:', tables)

print('\n--- USERS SCHEMA ---')
cursor.execute('PRAGMA table_info(users)')
for row in cursor.fetchall():
    print(row)

print('\n--- COMPLAINTS SCHEMA ---')
cursor.execute('PRAGMA table_info(complaints)')
for row in cursor.fetchall():
    print(row)

print('\n--- NOTIFICATIONS SCHEMA ---')
cursor.execute('PRAGMA table_info(notifications)')
for row in cursor.fetchall():
    print(row)

print('\n--- ALL USERS ---')
cursor.execute('SELECT id, username, role, full_name FROM users')
for row in cursor.fetchall():
    print(row)

print('\n--- COMPLAINT COUNTS ---')
cursor.execute('SELECT COUNT(*) FROM complaints')
print('Total complaints:', cursor.fetchone()[0])

conn.close()
