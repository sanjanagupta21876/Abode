from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from services.db import get_cursor, commit_db
from services.complaint_router import route_complaint
from functools import wraps

bp = Blueprint('complaint', __name__, url_prefix='/complaint')


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@bp.route('/', methods=['GET'])
@login_required
def list_complaints():
    cursor = get_cursor()
    uid = session['user_id']
    role = session['role']
    
    if role == 'warden':
        status_filter = request.args.get('status', 'active')
        category_filter = request.args.get('category', 'all')
        time_filter = request.args.get('time', 'all')
        
        query = """
            SELECT c.id, u.full_name, s.room_number, c.title, c.category, c.status, c.created_at,
                   c.priority, c.location, c.department, c.assigned_staff_id,
                   (SELECT u2.full_name FROM users u2 WHERE u2.id = c.assigned_staff_id) AS staff_name
            FROM complaints c
            JOIN users u ON c.student_id = u.id
            JOIN students s ON u.id = s.user_id
            WHERE 1=1
        """
        params = []
        
        if status_filter == 'active':
            query += " AND c.status IN ('pending', 'in_progress', 'unresolved')"
        elif status_filter in ['pending', 'in_progress', 'unresolved', 'resolved']:
            query += " AND c.status = ?"
            params.append(status_filter)
            
        if category_filter != 'all':
            query += " AND c.category = ?"
            params.append(category_filter)
            
        if time_filter == 'today':
            query += " AND date(c.created_at) = date('now')"
        elif time_filter == 'week':
            query += " AND date(c.created_at) >= date('now', '-7 days')"
            
        query += " ORDER BY CASE WHEN c.status IN ('pending', 'unresolved') THEN 1 WHEN c.status = 'in_progress' THEN 2 ELSE 3 END, c.created_at DESC"
        cursor.execute(query, params)
    else:
        cursor.execute("""
            SELECT c.id, c.title, c.category, c.description, c.status, c.created_at,
                   c.priority, c.location, c.department
            FROM complaints c WHERE c.student_id = ? ORDER BY c.created_at DESC
        """, (uid,))
        
    complaints = cursor.fetchall()
    return render_template('complaint.html', complaints=complaints, role=role)


@bp.route('/submit', methods=['GET', 'POST'])
@login_required
def submit():
    if session.get('role') != 'student':
        flash('Only students can submit complaints.', 'warning')
        return redirect(url_for('complaint.list_complaints'))

    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category    = request.form.get('category', 'other')
        priority    = request.form.get('priority', 'normal')
        location    = request.form.get('location', '').strip() or None
        uid         = session['user_id']

        if not title or not description:
            flash('Please fill in all fields.', 'danger')
            return render_template('complaint_form.html')

        cursor = get_cursor()
        cursor.execute(
            "INSERT INTO complaints (student_id, title, description, category, priority, location) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, title, description, category, priority, location)
        )
        complaint_id = cursor.lastrowid

        # Auto-route complaint to the appropriate department / staff
        route_complaint(cursor, complaint_id, category, uid,
                        location=location, title=title, priority=priority)

        # Legacy: urgent water notifications to wardens
        if category in ('hot_water', 'cold_water'):
            label = '🔥 Hot Water' if category == 'hot_water' else '❄️ Cold Water'
            notif_title = f"🚨 PRIORITY: {label} Complaint"
            notif_msg = f"{label} complaint — \"{title}\" — requires urgent attention!"
            cursor.execute("SELECT id FROM users WHERE role = 'warden'")
            warden_rows = cursor.fetchall()
            for w in warden_rows:
                cursor.execute(
                    "INSERT INTO notifications (sender_id, user_id, title, message) VALUES (?, ?, ?, ?)",
                    (uid, w['id'], notif_title, notif_msg)
                )

        commit_db()
        flash('Complaint submitted successfully!', 'success')
        return redirect(url_for('complaint.list_complaints'))

    return render_template('complaint_form.html')


@bp.route('/update/<int:complaint_id>', methods=['POST'])
@login_required
def update_status(complaint_id):
    if session.get('role') != 'warden':
        flash('Only wardens can update complaint status.', 'danger')
        return redirect(url_for('complaint.list_complaints'))

    new_status = request.form.get('status')
    
    if new_status == 'resolved':
        flash('Wardens cannot mark complaints as Done. Only students can confirm resolution.', 'warning')
        return redirect(url_for('complaint.list_complaints'))
        
    cursor = get_cursor()
    cursor.execute("UPDATE complaints SET status = ? WHERE id = ?", (new_status, complaint_id))
    commit_db()
    flash('Complaint status updated.', 'success')
    return redirect(url_for('complaint.list_complaints'))

