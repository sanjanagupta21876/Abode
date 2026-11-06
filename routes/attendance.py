from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from services.db import get_cursor, commit_db
from datetime import date, datetime
from functools import wraps

bp = Blueprint('attendance', __name__, url_prefix='/attendance')


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@bp.route('/')
@login_required
def view():
    cursor = get_cursor()
    uid = session['user_id']
    role = session['role']

    if role == 'warden':
        selected = request.args.get('date', str(date.today()))
        try:
            datetime.strptime(selected, '%Y-%m-%d')
        except ValueError:
            selected = str(date.today())
        cursor.execute("""
            SELECT u.id AS user_id, u.full_name, s.roll_number, s.room_number,
                   a.date, a.status, a.marked_at
            FROM users u
            JOIN students s ON u.id = s.user_id
            LEFT JOIN attendance a ON u.id = a.student_id AND a.date = ?
            ORDER BY s.roll_number
        """, (selected,))
        rows = cursor.fetchall()
        now = datetime.now()
        records = []
        for r in rows:
            row = dict(r)
            marked_at = row.get('marked_at')
            editable = False
            if marked_at:
                try:
                    mt = datetime.strptime(marked_at, '%Y-%m-%d %H:%M:%S')
                    editable = (now - mt).total_seconds() <= 24 * 60 * 60
                except (ValueError, TypeError):
                    editable = False
            else:
                editable = (selected == str(date.today()))
            row['is_editable'] = editable
            records.append(row)
        return render_template('attendance.html', records=records, role='warden', selected_date=selected)
    else:
        cursor.execute("""
            SELECT date, status FROM attendance WHERE student_id = ? ORDER BY date DESC LIMIT 30
        """, (uid,))
        records = cursor.fetchall()
        cursor.execute("""
            SELECT
                COALESCE(SUM(CASE WHEN status='present' THEN 1 ELSE 0 END), 0) AS present,
                COALESCE(SUM(CASE WHEN status='absent' THEN 1 ELSE 0 END), 0) AS absent,
                COUNT(*) AS total
            FROM attendance WHERE student_id = ? AND date >= date('now', '-30 days')
        """, (uid,))
        summary = cursor.fetchone()
        return render_template('attendance.html', records=records, role='student', summary=summary)


@bp.route('/mark', methods=['POST'])
@login_required
def mark():
    if session.get('role') != 'warden':
        flash('Only wardens can mark attendance.', 'danger')
        return redirect(url_for('attendance.view'))

    student_ids = request.form.getlist('student_ids[]')
    statuses    = request.form.getlist('statuses[]')
    marked_by   = session['user_id']
    mark_date   = request.form.get('attendance_date') or str(date.today())
    try:
        datetime.strptime(mark_date, '%Y-%m-%d')
    except ValueError:
        mark_date = str(date.today())

    cursor = get_cursor()
    for sid, status in zip(student_ids, statuses):
        cursor.execute("""
            INSERT INTO attendance (student_id, date, status, marked_by)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(student_id, date) DO UPDATE SET status = excluded.status, marked_by = excluded.marked_by
        """, (sid, mark_date, status, marked_by))

    commit_db()
    flash(f"Attendance marked for {len(student_ids)} students.", 'success')
    return redirect(url_for('attendance.view', date=mark_date))