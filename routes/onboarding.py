from flask import Blueprint, render_template, session, redirect, url_for, flash, request  # type: ignore
from services.db import get_cursor, commit_db  # type: ignore
from functools import wraps

bp = Blueprint('onboarding', __name__, url_prefix='/onboarding')

# ── Safe schema migrations — called by app.py inside app context ─────────────
def run_migrations():
    cur = get_cursor()
    for sql in [
        "ALTER TABLE users    ADD COLUMN onboarding_complete INTEGER DEFAULT 0",
        "ALTER TABLE students ADD COLUMN allergies TEXT DEFAULT 'None'",
        "ALTER TABLE students ADD COLUMN profile_pic TEXT DEFAULT NULL",
        "ALTER TABLE roommate_profiles ADD COLUMN allergies TEXT DEFAULT ''",
        "ALTER TABLE students ADD COLUMN birth_date DATE DEFAULT NULL",
        "ALTER TABLE students ADD COLUMN room_type TEXT DEFAULT NULL",
        "CREATE TABLE IF NOT EXISTS app_state (key TEXT PRIMARY KEY, value TEXT)",
    ]:
        try:
            cur.execute(sql)
            commit_db()
        except Exception:
            pass  # column/table already exists


# ── Decorator ───────────────────────────────────────────────────────────────
def student_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'student':
            flash('Please log in as a student first.', 'warning')
            return redirect(url_for('auth.login', role='student'))
        return f(*args, **kwargs)
    return decorated


# ── Helpers ─────────────────────────────────────────────────────────────────
def _get_student(uid):
    cur = get_cursor()
    cur.execute("SELECT * FROM students WHERE user_id = ?", (uid,))
    return cur.fetchone()

def _get_user(uid):
    cur = get_cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (uid,))
    return cur.fetchone()


# ── Step 1 — Basic Details ──────────────────────────────────────────────────
@bp.route('/step1', methods=['GET', 'POST'])
@student_required
def step1():
    uid = session['user_id']
    user    = _get_user(uid)
    student = _get_student(uid)

    if request.method == 'POST':
        course      = request.form.get('course', '').strip()
        roll_number = request.form.get('roll_number', '').strip()
        phone       = request.form.get('phone', '').strip()
        room_number = request.form.get('room_number', '').strip()
        year        = request.form.get('year', '1').strip()
        birth_date  = request.form.get('birth_date', '').strip() or None
        room_type   = request.form.get('room_type', '').strip() or None

        # Persist to students table
        cur = get_cursor()
        cur.execute("""
            UPDATE students
            SET course=?, roll_number=?, phone=?, room_number=?, year=?, birth_date=?, room_type=?
            WHERE user_id=?
        """, (course, roll_number, phone, room_number, year, birth_date, room_type, uid))
        commit_db()

        # Cache in session so Back shows the data
        session['ob_step1'] = dict(course=course, roll_number=roll_number,
                                   phone=phone, room_number=room_number, year=year,
                                   birth_date=birth_date or '', room_type=room_type or '')
        
        return redirect(url_for('onboarding.step2')) 
    # Pre-fill: session cache first, then DB row
    pre = session.get('ob_step1', {})
    if not pre and student:
        pre = dict(
            course=student['course'] or '',
            roll_number=student['roll_number'] or '',
            phone=student['phone'] or '',
            room_number=student['room_number'] or '',
            year=str(student['year'] or '1'),
            birth_date=student['birth_date'] or '',
            room_type=student['room_type'] or '',
        )
    return render_template('onboarding.html', step=1,
                           user=user, student=student, pre=pre)


# ── Step 2 — Allergies ──────────────────────────────────────────────────────
@bp.route('/step2', methods=['GET', 'POST'])
@student_required
def step2():
    uid = session['user_id']

    if request.method == 'POST':
        allergies = request.form.get('allergies', '').strip() or 'None'

        cur = get_cursor()
        # 1. Save to students table
        cur.execute("UPDATE students SET allergies=? WHERE user_id=?", (allergies, uid))

        # 2. Also sync to roommate_profiles.allergies
        cur.execute("SELECT student_id FROM roommate_profiles WHERE student_id = ?", (uid,))
        rp = cur.fetchone()
        if rp:
            cur.execute(
                "UPDATE roommate_profiles SET allergies=? WHERE student_id=?",
                (allergies, uid)
            )
        else:
            # Profile doesn't exist yet (Step 3 hasn't run); create a placeholder row
            cur.execute(
                "INSERT INTO roommate_profiles (student_id, q1,q2,q3,q4,q5,q6,q7,q8,q9,q10, allergies) "
                "VALUES (?,2,2,2,2,2,2,2,2,2,3,?)",
                (uid, allergies)
            )
        commit_db()

        session['ob_step2'] = dict(allergies=allergies)
        return redirect(url_for('onboarding.step3'))

    pre = session.get('ob_step2', {})
    if not pre:
        student = _get_student(uid)
        if student:
            allergy_val = student['allergies'] if 'allergies' in student.keys() else 'None'
            pre = dict(allergies=allergy_val if allergy_val != 'None' else '')
    return render_template('onboarding.html', step=2, pre=pre)


# ── Step 3 — Roommate Quiz ──────────────────────────────────────────────────
@bp.route('/step3', methods=['GET', 'POST'])
@student_required
def step3():
    uid = session['user_id']

    if request.method == 'POST':
        # 4 simplified questions mapped to q1–q4 in roommate_profiles
        # q1=sleep, q2=study_env, q3=cleanliness, q4=social
        # remaining q5–q10 default to 2 (middle) if not previously set
        answers = {f'q{i}': int(request.form.get(f'q{i}', 2)) for i in range(1, 5)}

        cur = get_cursor()
        cur.execute("SELECT student_id FROM roommate_profiles WHERE student_id = ?", (uid,))
        profile = cur.fetchone()

        if profile:
            cur.execute("""
                UPDATE roommate_profiles
                SET q1=?, q2=?, q3=?, q4=?, updated_at=CURRENT_TIMESTAMP
                WHERE student_id=?
            """, (answers['q1'], answers['q2'], answers['q3'], answers['q4'], uid))
        else:
            # Insert with defaults for q5–q10
            cur.execute("""
                INSERT INTO roommate_profiles
                    (student_id, q1, q2, q3, q4, q5, q6, q7, q8, q9, q10)
                VALUES (?, ?, ?, ?, ?, 2, 2, 2, 2, 2, 3)
            """, (uid, answers['q1'], answers['q2'], answers['q3'], answers['q4']))

        # Mark onboarding complete
        cur.execute("UPDATE users SET onboarding_complete=1 WHERE id=?", (uid,))
        commit_db()

        # Clear onboarding session state
        for key in ['ob_step1', 'ob_step2']:
            session.pop(key, None)

        flash('Welcome aboard! Your profile is all set. 🎉', 'success')
        return redirect(url_for('student.dashboard'))

    pre = {}
    cur = get_cursor()
    cur.execute("SELECT * FROM roommate_profiles WHERE student_id = ?", (uid,))
    profile = cur.fetchone()
    if profile:
        pre = {f'q{i}': profile[f'q{i}'] for i in range(1, 5)}

    return render_template('onboarding.html', step=3, pre=pre)
