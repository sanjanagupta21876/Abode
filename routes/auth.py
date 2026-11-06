import os
import secrets
import time
from flask import Blueprint, request, session, redirect, url_for, render_template, flash
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from services.db import get_cursor, commit_db
from services.email_service import send_otp_email
from services.complaint_router import initialize_staff_schema

bp = Blueprint('auth', __name__, url_prefix='/auth')

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    '..', 'static', 'uploads', 'profile_pics'
)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def normalize_email(email):
    email = email.strip().lower()
    return email if '@' in email else f'{email}@srmist.edu.in'


def issue_otp(email, purpose):
    code = f'{secrets.randbelow(1_000_000):06d}'
    session['otp_hash'] = generate_password_hash(code)
    session['otp_email'] = email
    session['otp_purpose'] = purpose
    session['otp_clock'] = 'monotonic_v1'
    session['otp_expires_at'] = time.monotonic() + 600
    session['otp_attempts'] = 0
    return code


def verify_session_otp(code, purpose):
    if session.get('otp_purpose') != purpose:
        return False, 'Request a new verification code.'
    if session.get('otp_clock') != 'monotonic_v1' or session.get('otp_expires_at') is None:
        return False, 'Your verification session was refreshed. Request a new code.'
    if time.monotonic() > session['otp_expires_at']:
        return False, 'This code has expired. Request a new one.'
    if session.get('otp_attempts', 0) >= 5:
        return False, 'Too many attempts. Request a new verification code.'
    normalized_code = ''.join(str(code).split())
    if not check_password_hash(session.get('otp_hash', ''), normalized_code):
        session['otp_attempts'] = session.get('otp_attempts', 0) + 1
        remaining = 5 - session['otp_attempts']
        return False, f'Invalid code. {remaining} attempt(s) remaining.'
    for key in ('otp_hash', 'otp_clock', 'otp_expires_at', 'otp_attempts'):
        session.pop(key, None)
    return True, None


def registered_hostel_member(email):
    cursor = get_cursor()
    cursor.execute('SELECT 1 FROM hostel_members WHERE email = ? AND active = 1', (email,))
    return cursor.fetchone() is not None


