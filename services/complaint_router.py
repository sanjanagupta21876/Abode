"""
Complaint routing service: maps categories to departments, assigns staff,
sends notifications. All DB functions accept a cursor; caller must commit.
"""

from services.db import get_cursor, commit_db

# ── Department constants ──────────────────────────────────────────────────────

DEPARTMENTS = [
    'ELECTRICIAN',
    'PLUMBER',
    'CARPENTER',
    'WIFI_TECHNICIAN',
    'HOUSEKEEPING',
    'GENERAL_MAINTENANCE',
]

DEPARTMENT_LABELS = {
    'ELECTRICIAN':         'Electrician',
    'PLUMBER':             'Plumber',
    'CARPENTER':           'Carpenter',
    'WIFI_TECHNICIAN':     'Wi-Fi Technician',
    'HOUSEKEEPING':        'Housekeeping',
    'GENERAL_MAINTENANCE': 'General Maintenance',
}

DEPARTMENT_EMOJIS = {
    'ELECTRICIAN':         '⚡',
    'PLUMBER':             '🔧',
    'CARPENTER':           '🪚',
    'WIFI_TECHNICIAN':     '📶',
    'HOUSEKEEPING':        '🧹',
    'GENERAL_MAINTENANCE': '🔨',
}

# Existing complaint categories → department
CATEGORY_DEPARTMENT_MAP = {
    'electrician':  'ELECTRICIAN',
    'plumber':      'PLUMBER',
    'hot_water':    'PLUMBER',
    'cold_water':   'PLUMBER',
    'carpenter':    'CARPENTER',
    'wifi':         'WIFI_TECHNICIAN',
    'cleanliness':  'HOUSEKEEPING',
    'laundry':      'HOUSEKEEPING',
    'food':         'GENERAL_MAINTENANCE',
    'security':     'GENERAL_MAINTENANCE',
    'other':        'GENERAL_MAINTENANCE',
}


def get_department(category):
    """Return the department string for a given complaint category."""
    return CATEGORY_DEPARTMENT_MAP.get((category or 'other').lower(), 'GENERAL_MAINTENANCE')


def assign_staff(cursor, department):
    """
    Find the active staff member in the given department with the fewest
    open (non-resolved) complaints. Uses least-load assignment.
    Returns user_id or None if no active staff exists.
    """
    cursor.execute("""
        SELECT ss.user_id,
               COUNT(c.id) AS open_count
        FROM service_staff ss
        LEFT JOIN complaints c
            ON c.assigned_staff_id = ss.user_id
           AND c.status NOT IN ('resolved')
        WHERE ss.department = ? AND ss.active = 1
        GROUP BY ss.user_id
        ORDER BY open_count ASC
        LIMIT 1
    """, (department,))
    row = cursor.fetchone()
    return row['user_id'] if row else None


def route_complaint(cursor, complaint_id, category, sender_id, location=None, title='', priority='normal'):
    """
    Auto-route a complaint:
      - Determine department from category
      - Find least-loaded active staff member
      - Update complaint record (department + assigned_staff_id)
      - Send notification to staff (or warden if no staff available)

    Returns (department, assigned_staff_id). Caller must commit.
    """
    department = get_department(category)
    staff_user_id = assign_staff(cursor, department)

    if staff_user_id:
        cursor.execute("""
            UPDATE complaints
            SET department = ?, assigned_staff_id = ?
            WHERE id = ?
        """, (department, staff_user_id, complaint_id))

        dept_emoji = DEPARTMENT_EMOJIS.get(department, '🔔')
        priority_label = priority.upper() if priority and priority != 'normal' else ''
        notif_title = f"{dept_emoji} New Complaint Assigned"
        notif_msg = (
            f"A new complaint has been assigned to you.\n"
            f"Location: {location or 'Not specified'}\n"
            f"Issue: {title}"
            + (f"\nPriority: {priority_label}" if priority_label else "")
        )
        cursor.execute(
            "INSERT INTO notifications (sender_id, user_id, title, message) VALUES (?, ?, ?, ?)",
            (sender_id, staff_user_id, notif_title, notif_msg)
        )
    else:
        # No active staff — keep pending, notify all wardens
        cursor.execute("""
            UPDATE complaints SET department = ? WHERE id = ?
        """, (department, complaint_id))

        dept_label = DEPARTMENT_LABELS.get(department, department)
        notif_title = f"⚠️ No Staff Available — {dept_label}"
        notif_msg = (
            f"A {dept_label} complaint was submitted but no active staff is available.\n"
            f"Location: {location or 'Not specified'}\n"
            f"Issue: {title}\n"
            f"Please assign staff or handle manually."
        )
        cursor.execute("SELECT id FROM users WHERE role = 'warden'")
        for w in cursor.fetchall():
            cursor.execute(
                "INSERT INTO notifications (sender_id, user_id, title, message) VALUES (?, ?, ?, ?)",
                (sender_id, w['id'], notif_title, notif_msg)
            )

    return department, staff_user_id


def notify_student_status(cursor, complaint_id, student_id, new_status, resolution_note=None):
    """
    Notify the student when their complaint status changes to in_progress or resolved.
    """
    if new_status == 'in_progress':
        title = f"🔄 Complaint #{complaint_id} — In Progress"
        msg = f"Your complaint #{complaint_id} is now being worked on by our maintenance team!"
    elif new_status == 'resolved':
        title = f"✅ Complaint #{complaint_id} — Resolved"
        msg = f"Your complaint #{complaint_id} has been resolved."
        if resolution_note:
            msg += f"\n\nResolution: {resolution_note}"
    else:
        return  # No notification for other transitions

    cursor.execute(
        "INSERT INTO notifications (sender_id, user_id, title, message) VALUES (?, ?, ?, ?)",
        (None, student_id, title, msg)
    )


def initialize_staff_schema():
    """
    Create service_staff table and add new columns to complaints.
    Safe to call multiple times — all operations are idempotent.
    """
    cursor = get_cursor()

    # Create service_staff table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS service_staff (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id   INTEGER UNIQUE NOT NULL,
            department TEXT NOT NULL,
            active    INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Add new columns to complaints (ignore errors if column already exists)
    new_columns = [
        ("department",        "TEXT    DEFAULT NULL"),
        ("priority",          "TEXT    DEFAULT 'normal'"),
        ("location",          "TEXT    DEFAULT NULL"),
        ("assigned_staff_id", "INTEGER DEFAULT NULL"),
        ("resolution_note",   "TEXT    DEFAULT NULL"),
        ("resolved_at",       "TIMESTAMP DEFAULT NULL"),
    ]
    for col_name, col_def in new_columns:
        try:
            cursor.execute(f"ALTER TABLE complaints ADD COLUMN {col_name} {col_def}")
        except Exception:
            pass  # Column already exists — skip silently

    commit_db()