@bp.route('/student_action/<int:complaint_id>', methods=['POST'])
@login_required
def student_action(complaint_id):
    if session.get('role') != 'student':
        flash('Only students can confirm complaint resolution.', 'danger')
        return redirect(url_for('complaint.list_complaints'))

    action = request.form.get('action')
    uid = session['user_id']
    
    cursor = get_cursor()
    # Verify ownership
    cursor.execute("SELECT id FROM complaints WHERE id = ? AND student_id = ?", (complaint_id, uid))
    if not cursor.fetchone():
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('complaint.list_complaints'))
        
    new_status = 'resolved' if action == 'done' else 'unresolved'
    
    cursor.execute("UPDATE complaints SET status = ? WHERE id = ?", (new_status, complaint_id))
    commit_db()
    
    msg = 'Complaint marked as resolved.' if action == 'done' else 'Complaint marked as unresolved. Warden will be notified.'
    flash(msg, 'success' if action == 'done' else 'warning')
    return redirect(url_for('complaint.list_complaints'))


@bp.route('/edit/<int:complaint_id>', methods=['GET', 'POST'])
@login_required
def edit(complaint_id):
    if session.get('role') != 'student':
        flash('Only students can edit complaints.', 'danger')
        return redirect(url_for('complaint.list_complaints'))

    uid = session['user_id']
    cursor = get_cursor()

    # Retrieve complaint and verify ownership and pending status
    cursor.execute("""
        SELECT id, title, description, category, status 
        FROM complaints 
        WHERE id = ? AND student_id = ?
    """, (complaint_id, uid))
    complaint = cursor.fetchone()

    if not complaint:
        flash('Complaint not found or unauthorized.', 'danger')
        return redirect(url_for('complaint.list_complaints'))

    if complaint['status'] not in ('pending', 'unresolved', 'assigned'):
        flash('Only pending or unresolved complaints can be edited.', 'warning')
        return redirect(url_for('complaint.list_complaints'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        category = request.form.get('category', 'other')

        if not title or not description:
            flash('Please fill in all fields.', 'danger')
            return render_template('complaint_form.html', complaint=complaint)

        # Re-route if category changed
        priority = request.form.get('priority', 'normal')
        location = request.form.get('location', '').strip() or None

        # 1. Clean up any existing notifications associated with this complaint's previous title
        cursor.execute(
            "DELETE FROM notifications WHERE sender_id = ? AND message LIKE ?",
            (uid, f'%"{complaint["title"]}"%')
        )

        # 2. Update the complaint in the database
        cursor.execute("""
            UPDATE complaints
            SET title = ?, description = ?, category = ?,
                priority = ?, location = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (title, description, category, priority, location, complaint_id))

        # 3. Re-route to department (handles category change)
        route_complaint(cursor, complaint_id, category, uid,
                        location=location, title=title, priority=priority)

        # 4. If new category is water-related, trigger priority notifications to wardens
        if category in ('hot_water', 'cold_water'):
            label = '🔥 Hot Water' if category == 'hot_water' else '❄️ Cold Water'
            notif_title = f"🚨 PRIORITY: {label} Complaint"
            notif_msg = f"{label} complaint — \"{title}\" — requires urgent attention!"
            cursor.execute("SELECT id FROM users WHERE role = 'warden'")
            warden_rows = cursor.fetchall()
            for w in warden_rows:
                cursor.execute(
                    "INSERT INTO notifications (sender_id, user_id, title, message) VALUES (?, ?, ?, ?)",
                    (uid, w['id'], notif_title, notif_msg)
                )

        commit_db()
        flash('Complaint updated successfully!', 'success')
        return redirect(url_for('complaint.list_complaints'))

    return render_template('complaint_form.html', complaint=complaint)


@bp.route('/delete/<int:complaint_id>', methods=['POST'])
@login_required
def delete(complaint_id):
    if session.get('role') != 'student':
        flash('Only students can delete complaints.', 'danger')
        return redirect(url_for('complaint.list_complaints'))

    uid = session['user_id']
    cursor = get_cursor()

    # Retrieve complaint and verify ownership and pending status
    cursor.execute("""
        SELECT id, title, status 
        FROM complaints 
        WHERE id = ? AND student_id = ?
    """, (complaint_id, uid))
    complaint = cursor.fetchone()

    if not complaint:
        flash('Complaint not found or unauthorized.', 'danger')
        return redirect(url_for('complaint.list_complaints'))

    if complaint['status'] not in ('pending', 'unresolved'):
        flash('Only pending or unresolved complaints can be deleted.', 'warning')
        return redirect(url_for('complaint.list_complaints'))

    # Clean up associated notifications
    cursor.execute(
        "DELETE FROM notifications WHERE sender_id = ? AND message LIKE ?",
        (uid, f'%"{complaint["title"]}"%')
    )

    # Delete the complaint
    cursor.execute("DELETE FROM complaints WHERE id = ?", (complaint_id,))
    commit_db()

    flash('Complaint deleted successfully!', 'success')
    return redirect(url_for('complaint.list_complaints'))