def initialize_auth_schema():
    from services.db import get_db
    db = get_db()
    cursor = db.cursor()

    cursor.execute('CREATE TABLE IF NOT EXISTS hostel_members (email TEXT PRIMARY KEY, full_name TEXT, active INTEGER NOT NULL DEFAULT 1)')
    db.commit()

    # ── Migration 1: fix users.role CHECK constraint to include 'service_staff' ──
    # IMPORTANT: disable FK enforcement so SQLite does NOT auto-rewrite FK
    # references in child tables when we rename the users table.
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='users'")
    row = cursor.fetchone()
    users_ddl = row[0] if row else ''

    if 'service_staff' not in users_ddl and 'CHECK' in users_ddl:
        db.execute("PRAGMA foreign_keys = OFF")
        try:
            db.execute("ALTER TABLE users RENAME TO _users_old")
            db.execute("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    role TEXT CHECK(role IN ('student','warden','service_staff')) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    onboarding_complete INTEGER DEFAULT 0
                )
            """)
            db.execute("""
                INSERT INTO users
                    (id, username, password, full_name, email, role,
                     created_at, onboarding_complete)
                SELECT id, username, password, full_name, email, role,
                       created_at, COALESCE(onboarding_complete, 0)
                FROM _users_old
            """)
            db.execute("DROP TABLE _users_old")
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.execute("PRAGMA foreign_keys = ON")

    # ── Migration 2: fix service_staff FK if it wrongly references _users_old ──
    # This repairs the side-effect of a previous migration that ran with FK ON.
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='service_staff'")
    row = cursor.fetchone()
    ss_ddl = row[0] if row else ''

    if '_users_old' in ss_ddl:
        db.execute("PRAGMA foreign_keys = OFF")
        try:
            db.execute("ALTER TABLE service_staff RENAME TO _service_staff_old")
            db.execute("""
                CREATE TABLE service_staff (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id   INTEGER UNIQUE NOT NULL,
                    department TEXT NOT NULL,
                    active    INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            db.execute("""
                INSERT INTO service_staff
                    (id, user_id, department, active, created_at)
                SELECT id, user_id, department, active, created_at
                FROM _service_staff_old
            """)
            db.execute("DROP TABLE _service_staff_old")
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.execute("PRAGMA foreign_keys = ON")

    # Initialize service staff schema (idempotent)
    initialize_staff_schema()


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role     = request.form.get('role', 'student')

        if not username or not password:
            flash('Please enter both username and password.', 'danger')
            return render_template('login.html', role=role)

        cursor = get_cursor()
        cursor.execute("SELECT * FROM users WHERE username = ? AND role = ?", (username, role))
        user = cursor.fetchone()

        if user and check_password_hash(user['password'], password):
            session['user_id']   = user['id']
            session['username']  = user['username']
            session['full_name'] = user['full_name']
            session['role']      = user['role']

            # Fetch profile picture for student
            if role == 'student':
                cursor.execute("SELECT profile_pic FROM students WHERE user_id = ?", (user['id'],))
                stud_row = cursor.fetchone()
                if stud_row and stud_row['profile_pic']:
                    session['profile_pic'] = stud_row['profile_pic']
                else:
                    session['profile_pic'] = None
            else:
                session['profile_pic'] = None

            flash(f"Welcome back, {user['full_name']}!", 'success')

            if role == 'warden':
                return redirect(url_for('warden.dashboard'))
            elif role == 'service_staff':
                # Fetch and store department in session
                cursor.execute(
                    "SELECT department FROM service_staff WHERE user_id = ?",
                    (user['id'],)
                )
                staff_row = cursor.fetchone()
                if not staff_row:
                    flash('Your staff account has no department assigned. Contact the warden.', 'danger')
                    session.clear()
                    return render_template('login.html', role=role)
                if not staff_row['department']:
                    flash('Your staff account is inactive. Contact the warden.', 'danger')
                    session.clear()
                    return render_template('login.html', role=role)
                session['staff_department'] = staff_row['department']
                return redirect(url_for('staff.dashboard'))
            else:
                onboarding_done = user['onboarding_complete'] if 'onboarding_complete' in user.keys() else 1
                if not onboarding_done:
                    return redirect(url_for('onboarding.step1'))
                return redirect(url_for('student.dashboard'))
        else:
            flash('Invalid credentials. Please check your username and password.', 'danger')

    return render_template('login.html', role=request.args.get('role', 'student'))


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        full_name   = request.form.get('full_name', '').strip()
        email       = normalize_email(request.form.get('email', ''))
        password    = request.form.get('password', '')
        roll_number = request.form.get('roll_number', '').strip()
        course      = request.form.get('course', '').strip()
        room_number = request.form.get('room_number', '').strip()
        phone       = request.form.get('phone', '').strip()
        year        = request.form.get('year', '1').strip()
        birth_date  = request.form.get('birth_date', '').strip() or None
        room_type   = request.form.get('room_type', '').strip() or None
        allergies   = request.form.get('allergies', '').strip()
        q1 = int(request.form.get('q1', 2))
        q2 = int(request.form.get('q2', 2))
        q3 = int(request.form.get('q3', 2))
        q4 = int(request.form.get('q4', 2))

        # Check required fields
        if not full_name or not email or not password or not allergies:
            flash('Name, email, password, and allergy details are required.', 'danger')
            return render_template('register.html')

        if not email.endswith('@srmist.edu.in'):
            flash('Please use your official @srmist.edu.in email address.', 'danger')
            return render_template('register.html')

        if not registered_hostel_member(email):
            flash('You are not a registered hostel member. Please contact the hostel office.', 'danger')
            return render_template('register.html')

        if session.get('registration_verified_email') != email:
            flash('Please verify your official email via OTP first.', 'danger')
            return render_template('register.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('register.html')

        # Derive username from email prefix
        username = email.split('@')[0]

        # Handle profile picture upload
        profile_pic_filename = None
        pic_file = request.files.get('profile_pic')
        if pic_file and pic_file.filename:
            if allowed_file(pic_file.filename):
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                ext = pic_file.filename.rsplit('.', 1)[1].lower()
                safe_name = secure_filename(f"{username}_profile.{ext}")
                pic_file.save(os.path.join(UPLOAD_DIR, safe_name))
                profile_pic_filename = safe_name
            else:
                flash('Invalid profile picture file format. Allowed: PNG, JPG, JPEG, GIF, WEBP.', 'danger')
                return render_template('register.html')
        else:
            flash('Profile picture is required.', 'danger')
            return render_template('register.html')

        hashed_pw = generate_password_hash(password)
        cursor = get_cursor()
        try:
            cursor.execute(
                "INSERT INTO users (username, password, full_name, email, role, onboarding_complete) "
                "VALUES (?, ?, ?, ?, 'student', 1)",
                (username, hashed_pw, full_name, email)
            )
            user_id = cursor.lastrowid

            cursor.execute(
                "INSERT INTO students (user_id, roll_number, course, room_number, phone, year, birth_date, room_type, allergies, profile_pic) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, roll_number or f'ROLL{user_id:04d}', course,
                 room_number, phone, int(year or 1), birth_date, room_type, allergies, profile_pic_filename)
            )

            # Save roommate preferences
            cursor.execute("""
                INSERT INTO roommate_profiles
                    (student_id, q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, allergies)
                VALUES (?, ?, ?, ?, ?, 2, 2, 2, 2, 2, 3, ?)
            """, (user_id, q1, q2, q3, q4, allergies))

            commit_db()

            session.pop('registration_verified_email', None)
            session.pop('otp_email', None)
            session.pop('otp_purpose', None)

            session['user_id']   = user_id
            session['username']  = username
            session['full_name'] = full_name
            session['role']      = 'student'
            session['profile_pic'] = profile_pic_filename
            flash(f"Welcome to Abode, {full_name.split()[0]}! Your account is all set. 🎉", 'success')
            return redirect(url_for('student.dashboard'))

        except Exception as e:
            flash('An account with this email already exists. Please sign in instead.', 'danger')

    return render_template('register.html')


@bp.route('/register-warden', methods=['GET', 'POST'])
def register_warden():
    """Warden registration — guarded by an admin secret key."""
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        full_name  = request.form.get('full_name', '').strip()
        email      = normalize_email(request.form.get('email', ''))
        password   = request.form.get('password', '')
        secret_key = request.form.get('secret_key', '').strip()

        if not full_name or not email or not password:
            flash('All fields are required.', 'danger')
            return render_template('register_warden.html')

        # SRM email guard
        if not email.endswith('@srmist.edu.in'):
            flash('Only official @srmist.edu.in email addresses are allowed for warden registration.', 'danger')
            return render_template('register_warden.html')

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return render_template('register_warden.html')

        # Admin key guard
        from flask import current_app
        expected = current_app.config.get('WARDEN_SECRET', 'warden123')
        if secret_key != expected:
            flash('Invalid admin secret key. Contact the hostel administrator.', 'danger')
            return render_template('register_warden.html')

        username = email.split('@')[0]
        hashed_pw = generate_password_hash(password)

        cursor = get_cursor()
        try:
            cursor.execute(
                "INSERT INTO users (username, password, full_name, email, role, onboarding_complete) "
                "VALUES (?, ?, ?, ?, 'warden', 1)",
                (username, hashed_pw, full_name, email)
            )
            commit_db()
            flash(f"Warden account created for {full_name}. Please sign in.", 'success')
            return redirect(url_for('auth.login', role='warden'))
        except Exception:
            flash('An account with this email or username already exists.', 'danger')

    return render_template('register_warden.html')


@bp.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


@bp.route('/send_otp', methods=['POST'])
def send_otp():
    data = request.get_json(silent=True) or {}
    email = normalize_email(data.get('email') or request.form.get('email', ''))
    if not email.endswith('@srmist.edu.in'):
        return {'success': False, 'message': 'Use your official @srmist.edu.in email address.'}, 400
    if not registered_hostel_member(email):
        return {'success': False, 'message': 'You are not a registered hostel member. Please contact the hostel office.'}, 403
    code = issue_otp(email, 'registration')
    sent, message = send_otp_email(email, code, 'registration')
    if not sent:
        return {'success': False, 'message': message}, 503
    return {'success': True, 'message': 'Verification code sent to your email.'}


@bp.route('/verify_otp', methods=['POST'])
def verify_otp():
    data = request.get_json(silent=True) or {}
    otp = data.get('otp') or request.form.get('otp')
    if not otp:
        return {'success': False, 'message': 'OTP is required.'}, 400
    verified, message = verify_session_otp(otp, 'registration')
    if not verified:
        return {'success': False, 'message': message}, 400
    session['registration_verified_email'] = session.get('otp_email')
    return {'success': True, 'message': 'Email verified successfully.'}


@bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = normalize_email(request.form.get('email', ''))
        cursor = get_cursor()
        cursor.execute('SELECT id FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        if not user:
            flash('No account matches that email address.', 'danger')
            return render_template('forgot_password.html')
        code = issue_otp(email, 'password_reset')
        sent, message = send_otp_email(email, code, 'password reset')
        if not sent:
            flash(message, 'danger')
            return render_template('forgot_password.html')
        return redirect(url_for('auth.verify_reset_otp'))
    return render_template('forgot_password.html')


@bp.route('/forgot-password/verify', methods=['GET', 'POST'])
def verify_reset_otp():
    if session.get('otp_purpose') != 'password_reset':
        return redirect(url_for('auth.forgot_password'))
    if request.method == 'POST':
        verified, message = verify_session_otp(request.form.get('otp', ''), 'password_reset')
        if verified:
            session['password_reset_verified_email'] = session.get('otp_email')
            return redirect(url_for('auth.reset_password'))
        flash(message, 'danger')
    return render_template('verify_reset_otp.html')


@bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    email = session.get('password_reset_verified_email')
    if not email:
        return redirect(url_for('auth.forgot_password'))
    if request.method == 'POST':
        password = request.form.get('password', '')
        confirmation = request.form.get('confirmation', '')
        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
        elif password != confirmation:
            flash('Passwords do not match.', 'danger')
        else:
            cursor = get_cursor()
            cursor.execute('UPDATE users SET password = ? WHERE email = ?', (generate_password_hash(password), email))
            commit_db()
            session.pop('password_reset_verified_email', None)
            session.pop('otp_email', None)
            session.pop('otp_purpose', None)
            flash('Password updated. You can now sign in.', 'success')
            return redirect(url_for('auth.login'))
    return render_template('reset_password.html')
