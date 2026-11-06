import os
import socket
from urllib.parse import quote
from flask import Flask, render_template, session, redirect, url_for, send_from_directory
from config import Config
from services.db import close_db
from services.birthday_service import create_birthday_notifications
from routes import auth, student, warden, attendance, complaint, notification, menu, roommate, emergency, onboarding, outpass, staff
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)


# Custom Jinja2 filter: handles both datetime objects and SQLite string dates
@app.template_filter('datefmt')
def datefmt_filter(value, fmt='%d %b %Y'):
    if value is None:
        return '-'
    if isinstance(value, str):
        # Try common SQLite timestamp formats
        for parse_fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d']:
            try:
                return datetime.strptime(value, parse_fmt).strftime(fmt)
            except ValueError:
                continue
        return value  # Return raw string if parsing fails
    try:
        return value.strftime(fmt)
    except Exception:
        return str(value)


@app.template_filter('datetimefmt')
def datetimefmt_filter(value, fmt='%d %b %Y, %I:%M %p'):
    return datefmt_filter(value, fmt)


CATEGORY_EMOJIS = {
    'plumber': '🔧',
    'carpenter': '🪚',
    'electrician': '⚡',
    'wifi': '📶',
    'laundry': '🧺',
    'food': '🍽️',
    'security': '🛡️',
    'cleanliness': '🧹',
    'hot_water': '🔥',
    'cold_water': '❄️',
    'other': '❓',
}


@app.template_filter('category_emoji')
def category_emoji_filter(value):
    return CATEGORY_EMOJIS.get((value or '').lower(), '')


# Register all blueprints
app.register_blueprint(auth.bp)
app.register_blueprint(student.bp)
app.register_blueprint(warden.bp)
app.register_blueprint(complaint.bp)
app.register_blueprint(attendance.bp)
app.register_blueprint(notification.bp)
app.register_blueprint(menu.bp)
app.register_blueprint(roommate.bp)
app.register_blueprint(emergency.bp)
app.register_blueprint(onboarding.bp)
app.register_blueprint(outpass.bp)
app.register_blueprint(staff.bp)

# Run safe DB column migrations (adds onboarding_complete & allergies if missing)
with app.app_context():
    onboarding.run_migrations()
    auth.initialize_auth_schema()
    outpass.init_outpass_schema()
    outpass.start_watcher(app)
    create_birthday_notifications()

app.teardown_appcontext(close_db)


@app.before_request
def cleanup_expired_notifications():
    if 'user_id' in session:
        from services.db import get_cursor, commit_db
        try:
            cursor = get_cursor()
            cursor.execute("""
                DELETE FROM notifications
                WHERE (title LIKE '%Hot Water Complaint%' OR title LIKE '%Cold Water Complaint%')
                  AND datetime(created_at) < datetime('now', '-5 hours')
            """)
            commit_db()
        except Exception:
            pass


@app.route('/')
def index():
    if 'user_id' in session:
        role = session.get('role')
        if role == 'warden':
            return redirect(url_for('warden.dashboard'))
        elif role == 'service_staff':
            return redirect(url_for('staff.dashboard'))
        return redirect(url_for('student.dashboard'))
    return render_template('index.html')


@app.route('/residence-story')
def residence_story():
    if 'user_id' in session:
        return redirect(url_for('index'))
    return render_template('residence_story.html')


@app.context_processor
def inject_unread_count():
    if 'user_id' in session:
        from services.db import get_cursor
        uid = session['user_id']
        try:
            cursor = get_cursor()
            cursor.execute("""
                SELECT COUNT(*) AS cnt FROM notifications
                WHERE (user_id = ? OR user_id IS NULL) AND is_read = 0
            """, (uid,))
            result = cursor.fetchone()
            return {'unread_count': result['cnt'] if result else 0}
        except Exception:
            return {'unread_count': 0}
    return {'unread_count': 0}


@app.context_processor
def inject_sos_contact():
    if 'user_id' in session and session.get('role') == 'student':
        try:
            from services.db import get_cursor
            cursor = get_cursor()
            cursor.execute("""
                SELECT w.phone, u.full_name 
                FROM warden w 
                JOIN users u ON w.user_id = u.id 
                LIMIT 1
            """)
            warden = cursor.fetchone()
            if warden and warden['phone']:
                return {'sos_phone': warden['phone'], 'sos_name': warden['full_name']}
        except Exception:
            pass
    return {'sos_phone': '9876543210', 'sos_name': 'Warden Mudit'}


@app.route('/hostel/<path:filename>')
def hostel_files(filename):
    return send_from_directory(os.path.join(app.root_path, 'hostel'), filename)


@app.route('/qr')
def qr_preview():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        local_ip = s.getsockname()[0]
    except Exception:
        local_ip = '127.0.0.1'
    finally:
        s.close()
    phone_url = f'http://{local_ip}:5000'
    qr_url = f'https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={quote(phone_url, safe="")}'
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Abode phone preview</title>
    <style>
        body {{ margin: 0; display: flex; align-items: center; justify-content: center; min-height: 100vh;
                background: #0f172a; font-family: system-ui, -apple-system, BlinkMacSystemFont, sans-serif; color: #fff; }}
        .card {{ text-align: center; padding: 2rem; background: #1e293b; border-radius: 20px; box-shadow: 0 20px 40px rgba(0,0,0,.25); max-width: 320px; }}
        img {{ width: 250px; height: 250px; border-radius: 12px; margin: 1.2rem 0; }}
        a {{ color: #60a5fa; word-break: break-all; }}
        p.note {{ font-size: .85rem; color: #94a3b8; margin-top: 1rem; }}
    </style>
</head>
<body>
    <div class="card">
        <h2>Scan to open Abode on your phone</h2>
        <img src="{qr_url}" alt="Phone preview QR code">
        <p><a href="{phone_url}">{phone_url}</a></p>
        <p class="note">Make sure your phone is on the same WiFi network. Expo Go is for React Native apps; this Flask app opens in your phone's browser.</p>
    </div>
</body>
</html>'''


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
