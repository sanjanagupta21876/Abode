from flask import Blueprint, render_template, session, redirect, url_for, flash, request
from services.db import get_cursor, commit_db
from functools import wraps
import json
from collections import defaultdict

bp = Blueprint('notification', __name__, url_prefix='/notification')


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
    uid = session['user_id']
    role = session.get('role')
    cursor = get_cursor()
    
    # Clean up expired water complaint notifications (older than 5 hours)
    cursor.execute("""
        DELETE FROM notifications
        WHERE (title LIKE '%Hot Water Complaint%' OR title LIKE '%Cold Water Complaint%')
          AND datetime(created_at) < datetime('now', '-5 hours')
    """)
    commit_db()

    # Get notifications and poll data
    cursor.execute("""
        SELECT n.id, n.title, n.message, n.is_read, n.created_at, 
               u.full_name AS sender_name, n.is_poll, n.poll_options,
               s.room_number AS sender_room, u.role AS sender_role
        FROM notifications n
        LEFT JOIN users u ON n.sender_id = u.id
        LEFT JOIN students s ON u.id = s.user_id
        WHERE n.user_id = ? OR n.user_id IS NULL
        ORDER BY n.created_at DESC
    """, (uid,))
    notifications_raw = cursor.fetchall()
    
    notifications = []
    for n in notifications_raw:
        n_dict = dict(n)
        if n_dict['is_poll'] and n_dict['poll_options']:
            try:
                options = json.loads(n_dict['poll_options'])
                n_dict['options'] = options
                
                # Get my vote
                cursor.execute("SELECT selected_option FROM poll_responses WHERE notification_id = ? AND user_id = ?", (n['id'], uid))
                vote = cursor.fetchone()
                n_dict['my_vote'] = vote['selected_option'] if vote else None
                
                # Get counts for percentages
                cursor.execute("SELECT selected_option, COUNT(*) as cnt FROM poll_responses WHERE notification_id = ? GROUP BY selected_option", (n['id'],))
                counts = {r['selected_option']: r['cnt'] for r in cursor.fetchall()}
                n_dict['counts'] = counts
                n_dict['total_votes'] = sum(counts.values())

                # Detailed results for Warden (WhatsApp Style: Grouped by Option)
                if role == 'warden':
                    cursor.execute("""
                        SELECT u.full_name AS student_name, s.room_number, pr.selected_option, pr.created_at
                        FROM poll_responses pr
                        JOIN users u ON pr.user_id = u.id
                        LEFT JOIN students s ON u.id = s.user_id
                        WHERE pr.notification_id = ?
                        ORDER BY pr.created_at DESC
                    """, (n['id'],))
                    voters = cursor.fetchall()
                    
                    # Group voters by option index
                    grouped_voters = defaultdict(list)
                    for v in voters:
                        grouped_voters[v['selected_option']].append({
                            'name': v['student_name'],
                            'room': v['room_number'] or 'N/A',
                            'time': v['created_at']
                        })
                    n_dict['voter_details'] = grouped_voters
            except Exception:
                n_dict['is_poll'] = 0
            
        notifications.append(n_dict)

    # Mark as read
    cursor.execute("UPDATE notifications SET is_read = 1 WHERE (user_id = ? OR user_id IS NULL) AND is_read = 0", (uid,))
    commit_db()
    
    return render_template('notifications.html', notifications=notifications, role=role)


@bp.route('/vote/<int:nid>', methods=['POST'])
@login_required
def vote(nid):
    uid = session['user_id']
    option_idx = request.form.get('option', type=int)
    
    if option_idx is None:
        flash('Please select an option.', 'warning')
        return redirect(url_for('notification.view'))
        
    cursor = get_cursor()
    cursor.execute("INSERT OR REPLACE INTO poll_responses (notification_id, user_id, selected_option) VALUES (?, ?, ?)", (nid, uid, option_idx))
    commit_db()
    flash('Vote recorded!', 'success')
    return redirect(url_for('notification.view'))


@bp.route('/send', methods=['GET', 'POST'])
@login_required
def send():
    if session.get('role') != 'warden':
        flash('Only wardens can send notifications.', 'warning')
        return redirect(url_for('notification.view'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        message = request.form.get('message', '').strip()
        target = request.form.get('target', 'all')
        is_poll = 1 if request.form.get('is_poll') else 0
        poll_options = None
        
        if is_poll:
            opts = [o.strip() for o in request.form.getlist('poll_option') if o.strip()]
            if len(opts) < 2:
                flash('Poll needs at least 2 options.', 'danger')
                return abort_send()
            poll_options = json.dumps(opts)

        if not title or not message:
            flash('Title and message are required.', 'danger')
            return abort_send()

        cursor = get_cursor()
        t_id = None if target == 'all' else int(target)
        cursor.execute("""
            INSERT INTO notifications (sender_id, user_id, title, message, is_poll, poll_options)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session['user_id'], t_id, title, message, is_poll, poll_options))
        commit_db()
        flash('Notification sent!', 'success')
        return redirect(url_for('notification.view'))

    return abort_send()


def abort_send():
    cursor = get_cursor()
    cursor.execute("SELECT id, full_name, username FROM users WHERE role = 'student' ORDER BY full_name")
    students = cursor.fetchall()
    return render_template('notification_form.html', students=students)
