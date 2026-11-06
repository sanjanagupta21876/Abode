from flask import Blueprint, render_template, session, redirect, url_for, flash, request, jsonify
from services.db import get_cursor, commit_db
from functools import wraps
import json

bp = Blueprint('roommate', __name__, url_prefix='/student/roommate')

# Safe migration: add allergies column if it doesn't already exist
try:
    _cur = get_cursor()
    _cur.execute("ALTER TABLE roommate_profiles ADD COLUMN allergies TEXT DEFAULT ''")
    commit_db()
except Exception:
    pass  # Column already exists, ignore

def student_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'student':
            flash('Please log in as a student.', 'warning')
            return redirect(url_for('auth.login', role='student'))
        return f(*args, **kwargs)
    return decorated

@bp.route('/quiz', methods=['GET', 'POST'])
@student_required
def quiz():
    uid = session['user_id']
    cursor = get_cursor()
    
    if request.method == 'POST':
        # Retrieve answers and allergy text
        answers = {f'q{i}': int(request.form.get(f'q{i}', 1)) for i in range(1, 11)}
        allergies = request.form.get('allergies', '').strip()
        
        # Upsert roommate profile
        cursor.execute("SELECT student_id FROM roommate_profiles WHERE student_id = ?", (uid,))
        profile = cursor.fetchone()
        
        if profile:
            cursor.execute("""
                UPDATE roommate_profiles 
                SET q1=?, q2=?, q3=?, q4=?, q5=?, q6=?, q7=?, q8=?, q9=?, q10=?, allergies=?, updated_at=CURRENT_TIMESTAMP
                WHERE student_id=?
            """, (
                answers['q1'], answers['q2'], answers['q3'], answers['q4'], answers['q5'],
                answers['q6'], answers['q7'], answers['q8'], answers['q9'], answers['q10'],
                allergies, uid
            ))
        else:
            cursor.execute("""
                INSERT INTO roommate_profiles (student_id, q1, q2, q3, q4, q5, q6, q7, q8, q9, q10, allergies)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                uid, answers['q1'], answers['q2'], answers['q3'], answers['q4'], answers['q5'],
                answers['q6'], answers['q7'], answers['q8'], answers['q9'], answers['q10'],
                allergies
            ))
        commit_db()
        flash('Profile saved! Find your matching roommate below.', 'success')
        return redirect(url_for('roommate.swipe'))

    cursor.execute("SELECT * FROM roommate_profiles WHERE student_id = ?", (uid,))
    profile = cursor.fetchone()
    return render_template('roommate/quiz.html', profile=profile)

@bp.route('/swipe')
@student_required
def swipe():
    uid = session['user_id']
    cursor = get_cursor()

    # Check if user has completed the quiz
    cursor.execute("SELECT * FROM roommate_profiles WHERE student_id = ?", (uid,))
    my_profile = cursor.fetchone()
    if not my_profile:
        flash('Please complete the compatibility quiz first.', 'info')
        return redirect(url_for('roommate.quiz'))

    # Get user room to determine gender
    cursor.execute("SELECT room_number FROM students WHERE user_id = ?", (uid,))
    my_student_record = cursor.fetchone()
    my_room = my_student_record['room_number'] if my_student_record else ""
    is_my_room_female = str(my_room).startswith('1')

    # Fetch potential matches (same gender, not self, not already swiped)
    cursor.execute("""
        SELECT u.id, u.full_name, s.course, s.year, s.room_number,
               rp.q1, rp.q2, rp.q3, rp.q4, rp.q5, rp.q6, rp.q7, rp.q8, rp.q9, rp.q10
        FROM users u
        JOIN students s ON u.id = s.user_id
        JOIN roommate_profiles rp ON u.id = rp.student_id
        WHERE u.id != ? AND u.id NOT IN (
            SELECT swipee_id FROM roommate_swipes WHERE swiper_id = ?
        )
    """, (uid, uid))
    potentials = cursor.fetchall()
    
    valid_candidates = []
    
    for candidate in potentials:
        c_room = str(candidate['room_number'])
        c_female = c_room.startswith('1')
        
        # Same gender check
        if c_female != is_my_room_female:
            continue
            
        # Compatibility Calculation
        score = 0
        highlights = []
        
        # Q1-Q9
        for i in range(1, 10):
            q_key = f'q{i}'
            diff = abs(my_profile[q_key] - candidate[q_key])
            similarity = 3 - diff
            score += similarity
            
        # Q10 (Food)
        my_food = my_profile['q10']
        cand_food = candidate['q10']
        food_similarity = 0
        if my_food == 4 or cand_food == 4 or my_food == cand_food:
            food_similarity = 3
        elif (my_food in [1,2] and cand_food in [1,2]) or (my_food in [2,3] and cand_food in [2,3]):
             food_similarity = 1
        score += food_similarity
            
        compat_percent = int((score / 63) * 100)
        
        # Highlights
        if abs(my_profile['q4'] - candidate['q4']) <= 1:
            highlights.append("Same sleep schedule 😴")
        if my_profile['q4'] >= 3 and candidate['q4'] >= 3:
            highlights.append("Both night owls 🦉")
        if my_food == cand_food and my_food != 4:
            highlights.append("Same food preference 🥗")
        if my_profile['q6'] == candidate['q6']:
            if my_profile['q6'] <= 2:
                highlights.append("Both introverts 🤐")
            else:
                highlights.append("Both extroverts 🎉")
        
        valid_candidates.append({
            'id': candidate['id'],
            'full_name': candidate['full_name'],
            'course': candidate['course'],
            'year': candidate['year'],
            'compatibility': compat_percent,
            'highlights': highlights[:3],
            'q4': candidate['q4'],
            'q6': candidate['q6'],
            'q7': candidate['q7'],
            'q8': candidate['q8'],
            'q9': candidate['q9']
        })
        
    valid_candidates.sort(key=lambda x: x['compatibility'], reverse=True)
    return render_template('roommate/swipe.html', candidates=valid_candidates, profile=my_profile)

@bp.route('/swipe_action', methods=['POST'])
@student_required
def swipe_action():
    uid = session['user_id']
    data = request.json
    swipee_id = data.get('swipee_id')
    action = data.get('action') # 'right' or 'left'
    
    if not swipee_id or action not in ['right', 'left']:
        return jsonify({'error': 'Invalid request'}), 400
        
    cursor = get_cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO roommate_swipes (swiper_id, swipee_id, action) VALUES (?, ?, ?)",
                       (uid, swipee_id, action))
        commit_db()
        
        match = False
        if action == 'right':
            # Check if swipee also swiped right on swiper
            cursor.execute("SELECT action FROM roommate_swipes WHERE swiper_id = ? AND swipee_id = ?",
                           (swipee_id, uid))
            result = cursor.fetchone()
            if result and result['action'] == 'right':
                match = True
                
        return jsonify({'success': True, 'match': match})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/matches')
@student_required
def matches():
    uid = session['user_id']
    cursor = get_cursor()
    
    # Mutual rights
    cursor.execute("""
        SELECT u.id, u.full_name, s.course, s.room_number
        FROM users u
        JOIN students s ON u.id = s.user_id
        WHERE u.id IN (
            SELECT a.swipee_id FROM roommate_swipes a
            INNER JOIN roommate_swipes b 
            ON a.swipee_id = b.swiper_id AND a.swiper_id = b.swipee_id
            WHERE a.swiper_id = ? AND a.action = 'right' AND b.action = 'right'
        )
    """, (uid,))
    my_matches = cursor.fetchall()
    
    return render_template('roommate/matches.html', matches=my_matches)

@bp.route('/chat/<int:match_id>', methods=['GET'])
@student_required
def chat(match_id):
    uid = session['user_id']
    cursor = get_cursor()
    
    # Verify mutual match
    cursor.execute("""
        SELECT COUNT(*) as is_match FROM roommate_swipes a
        INNER JOIN roommate_swipes b 
        ON a.swipee_id = b.swiper_id AND a.swiper_id = b.swipee_id
        WHERE a.swiper_id = ? AND a.swipee_id = ? AND a.action = 'right' AND b.action = 'right'
    """, (uid, match_id))
    if not cursor.fetchone()['is_match']:
        flash("You can only chat with your mutual matches.", "danger")
        return redirect(url_for('roommate.matches'))
        
    cursor.execute("SELECT id, full_name FROM users WHERE id = ?", (match_id,))
    match_user = cursor.fetchone()
    
    cursor.execute("""
        SELECT sender_id, message, created_at FROM roommate_messages
        WHERE (sender_id = ? AND receiver_id = ?) OR (sender_id = ? AND receiver_id = ?)
        ORDER BY created_at ASC
    """, (uid, match_id, match_id, uid))
    messages = cursor.fetchall()
    
    return render_template('roommate/chat.html', match_user=match_user, messages=messages, uid=uid)

@bp.route('/chat/<int:match_id>', methods=['POST'])
@student_required
def send_message(match_id):
    uid = session['user_id']
    message = request.form.get('message')
    if message:
        cursor = get_cursor()
        cursor.execute("INSERT INTO roommate_messages (sender_id, receiver_id, message) VALUES (?, ?, ?)",
                       (uid, match_id, message))
        commit_db()
    return redirect(url_for('roommate.chat', match_id=match_id))
