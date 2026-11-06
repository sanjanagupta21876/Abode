from flask import Blueprint, render_template, session, redirect, url_for, flash
from services.db import get_cursor
from functools import wraps

bp = Blueprint('student', __name__, url_prefix='/student')


def student_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'student':
            flash('Please log in as a student.', 'warning')
            return redirect(url_for('auth.login', role='student'))
        # Onboarding guard: redirect to wizard if not completed
        cursor = get_cursor()
        cursor.execute("SELECT onboarding_complete FROM users WHERE id = ?", (session['user_id'],))
        row = cursor.fetchone()
        if row and 'onboarding_complete' in row.keys() and not row['onboarding_complete']:
            return redirect(url_for('onboarding.step1'))
        return f(*args, **kwargs)
    return decorated


@bp.route('/dashboard')
@student_required
def dashboard():
    uid = session['user_id']
    cursor = get_cursor()

    # Student profile
    cursor.execute("""
        SELECT u.full_name, u.email, s.roll_number, s.course, s.room_number, s.phone, s.year, s.profile_pic
        FROM users u JOIN students s ON u.id = s.user_id WHERE u.id = ?
    """, (uid,))
    student = cursor.fetchone()

    # Recent complaints
    cursor.execute("""
        SELECT id, title, status, created_at FROM complaints WHERE student_id = ? ORDER BY created_at DESC LIMIT 5
    """, (uid,))
    complaints = cursor.fetchall()

    # Unread notifications
    cursor.execute("""
        SELECT id, title, message, created_at FROM notifications
        WHERE (user_id = ? OR user_id IS NULL) AND is_read = 0 ORDER BY created_at DESC LIMIT 5
    """, (uid,))
    notifications = cursor.fetchall()

    # Attendance summary (last 30 days)
    cursor.execute("""
        SELECT
            SUM(CASE WHEN status = 'present' THEN 1 ELSE 0 END) AS present_count,
            SUM(CASE WHEN status = 'absent' THEN 1 ELSE 0 END)  AS absent_count,
            COUNT(*) AS total_count
        FROM attendance WHERE student_id = ? AND date >= date('now', '-30 days')
    """, (uid,))
    attendance = cursor.fetchone()

    return render_template('student_dashboard.html',
        student=student, complaints=complaints,
        notifications=notifications, attendance=attendance)
