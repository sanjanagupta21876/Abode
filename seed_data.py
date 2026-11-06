"""
Seed script - creates tables and populates with real student data for SQLite.
Usage: python seed_data.py
"""
import sqlite3
import os
from werkzeug.security import generate_password_hash

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database', 'smart_hostel.db')


def seed():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    cur = conn.cursor()

    # ── Create all tables ─────────────────────
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role TEXT CHECK(role IN ('student','warden')) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            roll_number TEXT UNIQUE,
            course TEXT,
            year INTEGER DEFAULT 1,
            room_number TEXT,
            phone TEXT,
            parent_name TEXT,
            parent_phone TEXT,
            address TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS warden (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            employee_id TEXT UNIQUE NOT NULL,
            department TEXT,
            phone TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS workers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            phone TEXT,
            is_available INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP 
               );
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            status TEXT CHECK(status IN ('present','absent')) NOT NULL,
            marked_by INTEGER,
            marked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (marked_by) REFERENCES users(id) ON DELETE SET NULL,
            UNIQUE (student_id, date)
                      
        );
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT DEFAULT 'other',
            status TEXT DEFAULT 'pending',
            assigned_worker INTEGER DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (assigned_worker) REFERENCES workers(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER,
            user_id INTEGER,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE SET NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS roommate_profiles (
            student_id INTEGER PRIMARY KEY,
            q1 INTEGER, q2 INTEGER, q3 INTEGER, q4 INTEGER, q5 INTEGER,
            q6 INTEGER, q7 INTEGER, q8 INTEGER, q9 INTEGER, q10 INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS roommate_swipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            swiper_id INTEGER NOT NULL,
            swipee_id INTEGER NOT NULL,
            action TEXT CHECK(action IN ('right', 'left')) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (swiper_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (swipee_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE (swiper_id, swipee_id)
        );
        CREATE TABLE IF NOT EXISTS roommate_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE
        );
                      
        CREATE TABLE IF NOT EXISTS emergency_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            phone TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # ── Clear old data ─────────────────────
    for table in ['emergency_contacts', 'roommate_messages', 'roommate_swipes', 'roommate_profiles', 
                  'notifications', 'attendance',
                  'complaints', 'students', 'warden', 'workers', 'users']:
        cur.execute(f"DELETE FROM {table}")
    cur.execute("DELETE FROM sqlite_sequence")  # reset auto-increment

    # ── Passwords ─────────────────────
    student_pw = generate_password_hash('Student@123')
    warden_pw  = generate_password_hash('Warden@123')

    # ── Wardens (id 1, 2) ─────────────────────
    wardens = [
        ('warden_mudit',   warden_pw, 'Mudit Dixit',  'mudit.warden@hostel.edu',   'warden'),
        ('warden_priya', warden_pw, 'Priya Sharma',  'priya.warden@hostel.edu', 'warden'),
    ]
    cur.executemany("INSERT INTO users (username, password, full_name, email, role) VALUES (?,?,?,?,?)", wardens)
    cur.execute("INSERT INTO warden (user_id, employee_id, department, phone) VALUES (1,'EMP001','Administration','9876543210')")
    cur.execute("INSERT INTO warden (user_id, employee_id, department, phone) VALUES (2,'EMP002','Administration','9876543211')")
    print("✅ Wardens inserted (2)")

    # ──────────────────────────────────────────────────────────
    #  REAL STUDENT DATA — 53 students
    #  (username, full_name, email, room, branch, year, reg_no, phone)
    # ──────────────────────────────────────────────────────────
    raw_students = [
        # --- Girls Block (1000-series) ---
        ('aanya_singh',       'Aanya Singh',       '1001', 'CSE',       2, 'RA2411003030249', '9810467042'),
        ('arshia_bhandari',   'Arshia Bhandari',   '1002', 'CSE',       2, 'RA2411003030100', '6283391915'),
        ('ashika_gupta',      'Ashika Gupta',      '1002', 'CSE AIML',        2, 'RA2411026030110', '6283391995'),
        ('sanjana_gupta',     'Sanjana Gupta',     '1004', 'CSE',       2, 'RA2411026030192', '7000489253'),
        ('anika_bisht',       'Anika Bisht',       '1004', 'CSE',       2, 'RA2411090030069', '9810118047'),
        ('shelly',            'Shelly',            '1000', 'CSE AIML',        2, 'RA2411026030193','6283391915'),
        ('palak_behune',      'Palak Behune',      '1008', 'CSE AIML',        2, 'RA2411026030199',    '6283391815'),
        ('kaushiki',          'Kaushiki',          '1009', 'CSE',        2, 'RA2411026030182',              '8597873286'),
        ('ananya_raj',        'Ananya Raj',        '1009', 'CSE',        2, 'RA2411026030210','6283391915'),
        ('nandini_gambhir',   'Nandini Gambhir',   '1010', 'CSE DS',  2, 'RA2411026030077', '7206220721'),
        ('shreya_sharma',     'Shreya Sharma',     '1012', 'CSE AIML',        2, 'RA2411026030162', '6283391915'),
        ('samiksha_goel',     'Samiksha Goel',     '1015', 'CSE AIML',        2, 'RA2411026030172',    '7206220721'    ),
        ('jyotsna_singh',     'Jyotsna Singh',     '1015', 'CSE Core',        2, 'RA2411026030229', '7668418491'),

        # --- Boys Block A (3000-series) ---
        ('anukrat_gupta',     'Anukrat Gupta',     '3001', 'CSE Core',  2, 'RA2411003030320', '8949614426'),
        ('neil_maheswari',    'Neil Maheswari',    '3002', 'CSE Core',        2, 'RA2411026030214',              '7358036440'),
        ('yashvardhan_verma', 'Yashvardhan Verma', '3003', 'CSE Core',  2, 'RA2411003030347', '9650936204'),
        ('abhyuday_singh',    'Abhyuday Pratap Singh', '3004', 'CSE',   2, 'RA2411003030332', '6393283723'),
        ('harshal_verma',     'Harshal Verma',     '3004', 'CSE Core',    2, 'RA2411026030215',              '7037744490'),
        ('kaushik',           'Kaushik',           '3006', 'CSE Core',        2, 'RA2411026030216',            '7206220721'),
        ('sweekarn_bajpai',   'Sweekarn Bajpai',   '3006', 'CSE Core',        2, 'RA2411026030218',              '9453432014'),
        ('abhinav_singh',     'Abhinav Singh',     '3007', 'CSE Core',        2, 'RA2411026030219',              '7209220721'),
        ('sarthak_verma',     'Sarthak Verma',     '3007', 'CSE',       2, 'RA2411003030155', '8318230102'),
        ('nitin',             'Nitin',             '3008', 'CSE',        2, 'RA2411026030152',              '8689055776'),
        ('aayush_jaiswal',    'Aayush Jaiswal',    '3008', 'CSE',        2, 'RA2411026030153',              '7206220901'),
        ('parv_nigam',        'Parv Nigam',        '3010', 'CSE',        2, 'RA2411026030154',              '7206220711'),
        ('arjun_saxena',      'Arjun Saxena',      '3010', 'Mech',      2, 'RA2411002030006', '6394602130'),
        ('umang',             'Umang',             '3011', 'CSE',       2, 'RA2211003010012', '9958387333'),
        ('garav_gulati',      'Garav Gulati',      '3012', 'CSE',        2, 'RA2411026030100',              '9829866268'),
        ('rudra_sinha',       'Rudra Sinha',       '3012', 'CSE',       2, 'RA2411026030101', '8076736223'),
        ('yashasvi_singh',    'Yashasvi Singh',    '3013', 'CSE',       2, 'RA2411003030159', '7014653420'),
        ('hardik_dave',       'Hardik Dave',       '3013', 'CSE AIML',        2, 'RA2411026030169',              '7206220781'),
        ('srijan_singh',      'Srijan Singh',      '3014', 'CSE',        2, 'RA2411026030179',              '8920042743'),
        ('krishna_goyal',     'Krishna Goyal',     '3014', 'CSE',        2, 'RA2411026030191',              '6396614157'),
        ('kartikey_singh',    'Kartikey Singh',    '3015', 'CSE AIML',        2, 'RA2411026030168',              '7704928177'),
        ('guarmehar',         'Guarmehar',         '3015', 'B.Tech',    2, 'RA2411026030190', '6283906863'),
        ('akash_mehra',       'Akash Mehra',       '3016', 'B.Tech CSE',2, 'RA2411003030273', '9024018879'),
        ('swastik_mittal',    'Swastik Mittal',    '3016', 'CSE',        2, 'RA2411026030129',              '7015246711'),
        ('atharv_saxena',     'Atharv Saxena',     '3017', 'CSE Core',        2, 'RA2411026030112',              '8817418566'),
        ('samridh_bajaj',     'Samridh Bajaj',     '3018', 'CSE',        2, 'RA2411026030242',              '9667229366'),
        ('shushant',          'Shushant',          '3018', 'CSE Core',  2, 'RA2411003030414', '9810275814'),
        ('parth_tyagi',       'Parth Tyagi',       '3019', 'B.Tech CSE',2, 'RA2411026030105', '9950255450'),
        ('shradul_verma',     'Shradul Verma',     '3019', 'CSE Core',        2, 'RA2411026030392',              '7235420721'),
        ('pratham',           'Pratham',           '3020', 'CSE AIML',        2, 'RA2411026030292',              '9119178066'),
        ('chirag_bansal',     'Chirag Bansal',     '3021', 'B.Tech',    2, 'RA2411056030203', '7988641735'),
        ('waasif_khalid',     'Waasif Khalid',     '3020', 'CSE AIML',        2, 'RA2411026030422',             '7256740721'),
        ('prabhas_chaudhary', 'Prabhas Chaudhary', '3021', 'B.Tech',    2, 'RA2411003030079', '7088584197'),

        # --- Block C (5000-series) ---
        ('yash_chauhan',      'Yash Chauhan',      '5001', 'B.Tech',    2, 'RA241102630174',  '7017452844'),
        ('robbin_agarwal',    'Robbin Agarwal',    '5001', 'B.Tech',    2, 'RA2411056030005', '7983615073'),
        ('avik_chaudhary',    'Avik Chaudhary',    '5001', 'CSE Core',        2, 'RA241102603123',              '9990144339'),

        # --- Others ---
        ('diya_sah',          'Diya Sah',          '2002', 'CSE AIML',        2, 'RA2411026030232',              '7206257981'),
        ('manan_singh',       'Manan Singh',       '3014', 'CSE AIML',        2, 'RA2411026030001',              '9355046113'),
        ('ansh_pratap_singh', 'Ansh Pratap Singh',  '3004', 'CSE Core',        2, 'RA2411026030002',              '9555611978'),
    ]

    print(f"📝 Inserting {len(raw_students)} students...")

    # Insert users (IDs will be 3 .. 3+N-1 since wardens are 1,2)
    user_rows = []
    for uname, fname, *_ in raw_students:
        email = f"{uname}@student.hostel.edu"
        user_rows.append((uname, student_pw, fname, email, 'student'))
    cur.executemany("INSERT INTO users (username, password, full_name, email, role) VALUES (?,?,?,?,?)", user_rows)

    # Insert student profiles
    for idx, (uname, fname, room, branch, year, reg_no, phone) in enumerate(raw_students):
        user_id = idx + 3  # offset by 2 wardens
        cur.execute("""
            INSERT INTO students (user_id, roll_number, course, year, room_number, phone)
            VALUES (?,?,?,?,?,?)
        """, (user_id, reg_no, branch, year, room, phone))

    print(f"✅ {len(raw_students)} students inserted")

    # ── Workers ─────────────────────
    workers = [
        ('Ramu',   'Plumber',     '9800000001', 1),
        ('Shamu',  'Electrician', '9800000002', 1),
        ('Gopal',  'Carpenter',   '9800000003', 0),
        ('Mohan',  'Cleaner',     '9800000004', 1),
        ('Deepak', 'Security',    '9800000005', 1),
    ]
    cur.executemany("INSERT INTO workers (name, role, phone, is_available) VALUES (?,?,?,?)", workers)
    print("✅ Workers inserted")

    # ── Emergency Contacts ────────────────
    emergency = [
        ('Dr. Sharma', 'Chief Medical Officer', '9988776655', 'Available 24/7 on campus.'),
        ('Campus Security Main', 'Security Force', '9811223344', 'For all immediate security threats.'),
        ('Fire Services', 'Local Fire Dept', '101', 'Direct local line.'),
        ('Local Police', 'Police Station', '100', 'Nearest division.' )
    ]
    cur.executemany("INSERT INTO emergency_contacts (name, role, phone, notes) VALUES (?,?,?,?)", emergency)
    print("✅ Emergency Contacts inserted")

    # ── Sample Complaints ─────────────────────
    complaints = [
        (3,  'Leaking tap in bathroom',  'The tap in Room 1001 bathroom has been leaking for 3 days.',            'plumber', 'pending'),
        (5,  'Broken window latch',      'Window latch in Room 1002 is broken and cannot be closed properly.',    'carpenter', 'in_progress'),
        (16, 'Poor WiFi in Room 3003',   'WiFi signal is very weak in Room 3003, cannot attend online classes.',  'wifi',       'pending'),
        (19, 'Food quality issue',       'Dinner quality was very poor yesterday, rice was undercooked.',         'food',        'resolved'),
        (30, 'Noisy environment',        'Construction noise near Block A is disturbing study hours.',            'other',       'pending'),
    ]
    cur.executemany("INSERT INTO complaints (student_id, title, description, category, status) VALUES (?,?,?,?,?)", complaints)
    print("✅ Complaints inserted")

    # ── Attendance (sample last 3 days for first 10 students) ─────────
    for offset in range(1, 4):
        for sid in range(3, 13):  # first 10 students
            status = 'present' if (sid + offset) % 5 != 0 else 'absent'
            cur.execute("""
                INSERT INTO attendance (student_id, date, status, marked_by)
                VALUES (?, date('now', ?), ?, 1)
            """, (sid, f'-{offset} days', status))
    print("✅ Attendance inserted")

    # ── Notifications ─────────────────────
    cur.executescript("""
        INSERT INTO notifications (sender_id, user_id, title, message, is_read)
            VALUES (1, NULL, 'Hostel Day Celebration', 'Hostel Day will be celebrated on 15th March. All students are requested to participate.', 0);
        INSERT INTO notifications (sender_id, user_id, title, message, is_read)
            VALUES (1, NULL, 'Water Supply Interruption', 'Water supply will be interrupted on 8th March from 8 AM to 12 PM for maintenance.', 0);
        INSERT INTO notifications (sender_id, user_id, title, message, is_read)
            VALUES (1, NULL, 'Mess Menu Change', 'From next week, the mess menu will be updated. New menu will be posted on the notice board.', 1);
    """)
    print("✅ Notifications inserted")

    conn.commit()
    conn.close()

    print(f"\n🎉 Database seeded successfully with {len(raw_students)} students!")
    print(f"📁 Database file: {DB_PATH}")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("  Demo Credentials:")
    print("  Warden:  warden_raj / Warden@123")
    print("  Student: aanya_singh / Student@123")
    print("          (or any other student username)")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━")


if __name__ == '__main__':
    seed()
