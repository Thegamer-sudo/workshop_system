# ============================================
#  app.py — Student Workshop System
# ============================================

from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash, jsonify
)
from flask_mail import Mail, Message
import sqlite3
import hashlib
import secrets
from datetime import date, timedelta, datetime

app = Flask(__name__)
app.secret_key = 'student-workshop-secret-2026'

DATABASE = 'workshop_system.db'

ADMIN_EMAIL    = 'admin@test.com'
ADMIN_PASSWORD = 'admin123'
ADMIN_NAME     = 'Administrator'

# ============================================
#  EMAIL CONFIGURATION — REPLACE WITH YOUR INFO
# ============================================
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'YOUR_EMAIL@gmail.com'      # <-- REPLACE
app.config['MAIL_PASSWORD'] = 'YOUR_APP_PASSWORD'         # <-- REPLACE
app.config['MAIL_DEFAULT_SENDER'] = 'Student Workshop <YOUR_EMAIL@gmail.com>'

mail = Mail(app)


# ============================================
#  DATABASE
# ============================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT    NOT NULL,
            email    TEXT    NOT NULL UNIQUE,
            password TEXT    NOT NULL,
            role     TEXT    NOT NULL DEFAULT 'student',
            archived INTEGER NOT NULL DEFAULT 0
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS workshops (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            title       TEXT NOT NULL,
            description TEXT NOT NULL,
            date        TEXT NOT NULL,
            start_time  TEXT NOT NULL,
            end_time    TEXT NOT NULL,
            teams_link  TEXT,
            created_by  INTEGER NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending'
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS registrations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            workshop_id INTEGER NOT NULL,
            UNIQUE(user_id, workshop_id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            workshop_id INTEGER NOT NULL,
            user_id     INTEGER NOT NULL,
            rating      INTEGER NOT NULL,
            comment     TEXT,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(workshop_id, user_id)
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS reset_tokens (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            token      TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL
        )
    ''')

    conn.commit()
    conn.close()


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def ensure_admin_in_db():
    conn = get_db()
    existing = conn.execute(
        'SELECT id FROM users WHERE email = ?', (ADMIN_EMAIL,)
    ).fetchone()
    if not existing:
        conn.execute('''
            INSERT OR IGNORE INTO users (name, email, password, role, archived)
            VALUES (?, ?, 'ADMIN_ACCOUNT', 'admin', 0)
        ''', (ADMIN_NAME, ADMIN_EMAIL))
        conn.commit()
    conn.close()


def times_overlap(start_a, end_a, start_b, end_b):
    return start_a < end_b and end_a > start_b


# ============================================
#  EMAIL FUNCTIONS
# ============================================

def send_email(to, subject, html_content):
    try:
        msg = Message(subject, recipients=[to])
        msg.html = html_content
        mail.send(msg)
        print(f"✅ Email sent to {to}")
        return True
    except Exception as e:
        print(f"❌ Email error: {e}")
        return False


def send_welcome_email(user_name, user_email):
    subject = "🎉 Welcome to Student Workshop!"
    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 550px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden;">
        <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 30px 25px; text-align: center;">
            <div style="font-size: 32px; font-weight: 700; color: white;">Student Workshop</div>
        </div>
        <div style="padding: 30px 25px;">
            <h2 style="color: #0f172a;">Welcome, {user_name}! 👋</h2>
            <p style="color: #475569;">Your account has been successfully created.</p>
            <a href="http://127.0.0.1:5000/workshops" style="display: inline-block; background: #0d9488; color: white; padding: 12px 28px; text-decoration: none; border-radius: 8px;">Browse Workshops →</a>
        </div>
    </div>
    """
    send_email(user_email, subject, html)


def send_registration_email(user_name, user_email, workshop_title, workshop_date, workshop_time, teams_link=None):
    subject = f"✅ Registration Confirmed: {workshop_title}"
    join_button = f"""
    <a href="{teams_link}" style="display: inline-block; background: #5059C9; color: white; padding: 12px 28px; text-decoration: none; border-radius: 8px;">🎥 Join on Teams</a>
    """ if teams_link else '<p><em>🔗 A Teams link will be provided by the host.</em></p>'
    
    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 550px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden;">
        <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 30px 25px; text-align: center;">
            <div style="font-size: 28px; font-weight: 700; color: white;">Registration Confirmed!</div>
        </div>
        <div style="padding: 30px 25px;">
            <h2 style="color: #0f172a;">Hello {user_name},</h2>
            <p>You're registered for:</p>
            <div style="background: #f0fdfa; border-left: 4px solid #0d9488; padding: 20px; margin: 20px 0;">
                <h3>📖 {workshop_title}</h3>
                <p><strong>📅 Date:</strong> {workshop_date}</p>
                <p><strong>⏰ Time:</strong> {workshop_time}</p>
                {join_button}
            </div>
            <a href="http://127.0.0.1:5000/dashboard" style="background: #0f172a; color: white; padding: 10px 20px; text-decoration: none; border-radius: 8px;">📊 My Dashboard</a>
        </div>
    </div>
    """
    send_email(user_email, subject, html)


def send_workshop_approved_email(host_name, host_email, workshop_title):
    subject = f"🎉 Workshop Approved: {workshop_title}"
    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 550px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden;">
        <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 30px 25px; text-align: center;">
            <div style="font-size: 28px; font-weight: 700; color: white;">Workshop Approved!</div>
        </div>
        <div style="padding: 30px 25px;">
            <h2>Great news, {host_name}!</h2>
            <p>Your workshop <strong>"{workshop_title}"</strong> is now live!</p>
            <a href="http://127.0.0.1:5000/host/dashboard" style="display: inline-block; background: #0d9488; color: white; padding: 12px 28px; text-decoration: none; border-radius: 8px;">Go to Host Dashboard →</a>
        </div>
    </div>
    """
    send_email(host_email, subject, html)


def send_password_reset_email(user_name, user_email, reset_link):
    subject = "🔐 Reset Your Password - Student Workshop"
    html = f"""
    <div style="font-family: 'Segoe UI', Arial, sans-serif; max-width: 550px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden;">
        <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 30px 25px; text-align: center;">
            <div style="font-size: 28px; font-weight: 700; color: white;">Reset Password</div>
        </div>
        <div style="padding: 30px 25px;">
            <h2>Hello {user_name},</h2>
            <p>Click the button below to reset your password:</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_link}" style="background: #0d9488; color: white; padding: 14px 32px; text-decoration: none; border-radius: 8px;">Reset Password</a>
            </div>
            <p>This link expires in 24 hours.</p>
        </div>
    </div>
    """
    send_email(user_email, subject, html)


# ============================================
#  HELPER
# ============================================

def require_login(role=None):
    if 'user_id' not in session:
        flash('Please sign in to access that page.', 'warning')
        return False
    if role and session.get('role') != role:
        flash('You do not have permission to access that page.', 'error')
        return False
    return True


# ============================================
#  PUBLIC ROUTES
# ============================================

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/workshops')
def workshops():
    conn = get_db()
    role = session.get('role')
    uid  = session.get('user_id')
    current_time = datetime.now().strftime('%H:%M')
    today = date.today().isoformat()

    if role == 'admin':
        all_workshops = conn.execute('''
            SELECT w.*, u.name AS created_by_name
            FROM workshops w
            JOIN users u ON w.created_by = u.id
            ORDER BY w.date ASC, w.start_time ASC
        ''').fetchall()
    elif role == 'host':
        all_workshops = conn.execute('''
            SELECT w.*, u.name AS created_by_name,
                   (SELECT rating FROM feedback WHERE workshop_id = w.id AND user_id = ?) AS my_rating
            FROM workshops w
            JOIN users u ON w.created_by = u.id
            WHERE w.status = 'approved' OR w.created_by = ?
            ORDER BY w.date ASC, w.start_time ASC
        ''', (uid, uid)).fetchall()
    else:
        all_workshops = conn.execute('''
            SELECT w.*, u.name AS created_by_name,
                   (SELECT rating FROM feedback WHERE workshop_id = w.id AND user_id = ?) AS my_rating
            FROM workshops w
            JOIN users u ON w.created_by = u.id
            WHERE w.status = 'approved'
            ORDER BY w.date ASC, w.start_time ASC
        ''', (uid if uid else 0,)).fetchall()

    registered_ids = []
    if uid and role != 'admin':
        rows = conn.execute(
            'SELECT workshop_id FROM registrations WHERE user_id = ?', (uid,)
        ).fetchall()
        registered_ids = [r['workshop_id'] for r in rows]

    conn.close()
    return render_template(
        'workshops.html',
        workshops=all_workshops,
        registered_ids=registered_ids,
        today=today,
        current_time=current_time
    )


# ============================================
#  AUTHENTICATION
# ============================================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('role'):
        return redirect(url_for('index'))

    if request.method == 'POST':
        name     = request.form.get('name', '').strip()
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')
        role     = request.form.get('role', 'student')

        if role not in ('student', 'host'):
            role = 'student'

        if not name or not email or not password:
            flash('All fields are required.', 'error')
            return render_template('register.html')

        if len(password) < 8 or len(password) > 16:
            flash('Password must be between 8 and 16 characters.', 'error')
            return render_template('register.html')

        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('register.html')

        if email == ADMIN_EMAIL:
            flash('Unable to create account. Please check your details and try again.', 'error')
            return render_template('register.html')

        conn = get_db()
        try:
            conn.execute('''
                INSERT INTO users (name, email, password, role, archived)
                VALUES (?, ?, ?, ?, 0)
            ''', (name, email, hash_password(password), role))
            conn.commit()
            role_label = 'Host' if role == 'host' else 'Student'
            
            send_welcome_email(name, email)
            
            flash(f'Account created as {role_label}. A welcome email has been sent.', 'success')
            return redirect(url_for('login'))

        except sqlite3.IntegrityError:
            flash('Unable to create account. Please check your details and try again.', 'error')
            return render_template('register.html')

        finally:
            conn.close()

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('role'):
        return redirect(url_for('index'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if email == ADMIN_EMAIL and password == ADMIN_PASSWORD:
            session['user_id'] = 0
            session['name']    = ADMIN_NAME
            session['email']   = ADMIN_EMAIL
            session['role']    = 'admin'
            flash(f'Welcome back, {ADMIN_NAME}.', 'success')
            return redirect(url_for('admin_dashboard'))

        conn = get_db()
        user = conn.execute('''
            SELECT * FROM users WHERE email = ? AND password = ?
        ''', (email, hash_password(password))).fetchone()
        conn.close()

        if user:
            if user['archived']:
                flash('This account has been archived. Contact the administrator.', 'error')
                return render_template('login.html')
            session['user_id'] = user['id']
            session['name']    = user['name']
            session['email']   = user['email']
            session['role']    = user['role']
            flash(f'Welcome back, {user["name"]}.', 'success')
            if user['role'] == 'host':
                return redirect(url_for('host_dashboard'))
            return redirect(url_for('dashboard'))

        flash('Incorrect email or password.', 'error')
        return render_template('login.html')

    return render_template('login.html')


@app.route('/logout')
def logout():
    name = session.get('name', 'User')
    session.clear()
    flash(f'You have been signed out. Goodbye, {name}.', 'info')
    return redirect(url_for('index'))


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if session.get('role'):
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()

        conn = get_db()
        user = conn.execute('SELECT id, name FROM users WHERE email = ?', (email,)).fetchone()

        if user:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(hours=24)
            conn.execute('DELETE FROM reset_tokens WHERE user_id = ?', (user['id'],))
            conn.execute('''
                INSERT INTO reset_tokens (user_id, token, expires_at)
                VALUES (?, ?, ?)
            ''', (user['id'], token, expires_at))
            conn.commit()
            reset_link = url_for('reset_password', token=token, _external=True)
            
            send_password_reset_email(user['name'], email, reset_link)
            flash('A password reset link has been sent to your email address.', 'success')
        else:
            flash('If an account exists with that email, you will receive a reset link.', 'info')

        conn.close()
        return redirect(url_for('login'))

    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if session.get('role'):
        return redirect(url_for('index'))

    conn = get_db()
    reset = conn.execute('''
        SELECT user_id, expires_at FROM reset_tokens
        WHERE token = ?
    ''', (token,)).fetchone()

    if not reset:
        flash('Invalid or expired reset link.', 'error')
        conn.close()
        return redirect(url_for('login'))

    if datetime.now() > datetime.fromisoformat(reset['expires_at']):
        conn.execute('DELETE FROM reset_tokens WHERE token = ?', (token,))
        conn.commit()
        conn.close()
        flash('Reset link has expired.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm  = request.form.get('confirm_password', '')

        if len(password) < 8 or len(password) > 16:
            flash('Password must be between 8 and 16 characters.', 'error')
            return render_template('reset_password.html', token=token)

        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('reset_password.html', token=token)

        conn.execute('''
            UPDATE users SET password = ? WHERE id = ?
        ''', (hash_password(password), reset['user_id']))
        conn.execute('DELETE FROM reset_tokens WHERE token = ?', (token,))
        conn.commit()
        conn.close()

        flash('Password has been reset. Please sign in with your new password.', 'success')
        return redirect(url_for('login'))

    conn.close()
    return render_template('reset_password.html', token=token)


# ============================================
#  STUDENT ROUTES
# ============================================

@app.route('/dashboard')
def dashboard():
    if not require_login():
        return redirect(url_for('login'))
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))
    if session.get('role') == 'host':
        return redirect(url_for('host_dashboard'))

    today = date.today().isoformat()
    current_time = datetime.now().strftime('%H:%M')
    conn  = get_db()
    uid   = session['user_id']

    my_workshops = conn.execute('''
        SELECT w.*, u.name AS created_by_name,
               (SELECT rating FROM feedback WHERE workshop_id = w.id AND user_id = ?) AS my_rating
        FROM registrations r
        JOIN workshops w ON r.workshop_id = w.id
        JOIN users u ON w.created_by = u.id
        WHERE r.user_id = ?
        ORDER BY w.date ASC, w.start_time ASC
    ''', (uid, uid)).fetchall()

    conn.close()
    return render_template('dashboard.html', workshops=my_workshops, today=today, current_time=current_time)


@app.route('/workshops/<int:workshop_id>/respond', methods=['GET'])
def respond(workshop_id):
    if not require_login():
        return redirect(url_for('login'))
    if session.get('role') != 'student':
        flash('Only students can leave feedback.', 'error')
        return redirect(url_for('dashboard'))
    
    conn = get_db()
    workshop = conn.execute(
        'SELECT title, date, end_time FROM workshops WHERE id = ?',
        (workshop_id,)
    ).fetchone()
    conn.close()
    
    if not workshop:
        flash('Workshop not found.', 'error')
        return redirect(url_for('dashboard'))
    
    return render_template('respond.html', workshop=workshop)


@app.route('/workshops/<int:workshop_id>/feedback', methods=['POST'])
def leave_feedback(workshop_id):
    if not require_login():
        return redirect(url_for('login'))
    if session.get('role') != 'student':
        flash('Only students can leave feedback.', 'error')
        return redirect(url_for('dashboard'))

    conn = get_db()
    uid = session['user_id']

    # Check if user registered for this workshop
    reg = conn.execute('''
        SELECT 1 FROM registrations WHERE user_id = ? AND workshop_id = ?
    ''', (uid, workshop_id)).fetchone()

    if not reg:
        flash('You did not register for this workshop.', 'error')
        conn.close()
        return redirect(url_for('dashboard'))

    workshop = conn.execute(
        'SELECT title, date, end_time FROM workshops WHERE id = ?',
        (workshop_id,)
    ).fetchone()

    today = date.today().isoformat()
    current_time = datetime.now().strftime('%H:%M')

    # Check if workshop has ended
    if workshop['date'] > today or (workshop['date'] == today and workshop['end_time'] > current_time):
        flash('You can only leave feedback after the workshop has ended.', 'error')
        conn.close()
        return redirect(url_for('dashboard'))

    # Check if already left feedback
    existing = conn.execute(
        'SELECT id FROM feedback WHERE workshop_id = ? AND user_id = ?',
        (workshop_id, uid)
    ).fetchone()

    if existing:
        flash('You have already left feedback for this workshop.', 'warning')
        conn.close()
        return redirect(url_for('dashboard'))

    # Process the feedback
    rating = request.form.get('rating', '').strip()
    comment = request.form.get('comment', '').strip()

    if not rating or not rating.isdigit() or int(rating) < 1 or int(rating) > 5:
        flash('Please select a rating between 1 and 5.', 'error')
        conn.close()
        return redirect(url_for('respond', workshop_id=workshop_id))

    conn.execute('''
        INSERT INTO feedback (workshop_id, user_id, rating, comment)
        VALUES (?, ?, ?, ?)
    ''', (workshop_id, uid, int(rating), comment))
    conn.commit()
    conn.close()

    flash(f'Thank you for your feedback on "{workshop["title"]}"!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/workshops/<int:workshop_id>/join', methods=['POST'])
def join_workshop(workshop_id):
    if not require_login():
        return redirect(url_for('login'))
    if session.get('role') == 'admin':
        flash('Admins cannot register for workshops.', 'warning')
        return redirect(url_for('workshops'))

    conn = get_db()
    workshop = conn.execute(
        'SELECT * FROM workshops WHERE id = ? AND status = "approved"',
        (workshop_id,)
    ).fetchone()

    if not workshop:
        flash('Workshop not found.', 'error')
        conn.close()
        return redirect(url_for('workshops'))

    same_day = conn.execute('''
        SELECT w.title, w.start_time, w.end_time
        FROM registrations r
        JOIN workshops w ON r.workshop_id = w.id
        WHERE r.user_id = ? AND w.date = ?
    ''', (session['user_id'], workshop['date'])).fetchall()

    for existing in same_day:
        if times_overlap(
            workshop['start_time'], workshop['end_time'],
            existing['start_time'], existing['end_time']
        ):
            flash(
                f'Time conflict — "{existing["title"]}" runs from '
                f'{existing["start_time"]} to {existing["end_time"]}, '
                f'which overlaps with this workshop.',
                'error'
            )
            conn.close()
            return redirect(url_for('workshops'))

    try:
        conn.execute('''
            INSERT INTO registrations (user_id, workshop_id) VALUES (?, ?)
        ''', (session['user_id'], workshop_id))
        conn.commit()
        
        user = conn.execute('SELECT name FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        send_registration_email(
            user['name'],
            session['email'],
            workshop['title'],
            workshop['date'],
            f"{workshop['start_time']} - {workshop['end_time']}",
            workshop['teams_link']
        )
        
        flash(f'You have registered for "{workshop["title"]}". A confirmation email has been sent.', 'success')

    except sqlite3.IntegrityError:
        flash('You are already registered for this workshop.', 'warning')

    finally:
        conn.close()

    return redirect(url_for('workshops'))


@app.route('/workshops/<int:workshop_id>/unregister', methods=['POST'])
def unregister_workshop(workshop_id):
    if not require_login():
        return redirect(url_for('login'))

    conn = get_db()
    conn.execute('''
        DELETE FROM registrations WHERE user_id = ? AND workshop_id = ?
    ''', (session['user_id'], workshop_id))
    conn.commit()
    conn.close()

    flash('Your registration has been cancelled.', 'info')
    return redirect(request.referrer or url_for('workshops'))


# ============================================
#  CALENDAR API
# ============================================

@app.route('/api/calendar-workshops')
def calendar_workshops_api():
    if not session.get('role') or session.get('role') == 'admin':
        return jsonify([])

    conn = get_db()
    rows = conn.execute('''
        SELECT w.title, w.date, w.start_time, w.end_time
        FROM registrations r
        JOIN workshops w ON r.workshop_id = w.id
        WHERE r.user_id = ?
        ORDER BY w.date ASC, w.start_time ASC
    ''', (session['user_id'],)).fetchall()
    conn.close()

    return jsonify([{
        'title':      row['title'],
        'date':       row['date'],
        'start_time': row['start_time'],
        'end_time':   row['end_time']
    } for row in rows])


# ============================================
#  NOTIFICATION BELL API
# ============================================

@app.route('/api/upcoming-workshops')
def upcoming_workshops_api():
    if not session.get('role') or session.get('role') == 'admin':
        return jsonify([])

    now = datetime.now()
    today = now.date()
    in_7_days = today + timedelta(days=7)

    conn = get_db()
    rows = conn.execute('''
        SELECT w.title, w.date, w.start_time, w.end_time
        FROM registrations r
        JOIN workshops w ON r.workshop_id = w.id
        WHERE r.user_id = ?
          AND w.date BETWEEN ? AND ?
        ORDER BY w.date ASC, w.start_time ASC
    ''', (
        session['user_id'],
        today.isoformat(),
        in_7_days.isoformat()
    )).fetchall()
    conn.close()

    result = []
    for row in rows:
        workshop_date = date.fromisoformat(row['date'])
        days_away = (workshop_date - today).days

        minutes_away = None
        urgent = False

        if workshop_date == today:
            start_h, start_m = map(int, row['start_time'].split(':'))
            workshop_start = datetime(now.year, now.month, now.day, start_h, start_m)
            minutes_away = int((workshop_start - now).total_seconds() / 60)

            if minutes_away > 0 and minutes_away <= 30:
                urgent = True
            elif minutes_away <= 0:
                minutes_away = 0

        result.append({
            'title':        row['title'],
            'date':         row['date'],
            'time':         f"{row['start_time']} - {row['end_time']}",
            'days_away':    days_away,
            'minutes_away': minutes_away,
            'urgent':       urgent
        })

    return jsonify(result)


# ============================================
#  HOST ROUTES
# ============================================

@app.route('/host/dashboard')
def host_dashboard():
    if not require_login():
        return redirect(url_for('login'))
    if session.get('role') not in ('host', 'admin'):
        flash('Host access required.', 'error')
        return redirect(url_for('dashboard'))

    today = date.today().isoformat()
    current_time = datetime.now().strftime('%H:%M')
    conn  = get_db()
    uid   = session['user_id']

    my_workshops = conn.execute('''
        SELECT w.*, COUNT(r.id) AS registration_count
        FROM workshops w
        LEFT JOIN registrations r ON r.workshop_id = w.id
        WHERE w.created_by = ?
        GROUP BY w.id
        ORDER BY w.date ASC
    ''', (uid,)).fetchall()

    attending = conn.execute('''
        SELECT w.*, u.name AS created_by_name
        FROM registrations r
        JOIN workshops w ON r.workshop_id = w.id
        JOIN users u ON w.created_by = u.id
        WHERE r.user_id = ? AND w.created_by != ?
        ORDER BY w.date ASC
    ''', (uid, uid)).fetchall()

    conn.close()
    return render_template(
        'host_dashboard.html',
        my_workshops=my_workshops,
        attending=attending,
        today=today,
        current_time=current_time
    )


@app.route('/host/workshops/<int:workshop_id>/feedback')
def host_view_feedback(workshop_id):
    if not require_login():
        return redirect(url_for('login'))
    if session.get('role') not in ('host', 'admin'):
        flash('Access denied.', 'error')
        return redirect(url_for('host_dashboard'))

    conn = get_db()
    uid = session['user_id']

    workshop = conn.execute('''
        SELECT * FROM workshops WHERE id = ? AND created_by = ?
    ''', (workshop_id, uid)).fetchone()

    if not workshop and session.get('role') != 'admin':
        flash('This workshop does not belong to you.', 'error')
        conn.close()
        return redirect(url_for('host_dashboard'))

    feedback = conn.execute('''
        SELECT f.*, u.name AS student_name
        FROM feedback f
        JOIN users u ON f.user_id = u.id
        WHERE f.workshop_id = ?
        ORDER BY f.created_at DESC
    ''', (workshop_id,)).fetchall()

    avg_rating = conn.execute('''
        SELECT AVG(rating) as avg, COUNT(*) as count
        FROM feedback WHERE workshop_id = ?
    ''', (workshop_id,)).fetchone()

    conn.close()
    return render_template(
        'host_feedback.html',
        workshop=workshop,
        feedback=feedback,
        avg_rating=avg_rating['avg'],
        feedback_count=avg_rating['count']
    )


@app.route('/host/create', methods=['GET', 'POST'])
def host_create_workshop():
    if not require_login():
        return redirect(url_for('login'))
    if session.get('role') not in ('host', 'admin'):
        flash('Host access required.', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        date_val    = request.form.get('date', '').strip()
        start_time  = request.form.get('start_time', '').strip()
        end_time    = request.form.get('end_time', '').strip()
        teams_link  = request.form.get('teams_link', '').strip()

        if not title:
            flash('Title is required.', 'error')
            return render_template('host_create_workshop.html', today=date.today().isoformat())
        if not date_val:
            flash('Date is required.', 'error')
            return render_template('host_create_workshop.html', today=date.today().isoformat())
        if not start_time:
            flash('Start time is required.', 'error')
            return render_template('host_create_workshop.html', today=date.today().isoformat())
        if not end_time:
            flash('End time is required.', 'error')
            return render_template('host_create_workshop.html', today=date.today().isoformat())
        if not description:
            flash('Description is required.', 'error')
            return render_template('host_create_workshop.html', today=date.today().isoformat())
        if end_time <= start_time:
            flash('End time must be after start time.', 'error')
            return render_template('host_create_workshop.html', today=date.today().isoformat())

        conn = get_db()
        conn.execute('''
            INSERT INTO workshops (title, description, date, start_time, end_time, teams_link, created_by, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')
        ''', (title, description, date_val, start_time, end_time, teams_link or None, session['user_id']))
        conn.commit()
        conn.close()

        flash(f'"{title}" submitted for admin approval.', 'success')
        return redirect(url_for('host_dashboard'))

    today = date.today().isoformat()
    return render_template('host_create_workshop.html', today=today)


@app.route('/host/workshops/<int:workshop_id>/delete', methods=['POST'])
def host_delete_workshop(workshop_id):
    if not require_login():
        return redirect(url_for('login'))

    conn = get_db()
    workshop = conn.execute(
        'SELECT * FROM workshops WHERE id = ? AND created_by = ?',
        (workshop_id, session['user_id'])
    ).fetchone()

    if workshop:
        conn.execute('DELETE FROM feedback WHERE workshop_id = ?', (workshop_id,))
        conn.execute('DELETE FROM registrations WHERE workshop_id = ?', (workshop_id,))
        conn.execute('DELETE FROM workshops WHERE id = ?', (workshop_id,))
        conn.commit()
        flash(f'"{workshop["title"]}" has been deleted.', 'info')
    else:
        flash('Workshop not found or access denied.', 'error')

    conn.close()
    return redirect(url_for('host_dashboard'))


# ============================================
#  ADMIN ROUTES
# ============================================

@app.route('/admin')
def admin_dashboard():
    if not require_login(role='admin'):
        return redirect(url_for('login'))

    today = date.today().isoformat()
    current_time = datetime.now().strftime('%H:%M')
    conn  = get_db()

    all_workshops = conn.execute('''
        SELECT w.*, u.name AS created_by_name,
               COUNT(r.id) AS registration_count
        FROM workshops w
        JOIN users u ON w.created_by = u.id
        LEFT JOIN registrations r ON r.workshop_id = w.id
        GROUP BY w.id
        ORDER BY w.date ASC, w.start_time ASC
    ''').fetchall()

    pending_workshops = conn.execute('''
        SELECT w.*, u.name AS created_by_name
        FROM workshops w
        JOIN users u ON w.created_by = u.id
        WHERE w.status = 'pending'
        ORDER BY w.date ASC
    ''').fetchall()

    total_students = conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'student'"
    ).fetchone()[0]

    total_hosts = conn.execute(
        "SELECT COUNT(*) FROM users WHERE role = 'host'"
    ).fetchone()[0]

    total_registrations = conn.execute(
        "SELECT COUNT(*) FROM registrations"
    ).fetchone()[0]

    conn.close()
    return render_template(
        'admin_dashboard.html',
        all_workshops=all_workshops,
        pending_workshops=pending_workshops,
        total_students=total_students,
        total_hosts=total_hosts,
        total_registrations=total_registrations,
        today=today,
        current_time=current_time
    )


@app.route('/admin/workshops/<int:workshop_id>/approve', methods=['POST'])
def approve_workshop(workshop_id):
    if not require_login(role='admin'):
        return redirect(url_for('login'))

    conn = get_db()
    workshop = conn.execute('''
        SELECT w.*, u.name AS host_name, u.email AS host_email
        FROM workshops w
        JOIN users u ON w.created_by = u.id
        WHERE w.id = ?
    ''', (workshop_id,)).fetchone()

    if workshop:
        conn.execute(
            "UPDATE workshops SET status = 'approved' WHERE id = ?",
            (workshop_id,)
        )
        conn.commit()
        
        send_workshop_approved_email(
            workshop['host_name'],
            workshop['host_email'],
            workshop['title']
        )
        
        flash(f'"{workshop["title"]}" approved and is now visible to students. Email sent to host.', 'success')
    else:
        flash('Workshop not found.', 'error')

    conn.close()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/workshops/<int:workshop_id>/reject', methods=['POST'])
def reject_workshop(workshop_id):
    if not require_login(role='admin'):
        return redirect(url_for('login'))

    conn = get_db()
    workshop = conn.execute(
        'SELECT title FROM workshops WHERE id = ?', (workshop_id,)
    ).fetchone()

    if workshop:
        conn.execute(
            "UPDATE workshops SET status = 'rejected' WHERE id = ?",
            (workshop_id,)
        )
        conn.commit()
        flash(f'"{workshop["title"]}" has been rejected.', 'info')
    else:
        flash('Workshop not found.', 'error')

    conn.close()
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/workshops/create', methods=['GET', 'POST'])
def create_workshop():
    if not require_login(role='admin'):
        return redirect(url_for('login'))

    if request.method == 'POST':
        title       = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        date_val    = request.form.get('date', '').strip()
        start_time  = request.form.get('start_time', '').strip()
        end_time    = request.form.get('end_time', '').strip()
        teams_link  = request.form.get('teams_link', '').strip()

        if not title:
            flash('Title is required.', 'error')
            return render_template('create_workshop.html', today=date.today().isoformat())
        if not date_val:
            flash('Date is required.', 'error')
            return render_template('create_workshop.html', today=date.today().isoformat())
        if not start_time:
            flash('Start time is required.', 'error')
            return render_template('create_workshop.html', today=date.today().isoformat())
        if not end_time:
            flash('End time is required.', 'error')
            return render_template('create_workshop.html', today=date.today().isoformat())
        if not description:
            flash('Description is required.', 'error')
            return render_template('create_workshop.html', today=date.today().isoformat())
        if end_time <= start_time:
            flash('End time must be after start time.', 'error')
            return render_template('create_workshop.html', today=date.today().isoformat())

        ensure_admin_in_db()
        conn = get_db()
        admin_row = conn.execute(
            'SELECT id FROM users WHERE email = ?', (ADMIN_EMAIL,)
        ).fetchone()

        conn.execute('''
            INSERT INTO workshops (title, description, date, start_time, end_time, teams_link, created_by, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'approved')
        ''', (title, description, date_val, start_time, end_time, teams_link or None, admin_row['id']))
        conn.commit()
        conn.close()

        flash(f'Workshop "{title}" created and published.', 'success')
        return redirect(url_for('admin_dashboard'))

    today = date.today().isoformat()
    return render_template('create_workshop.html', today=today)


@app.route('/admin/workshops/<int:workshop_id>/delete', methods=['POST'])
def delete_workshop(workshop_id):
    if not require_login(role='admin'):
        return redirect(url_for('login'))

    conn = get_db()
    workshop = conn.execute(
        'SELECT title FROM workshops WHERE id = ?', (workshop_id,)
    ).fetchone()

    if workshop:
        conn.execute('DELETE FROM feedback WHERE workshop_id = ?', (workshop_id,))
        conn.execute('DELETE FROM registrations WHERE workshop_id = ?', (workshop_id,))
        conn.execute('DELETE FROM workshops WHERE id = ?', (workshop_id,))
        conn.commit()
        flash(f'"{workshop["title"]}" has been deleted.', 'info')
    else:
        flash('Workshop not found.', 'error')

    conn.close()
    return redirect(url_for('admin_dashboard'))


# ============================================
#  ADMIN — USER MANAGEMENT
# ============================================

@app.route('/admin/students')
def admin_students():
    if not require_login(role='admin'):
        return redirect(url_for('login'))

    conn = get_db()
    students = conn.execute('''
        SELECT u.id, u.name, u.email, u.archived,
               COUNT(r.id) AS registration_count
        FROM users u
        LEFT JOIN registrations r ON r.user_id = u.id
        WHERE u.role = 'student'
        GROUP BY u.id
        ORDER BY u.archived ASC, u.name ASC
    ''').fetchall()
    conn.close()

    return render_template('admin_students.html', students=students)


@app.route('/admin/hosts')
def admin_hosts():
    if not require_login(role='admin'):
        return redirect(url_for('login'))

    conn = get_db()
    hosts = conn.execute('''
        SELECT u.id, u.name, u.email, u.archived,
               COUNT(w.id) AS workshop_count
        FROM users u
        LEFT JOIN workshops w ON w.created_by = u.id
        WHERE u.role = 'host'
        GROUP BY u.id
        ORDER BY u.archived ASC, u.name ASC
    ''').fetchall()
    conn.close()

    return render_template('admin_hosts.html', hosts=hosts)


@app.route('/admin/users/<int:user_id>/archive', methods=['POST'])
def archive_user(user_id):
    if not require_login(role='admin'):
        return redirect(url_for('login'))

    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

    if user:
        new_status = 0 if user['archived'] else 1
        conn.execute('UPDATE users SET archived = ? WHERE id = ?', (new_status, user_id))
        conn.commit()
        action = 'archived' if new_status else 'restored'
        flash(f'{user["name"]} has been {action}.', 'info')
    else:
        flash('User not found.', 'error')

    conn.close()
    return redirect(request.referrer or url_for('admin_students'))


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
def delete_user(user_id):
    if not require_login(role='admin'):
        return redirect(url_for('login'))

    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()

    if user:
        role = user['role']
        conn.execute('DELETE FROM feedback WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM registrations WHERE user_id = ?', (user_id,))
        conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
        conn.commit()
        flash(f'{user["name"]} has been permanently deleted.', 'info')
        conn.close()
        if role == 'host':
            return redirect(url_for('admin_hosts'))
        return redirect(url_for('admin_students'))

    flash('User not found.', 'error')
    conn.close()
    return redirect(url_for('admin_students'))


# ============================================
#  START
# ============================================

if __name__ == '__main__':
    init_db()
    ensure_admin_in_db()
    app.run(debug=True)