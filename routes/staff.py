from flask import Blueprint, render_template, session, redirect, url_for, flash, request, abort
from services.db import get_cursor, commit_db
from services.complaint_router import (
    DEPARTMENTS, DEPARTMENT_LABELS, DEPARTMENT_EMOJIS,
    notify_student_status
)
from functools import wraps

bp = Blueprint('staff', __name__, url_prefix='/staff')


# ── Auth decorator ────────────────────────────────────────────────────────────

def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'service_staff':
            flash('Please log in as service staff.', 'warning')
            return redirect(url_for('auth.login', role='service_staff'))
        return f(*args, **kwargs)
    return decorated


# ── Dashboard ─────────────────────────────────────────────────────────────────

@bp.route('/dashboard')
@staff_required
def dashboard():
    cursor = get_cursor()
    department = session.get('staff_department')

    # Stats for this department
    cursor.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status NOT IN ('resolved') THEN 1 ELSE 0 END) AS open_count,
            SUM(CASE WHEN status = 'pending'     THEN 1 ELSE 0 END) AS pending,
            SUM(CASE WHEN status = 'in_progress' THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN status = 'resolved'    THEN 1 ELSE 0 END) AS resolved,
            SUM(CASE WHEN status NOT IN ('resolved')
                      AND datetime(created_at) < datetime('now', '-48 hours')
                 THEN 1 ELSE 0 END) AS overdue
        FROM complaints
        WHERE department = ?
    """, (department,))
    stats = cursor.fetchone()

    status_filter   = request.args.get('status',   'open')
    priority_filter = request.args.get('priority', 'all')

    query = """
        SELECT c.id, c.title, c.category, c.status, c.priority,
               c.location, c.description, c.created_at, c.assigned_staff_id,
               s.room_number
        FROM complaints c
        LEFT JOIN students s ON c.student_id = s.user_id
        WHERE c.department = ?
    """
    params = [department]

    if status_filter == 'open':
        query += " AND c.status NOT IN ('resolved')"
    elif status_filter in ('pending', 'in_progress', 'resolved'):
        query += " AND c.status = ?"
        params.append(status_filter)

    if priority_filter in ('low', 'normal', 'high', 'urgent'):
        query += " AND c.priority = ?"
        params.append(priority_filter)

    query += (
        " ORDER BY"
        " CASE WHEN c.priority='urgent' THEN 1 WHEN c.priority='high' THEN 2"
        " WHEN c.priority='normal' THEN 3 ELSE 4 END,"
        " c.created_at ASC"
    )

    cursor.execute(query, params)
    complaints = cursor.fetchall()

    dept_label = DEPARTMENT_LABELS.get(department, department)
    dept_emoji = DEPARTMENT_EMOJIS.get(department, '🔔')

    return render_template('staff/dashboard.html',
        complaints=complaints, stats=stats,
        department=department, dept_label=dept_label, dept_emoji=dept_emoji,
        status_filter=status_filter, priority_filter=priority_filter)


# ── Complaint detail ──────────────────────────────────────────────────────────

@bp.route('/complaint/<int:complaint_id>')
@staff_required
def view_complaint(complaint_id):
    cursor = get_cursor()
    department = session.get('staff_department')

    cursor.execute("""
        SELECT c.id, c.title, c.category, c.status, c.priority, c.location,
               c.description, c.created_at, c.updated_at, c.department,
               c.assigned_staff_id, c.resolution_note, c.resolved_at,
               s.room_number
        FROM complaints c
        LEFT JOIN students s ON c.student_id = s.user_id
        WHERE c.id = ?
    """, (complaint_id,))
    complaint = cursor.fetchone()

    if not complaint:
        abort(404)

    # ── CRITICAL: server-side department boundary check ──
    if complaint['department'] != department:
        abort(403)

    dept_label = DEPARTMENT_LABELS.get(department, department)
    dept_emoji = DEPARTMENT_EMOJIS.get(department, '🔔')

    return render_template('staff/complaint_detail.html',
        complaint=complaint,
        dept_label=dept_label, dept_emoji=dept_emoji)


# ── Update complaint status ───────────────────────────────────────────────────

@bp.route('/complaint/<int:complaint_id>/update', methods=['POST'])
@staff_required
def update_complaint(complaint_id):
    cursor = get_cursor()
    department = session.get('staff_department')

    cursor.execute(
        "SELECT id, student_id, department, status FROM complaints WHERE id = ?",
        (complaint_id,)
    )
    complaint = cursor.fetchone()

    if not complaint:
        abort(404)

    # ── CRITICAL: server-side department boundary check ──
    if complaint['department'] != department:
        abort(403)

    new_status      = request.form.get('status', '').strip()
    resolution_note = request.form.get('resolution_note', '').strip() or None
    current_status  = complaint['status']

    # Validate status transitions — no skipping, no going backwards
    allowed_transitions = {
        'pending':     ('in_progress',),
        'assigned':    ('in_progress',),
        'in_progress': ('resolved',),
        'resolved':    (),
        'unresolved':  ('in_progress',),
    }
    allowed = allowed_transitions.get(current_status, ())

    if new_status not in allowed:
        flash(f'Cannot change status from "{current_status}" to "{new_status}".', 'danger')
        return redirect(url_for('staff.view_complaint', complaint_id=complaint_id))

    if new_status == 'resolved':
        cursor.execute("""
            UPDATE complaints
            SET status = ?, resolution_note = ?,
                resolved_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_status, resolution_note, complaint_id))
    else:
        cursor.execute("""
            UPDATE complaints
            SET status = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_status, complaint_id))

    notify_student_status(cursor, complaint_id, complaint['student_id'],
                          new_status, resolution_note)
    commit_db()

    flash(f'Complaint #{complaint_id} updated to '
          f'"{new_status.replace("_", " ").title()}".', 'success')
    return redirect(url_for('staff.dashboard'))
