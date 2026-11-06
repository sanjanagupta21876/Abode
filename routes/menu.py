from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify
from services.db import get_cursor, commit_db
from functools import wraps
from datetime import datetime

bp = Blueprint('menu', __name__, url_prefix='/menu')


# ── Decorators ──────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def warden_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'warning')
            return redirect(url_for('auth.login'))
        if session.get('role') != 'warden':
            flash('Access denied. Warden privileges required.', 'error')
            return redirect(url_for('student.dashboard'))
        return f(*args, **kwargs)
    return decorated


# ── View weekly menu (students + wardens) ────────────────────────────────────

@bp.route('/')
@login_required
def view_menu():
    cursor = get_cursor()

    # Fetch all day × meal combinations with menu data where available
    cursor.execute('''
        SELECT
            md.id   AS day_id,
            md.day,
            md.display_order AS day_order,
            mt.id   AS meal_id,
            mt.meal,
            mt.display_order AS meal_order,
            hm.items,
            hm.calories
        FROM menu_days md
        CROSS JOIN meal_types mt
        LEFT JOIN hostel_menu hm
               ON md.id = hm.day_id AND mt.id = hm.meal_id
        ORDER BY md.display_order, mt.display_order
    ''')
    rows = cursor.fetchall()

    # Fetch ordered meal names for column headers
    cursor.execute('SELECT meal FROM meal_types ORDER BY display_order')
    meal_names = [r['meal'] for r in cursor.fetchall()]

    # Fetch ordered day names for row iteration
    cursor.execute('SELECT day FROM menu_days ORDER BY display_order')
    day_names = [r['day'] for r in cursor.fetchall()]

    # Build nested dict: weekly_menu[day][meal] = {items, calories}
    weekly_menu = {}
    for row in rows:
        day  = row['day']
        meal = row['meal']
        if day not in weekly_menu:
            weekly_menu[day] = {}
        weekly_menu[day][meal] = {
            'items':    row['items']    or 'Not set',
            'calories': row['calories'] or 0,
        }

    # Determine today's day name (Monday, Tuesday, …, Sunday)
    today_day = datetime.now().strftime('%A')  # e.g. 'Saturday'

    return render_template(
        'menu.html',
        weekly_menu=weekly_menu,
        day_names=day_names,
        meal_names=meal_names,
        today_day=today_day,
    )


# ── Warden edit page ─────────────────────────────────────────────────────────

@bp.route('/edit')
@warden_required
def edit_menu():
    cursor = get_cursor()
    cursor.execute('SELECT * FROM menu_days ORDER BY display_order')
    days = cursor.fetchall()

    cursor.execute('SELECT * FROM meal_types ORDER BY display_order')
    meals = cursor.fetchall()

    cursor.execute('''
        SELECT
            md.day,   md.id AS day_id,
            mt.meal,  mt.id AS meal_id,
            hm.items, hm.calories, hm.updated_at
        FROM hostel_menu hm
        JOIN menu_days  md ON hm.day_id  = md.id
        JOIN meal_types mt ON hm.meal_id = mt.id
        ORDER BY md.display_order, mt.display_order
    ''')
    existing_menu = cursor.fetchall()

    return render_template('menu_edit.html', days=days, meals=meals, existing_menu=existing_menu)


# ── Update / Insert a single menu cell ───────────────────────────────────────

@bp.route('/update', methods=['POST'])
@warden_required
def update_menu():
    day_id   = request.form.get('day_id',   '').strip()
    meal_id  = request.form.get('meal_id',  '').strip()
    items    = request.form.get('items',    '').strip()
    calories = request.form.get('calories', 0)

    if not day_id or not meal_id or not items:
        flash('Please fill in all required fields.', 'error')
        return redirect(url_for('menu.edit_menu'))

    try:
        calories = int(calories)
    except (ValueError, TypeError):
        calories = 0

    cursor = get_cursor()
    cursor.execute(
        'SELECT id FROM hostel_menu WHERE day_id = ? AND meal_id = ?',
        (day_id, meal_id)
    )
    existing = cursor.fetchone()

    if existing:
        cursor.execute('''
            UPDATE hostel_menu
            SET items = ?, calories = ?, updated_at = CURRENT_TIMESTAMP
            WHERE day_id = ? AND meal_id = ?
        ''', (items, calories, day_id, meal_id))
        flash('Menu updated successfully!', 'success')
    else:
        cursor.execute('''
            INSERT INTO hostel_menu (day_id, meal_id, items, calories)
            VALUES (?, ?, ?, ?)
        ''', (day_id, meal_id, items, calories))
        flash('Menu item added successfully!', 'success')

    commit_db()
    return redirect(url_for('menu.edit_menu'))


# ── AJAX helper – prefill form with existing value ────────────────────────────

@bp.route('/api/<int:day_id>/<int:meal_id>')
@login_required
def get_menu_item(day_id, meal_id):
    cursor = get_cursor()
    cursor.execute(
        'SELECT items, calories FROM hostel_menu WHERE day_id = ? AND meal_id = ?',
        (day_id, meal_id)
    )
    row = cursor.fetchone()
    if row:
        return jsonify({'items': row['items'], 'calories': row['calories']})
    return jsonify({'items': '', 'calories': ''})
