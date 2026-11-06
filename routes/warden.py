from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from werkzeug.security import generate_password_hash
from services.db import get_cursor, commit_db
from services.birthday_service import get_upcoming_birthdays
from services.complaint_router import DEPARTMENTS, DEPARTMENT_LABELS
from functools import wraps

bp = Blueprint('warden', __name__, url_prefix='/warden')


def warden_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'warden':
            flash('Please log in as a warden.', 'warning')
            return redirect(url_for('auth.login', role='warden'))
        return f(*args, **kwargs)
    return decorated


@bp.route('/dashboard')
@warden_required
def dashboard():
    cursor = get_cursor()

    cursor.execute("SELECT COUNT(*) AS cnt FROM students")
    total_students = cursor.fetchone()['cnt']

    cursor.execute("SELECT COUNT(*) AS cnt FROM complaints WHERE status = 'pending'")
    pending_complaints = cursor.fetchone()['cnt']



    cursor.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN status='present' THEN 1 ELSE 0 END), 0) AS present_count,
            COALESCE(SUM(CASE WHEN status='absent' THEN 1 ELSE 0 END), 0) AS absent_count
        FROM attendance WHERE date = date('now')
    """)
    attendance_today = cursor.fetchone()

    cursor.execute("""
        SELECT c.id, u.full_name, s.room_number, c.title, c.category, c.status, c.created_at
        FROM complaints c
        JOIN users u ON c.student_id = u.id
        LEFT JOIN students s ON u.id = s.user_id
        WHERE c.status != 'resolved'
        ORDER BY CASE WHEN c.status IN ('pending', 'unresolved') THEN 1 WHEN c.status = 'in_progress' THEN 2 ELSE 3 END,
                 c.created_at DESC LIMIT 10
    """)
    complaints = cursor.fetchall()



    upcoming_birthdays = get_upcoming_birthdays(days=2)

    return render_template('warden_dashboard.html',
        total_students=total_students, pending_complaints=pending_complaints,
        attendance_today=attendance_today, complaints=complaints,
        upcoming_birthdays=upcoming_birthdays)


@bp.route('/students')
@warden_required
def students():
    cursor = get_cursor()
    cursor.execute("""
        SELECT u.full_name, u.email, s.roll_number, s.course, s.year,
               s.room_number, s.phone,
               COALESCE(s.allergies, 'None') AS allergies
        FROM users u JOIN students s ON u.id = s.user_id
        ORDER BY s.roll_number
    """)
    students = cursor.fetchall()
    return render_template('students_list.html', students=students)


@bp.route('/student-profiles')
@warden_required
def student_profiles():
    cursor = get_cursor()

    # Filter params
    allergy_filter = request.args.get('allergy', '').strip()
    sleep_filter   = request.args.get('sleep', '').strip()
    social_filter  = request.args.get('social', '').strip()

    query = """
        SELECT u.full_name, u.email, s.roll_number, s.course, s.room_number,
               COALESCE(s.allergies, 'None') AS allergies,
               rp.q1 AS sleep_schedule, rp.q2 AS study_env,
               rp.q3 AS cleanliness,   rp.q4 AS social_pref
        FROM users u
        JOIN students s ON u.id = s.user_id
        LEFT JOIN roommate_profiles rp ON u.id = rp.student_id
        WHERE u.role = 'student'
    """
    params = []

    if allergy_filter:
        query += " AND LOWER(COALESCE(s.allergies,'')) LIKE ?"
        params.append(f'%{allergy_filter.lower()}%')
    if sleep_filter:
        query += " AND rp.q1 = ?"
        params.append(str(int(sleep_filter)))
    if social_filter:
        query += " AND rp.q4 = ?"
        params.append(str(int(social_filter)))

    query += " ORDER BY s.roll_number"

    cursor.execute(query, params)
    profiles = cursor.fetchall()

    return render_template('warden/student_profiles.html',
                           profiles=profiles,
                           allergy_filter=allergy_filter,
                           sleep_filter=sleep_filter,
                           social_filter=social_filter)


# ── Staff Management ──────────────────────────────────────────────────────────

@bp.route('/staff')
@warden_required
def manage_staff():
    cursor = get_cursor()
    
    # Get all service staff with their current workload
    cursor.execute("""
        SELECT ss.user_id, u.full_name, u.username, ss.department, ss.active,
               (SELECT COUNT(*) FROM complaints 
                WHERE assigned_staff_id = ss.user_id 
                AND status NOT IN ('resolved')) AS open_complaints,
               (SELECT COUNT(*) FROM complaints 
                WHERE assigned_staff_id = ss.user_id 
                AND status = 'resolved') AS resolved_complaints
        FROM service_staff ss
        JOIN users u ON ss.user_id = u.id
        ORDER BY ss.department, u.full_name
    """)
    staff_list = cursor.fetchall()
    
    return render_template('warden/manage_staff.html', 
                           staff_list=staff_list, 
                           labels=DEPARTMENT_LABELS)


@bp.route('/staff/add', methods=['GET', 'POST'])
@warden_required
def add_staff():
    if request.method == 'POST':
        full_name = request.form.get('full_name', '').strip()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        department = request.form.get('department', '').strip()
        
        if not full_name or not username or not password or not department:
            flash('All fields are required.', 'danger')
            return redirect(url_for('warden.add_staff'))
            
        if department not in DEPARTMENTS:
            flash('Invalid department selected.', 'danger')
            return redirect(url_for('warden.add_staff'))
            
        cursor = get_cursor()
        
        # Check if username exists
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        if cursor.fetchone():
            flash('Username already exists.', 'danger')
            return redirect(url_for('warden.add_staff'))
            
        # Create user
        hashed_pw = generate_password_hash(password)
        # Use a dummy email since staff won't use email auth, but schema requires unique email
        dummy_email = f"staff_{username}@srmist.edu.in"
        
        try:
            cursor.execute("""
                INSERT INTO users (username, password, full_name, email, role)
                VALUES (?, ?, ?, ?, 'service_staff')
            """, (username, hashed_pw, full_name, dummy_email))
            
            user_id = cursor.lastrowid
            
            # Create service_staff record
            cursor.execute("""
                INSERT INTO service_staff (user_id, department, active)
                VALUES (?, ?, 1)
            """, (user_id, department))
            
            commit_db()
            flash(f"Staff account '{full_name}' created successfully.", 'success')
            return redirect(url_for('warden.manage_staff'))
            
        except Exception as e:
            flash(f"Error creating staff account: {e}", 'danger')
            return redirect(url_for('warden.add_staff'))
            
    return render_template('warden/add_staff.html', departments=DEPARTMENTS, labels=DEPARTMENT_LABELS)


@bp.route('/staff/<int:user_id>/toggle', methods=['POST'])
@warden_required
def toggle_staff(user_id):
    cursor = get_cursor()
    
    # Verify this is a staff member
    cursor.execute("SELECT active, department FROM service_staff WHERE user_id = ?", (user_id,))
    staff = cursor.fetchone()
    
    if not staff:
        flash("Staff member not found.", 'danger')
        return redirect(url_for('warden.manage_staff'))
        
    new_status = 0 if staff['active'] == 1 else 1
    
    cursor.execute("UPDATE service_staff SET active = ? WHERE user_id = ?", (new_status, user_id))
    commit_db()
    
    status_text = "activated" if new_status == 1 else "deactivated"
    flash(f"Staff member {status_text} successfully.", 'success')
    return redirect(url_for('warden.manage_staff'))
