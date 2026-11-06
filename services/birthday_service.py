from datetime import date, datetime
from services.db import get_cursor, commit_db


def _today_str():
    return str(date.today())


def _get_last_run(cursor):
    try:
        cursor.execute("SELECT value FROM app_state WHERE key = 'last_birthday_run'")
        row = cursor.fetchone()
        return row['value'] if row else None
    except Exception:
        return None


def _set_last_run(cursor, today):
    cursor.execute(
        "INSERT INTO app_state (key, value) VALUES ('last_birthday_run', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (today,)
    )


def _birthday_greeting():
    return "Wishing you a wonderful year ahead!"


def create_birthday_notifications():
    """Create one birthday notification for each student whose birthday is today."""
    today = _today_str()
    cursor = get_cursor()

    # Ensure app_state table exists (safe even if migrations are skipped)
    try:
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT)"
        )
    except Exception:
        pass

    if _get_last_run(cursor) == today:
        return

    cursor.execute("""
        SELECT u.id AS user_id, u.full_name
        FROM users u
        JOIN students s ON u.id = s.user_id
        WHERE s.birth_date IS NOT NULL
          AND strftime('%m-%d', s.birth_date) = strftime('%m-%d', 'now')
    """)
    birthday_students = cursor.fetchall()

    for student in birthday_students:
        cursor.execute("""
            INSERT INTO notifications (sender_id, user_id, title, message)
            VALUES (NULL, ?, ?, ?)
        """, (
            student['user_id'],
            f"Happy Birthday, {student['full_name']}!",
            _birthday_greeting()
        ))

    _set_last_run(cursor, today)
    commit_db()


def _next_birthday(birth_date_str):
    try:
        birth = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None
    today = date.today()
    next_bday = birth.replace(year=today.year)
    if next_bday < today:
        next_bday = birth.replace(year=today.year + 1)
    return next_bday


def get_upcoming_birthdays(days=2):
    """Return students whose next birthday is within the next N days."""
    cursor = get_cursor()
    cursor.execute("""
        SELECT u.full_name, s.birth_date
        FROM users u
        JOIN students s ON u.id = s.user_id
        WHERE s.birth_date IS NOT NULL
    """)
    today = date.today()
    upcoming = []
    for row in cursor.fetchall():
        nxt = _next_birthday(row['birth_date'])
        if nxt is None:
            continue
        delta = (nxt - today).days
        if 0 <= delta <= days:
            upcoming.append({
                'full_name': row['full_name'],
                'birth_date': row['birth_date'],
                'days_until': delta
            })
    upcoming.sort(key=lambda x: (x['days_until'], x['full_name']))
    return upcoming
