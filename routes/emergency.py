from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from services.db import get_cursor, commit_db
from functools import wraps

bp = Blueprint('emergency', __name__, url_prefix='/emergency')

def warden_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'warden':
            flash('Access denied. Warden privileges required.', 'danger')
            return redirect(url_for('auth.login', role='warden'))
        return f(*args, **kwargs)
    return decorated

@bp.route('/', methods=['GET'])
@warden_required
def view_contacts():
    cursor = get_cursor()
    cursor.execute("""
        SELECT id, name, role, phone, notes
        FROM emergency_contacts
        ORDER BY name ASC
    """)
    contacts = cursor.fetchall()
    return render_template('emergency.html', contacts=contacts)

@bp.route('/add', methods=['POST'])
@warden_required
def add_contact():
    name = request.form.get('name', '').strip()
    role = request.form.get('role', '').strip()
    phone = request.form.get('phone', '').strip()
    notes = request.form.get('notes', '').strip()

    if not name or not role or not phone:
        flash('Name, role, and phone are required.', 'danger')
    else:
        cursor = get_cursor()
        cursor.execute(
            "INSERT INTO emergency_contacts (name, role, phone, notes) VALUES (?, ?, ?, ?)",
            (name, role, phone, notes)
        )
        commit_db()
        flash('Emergency contact added successfully.', 'success')

    return redirect(url_for('emergency.view_contacts'))

@bp.route('/edit/<int:contact_id>', methods=['POST'])
@warden_required
def edit_contact(contact_id):
    name = request.form.get('name', '').strip()
    role = request.form.get('role', '').strip()
    phone = request.form.get('phone', '').strip()
    notes = request.form.get('notes', '').strip()

    if not name or not role or not phone:
        flash('Name, role, and phone are required.', 'danger')
    else:
        cursor = get_cursor()
        cursor.execute("""
            UPDATE emergency_contacts 
            SET name = ?, role = ?, phone = ?, notes = ?
            WHERE id = ?
        """, (name, role, phone, notes, contact_id))
        commit_db()
        flash('Emergency contact updated successfully.', 'success')

    return redirect(url_for('emergency.view_contacts'))

@bp.route('/delete/<int:contact_id>', methods=['POST'])
@warden_required
def delete_contact(contact_id):
    cursor = get_cursor()
    cursor.execute("DELETE FROM emergency_contacts WHERE id = ?", (contact_id,))
    commit_db()
    flash('Emergency contact deleted.', 'info')
    return redirect(url_for('emergency.view_contacts'))
