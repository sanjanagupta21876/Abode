import math
import threading
import time
from datetime import datetime, timedelta
from flask import Blueprint, request, session, redirect, url_for, render_template, flash, current_app, jsonify
from services.db import get_cursor, commit_db
from functools import wraps

bp = Blueprint('outpass', __name__, url_prefix='/outpass')


def student_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'student':
            flash('Please log in as a student.', 'warning')
            return redirect(url_for('auth.login', role='student'))
        return f(*args, **kwargs)
    return decorated


def warden_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'warden':
            flash('Please log in as a warden.', 'warning')
            return redirect(url_for('auth.login', role='warden'))
        return f(*args, **kwargs)
    return decorated


def init_outpass_schema():
    cursor = get_cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS outpasses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('outpass', 'leave')),
            destination TEXT NOT NULL,
            purpose TEXT NOT NULL,
            departure_at TEXT NOT NULL,
            return_at TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'completed', 'overdue')),
            checked_in_at TEXT,
            checkin_lat REAL,
            checkin_lng REAL,
            alert_sent INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)
    commit_db()


def haversine_km(lat1, lng1, lat2, lng2):
    R = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def parse_dt(value):
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


@bp.route('/request', methods=['GET', 'POST'])
@student_required
def create_request():
    uid = session['user_id']
    cursor = get_cursor()
    cursor.execute("SELECT u.full_name, s.room_number FROM users u JOIN students s ON u.id = s.user_id WHERE u.id = ?", (uid,))
    student = cursor.fetchone()

    if request.method == 'POST':
        otype = request.form.get('otype', '').strip().lower()
        destination = request.form.get('destination', '').strip()
        purpose = request.form.get('purpose', '').strip()
        departure_at = request.form.get('departure_at', '').strip()
        return_at = request.form.get('return_at', '').strip()

        if otype not in ('outpass', 'leave'):
            flash('Invalid request type.', 'danger')
            return redirect(url_for('outpass.create_request'))
        if not destination or not purpose or not departure_at or not return_at:
            flash('All fields are required.', 'danger')
            return redirect(url_for('outpass.create_request'))
        if parse_dt(return_at) <= parse_dt(departure_at):
            flash('Expected return time must be after departure time.', 'danger')
            return redirect(url_for('outpass.create_request'))

        cursor.execute("""
            INSERT INTO outpasses (student_id, type, destination, purpose, departure_at, return_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (uid, otype, destination, purpose, departure_at, return_at))
        commit_db()
        flash('Outpass logged successfully.', 'success')
        return redirect(url_for('outpass.my_outpasses'))

    return render_template('outpass/form.html', student=student)


@bp.route('/mine')
@student_required
def my_outpasses():
    uid = session['user_id']
    cursor = get_cursor()
    cursor.execute("""
        SELECT id, type, destination, purpose, departure_at, return_at, status, checked_in_at,
               datetime('now') as now
        FROM outpasses
        WHERE student_id = ?
        ORDER BY created_at DESC
    """, (uid,))
    outpasses = cursor.fetchall()
    return render_template('outpass/mine.html', outpasses=outpasses)


@bp.route('/api/checkin/<int:oid>', methods=['POST'])
@student_required
def checkin(oid):
    uid = session['user_id']
    data = request.get_json(silent=True) or {}
    lat = data.get('lat')
    lng = data.get('lng')

    if lat is None or lng is None:
        return jsonify({'success': False, 'message': 'GPS coordinates missing.'}), 400

    cursor = get_cursor()
    cursor.execute("""
        SELECT id, status, return_at FROM outpasses WHERE id = ? AND student_id = ?
    """, (oid, uid))
    row = cursor.fetchone()
    if not row:
        return jsonify({'success': False, 'message': 'Outpass not found.'}), 404
    if row['status'] == 'completed':
        return jsonify({'success': False, 'message': 'You have already checked in.'})

    cfg = current_app.config
    radius = float(cfg.get('GEOFENCE_RADIUS_METRES', 100))
    distance_m = haversine_km(float(lat), float(lng), cfg['HOSTEL_LAT'], cfg['HOSTEL_LNG']) * 1000

    if distance_m > radius:
        return jsonify({'success': False, 'message': f'You must be at the hostel to check in. You are {distance_m:.0f} metres away.'})

    now = datetime.now().strftime('%Y-%m-%dT%H:%M')
    cursor.execute("""
        UPDATE outpasses
        SET status = 'completed', checked_in_at = ?, checkin_lat = ?, checkin_lng = ?
        WHERE id = ?
    """, (now, lat, lng, oid))
    commit_db()
    return jsonify({'success': True, 'message': 'Checked in successfully. Welcome back!'})


@bp.route('/warden/tracking')
@warden_required
def tracking():
    cursor = get_cursor()
    cursor.execute("""
        SELECT o.id, o.type, o.destination, o.purpose, o.departure_at, o.return_at, o.status,
               o.checked_in_at, u.full_name, s.room_number,
               CASE
                   WHEN o.status = 'completed' THEN 'completed'
                   WHEN datetime('now', 'localtime') > datetime(o.return_at, '+' || ? || ' minutes') THEN 'overdue'
                   WHEN datetime('now', 'localtime') > datetime(o.return_at) THEN 'grace'
                   ELSE 'active'
               END AS computed_status
        FROM outpasses o
        JOIN users u ON o.student_id = u.id
        LEFT JOIN students s ON u.id = s.user_id
        WHERE o.status != 'completed'
           OR (o.status = 'completed' AND o.checked_in_at >= datetime('now', 'localtime', '-24 hours'))
        ORDER BY o.created_at DESC
    """, (int(current_app.config.get('OUTPASS_GRACE_MINUTES', 30)),))
    rows = cursor.fetchall()

    active = [r for r in rows if r['computed_status'] in ('active', 'grace')]
    overdue = [r for r in rows if r['computed_status'] == 'overdue']
    completed = [r for r in rows if r['computed_status'] == 'completed']

    return render_template('outpass/tracking.html', active=active, overdue=overdue, completed=completed)


def _run_watcher(app):
    with app.app_context():
        cursor = get_cursor()
        cfg = app.config
        grace = int(cfg.get('OUTPASS_GRACE_MINUTES', 30))

        cursor.execute("""
            SELECT o.id, o.student_id, o.type, o.destination, o.return_at, u.full_name, s.room_number
            FROM outpasses o
            JOIN users u ON o.student_id = u.id
            LEFT JOIN students s ON u.id = s.user_id
            WHERE o.status = 'active'
              AND datetime('now', 'localtime') > datetime(o.return_at, '+' || ? || ' minutes')
              AND o.alert_sent = 0
        """, (grace,))
        overdue = cursor.fetchall()

        cursor.execute("SELECT user_id FROM warden")
        wardens = [w['user_id'] for w in cursor.fetchall()]

        for row in overdue:
            cursor.execute("""
                UPDATE outpasses SET status = 'overdue', alert_sent = 1 WHERE id = ?
            """, (row['id'],))

            # Notify the student
            cursor.execute("""
                INSERT INTO notifications (sender_id, user_id, title, message)
                VALUES (NULL, ?, ?, ?)
            """, (
                row['student_id'],
                f"Your {row['type']} is overdue",
                f"You have not returned from {row['destination']} by {row['return_at']}. Please check in as soon as you are back."
            ))

            # Notify each warden
            for warden_id in wardens:
                cursor.execute("""
                    INSERT INTO notifications (sender_id, user_id, title, message)
                    VALUES (NULL, ?, ?, ?)
                """, (
                    warden_id,
                    f"Overdue {row['type'].title()}: {row['full_name']}",
                    f"{row['full_name']} ({row['room_number'] or 'N/A'}) has not returned from {row['destination']} by {row['return_at']}."
                ))
        commit_db()


def watcher(app):
    while True:
        time.sleep(300)
        try:
            _run_watcher(app)
        except Exception:
            app.logger.exception('Outpass watcher failed')


def start_watcher(app):
    t = threading.Thread(target=watcher, args=(app,), daemon=True)
    t.start()


@bp.route('/watcher', methods=['POST'])
def trigger_watcher():
    _run_watcher(current_app._get_current_object())
    return jsonify({'success': True, 'message': 'Watcher run completed.'})
