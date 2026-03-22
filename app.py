# ============================================
#  app.py — Student Workshop System
# ============================================

from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash, jsonify
)
import sqlite3
import hashlib
from datetime import date, timedelta

app = Flask(__name__)
app.secret_key = 'student-workshop-secret-2026'

DATABASE = 'workshop_system.db'

ADMIN_EMAIL    = 'admin@test.com'
ADMIN_PASSWORD = 'admin123'
ADMIN_NAME     = 'Administrator'


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
#  HELPERS
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

    if role == 'admin':
        all_workshops = conn.execute('''
            SELECT w.*, u.name AS created_by_name
            FROM workshops w
            JOIN users u ON w.created_by = u.id
            ORDER BY w.date ASC, w.start_time ASC
        ''').fetchall()
    elif role == 'host':
        all_workshops = conn.execute('''
            SELECT w.*, u.name AS created_by_name
            FROM workshops w
            JOIN users u ON w.created_by = u.id
            WHERE w.status = 'approved' OR w.created_by = ?
            ORDER BY w.date ASC, w.start_time ASC
        ''', (uid,)).fetchall()
    else:
        all_workshops = conn.execute('''
            SELECT w.*, u.name AS created_by_name
            FROM workshops w
            JOIN users u ON w.created_by = u.id
            WHERE w.status = 'approved'
            ORDER BY w.date ASC, w.start_time ASC
        ''').fetchall()

    registered_ids = []
    if uid and role != 'admin':
        rows = conn.execute(
            'SELECT workshop_id FROM registrations WHERE user_id = ?', (uid,)
        ).fetchall()
        registered_ids = [r['workshop_id'] for r in rows]

    today = date.today().isoformat()
    conn.close()
    return render_template(
        'workshops.html',
        workshops=all_workshops,
        registered_ids=registered_ids,
        today=today
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
            flash(f'Account created as {role_label}. Please sign in.', 'success')
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
    conn  = get_db()

    my_workshops = conn.execute('''
        SELECT w.*, u.name AS created_by_name
        FROM registrations r
        JOIN workshops w ON r.workshop_id = w.id
        JOIN users u ON w.created_by = u.id
        WHERE r.user_id = ?
        ORDER BY w.date ASC, w.start_time ASC
    ''', (session['user_id'],)).fetchall()

    conn.close()
    return render_template('dashboard.html', workshops=my_workshops, today=today)


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
        flash(f'You have registered for "{workshop["title"]}".', 'success')

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

    today     = date.today()
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
        days_away = (date.fromisoformat(row['date']) - today).days
        result.append({
            'title':     row['title'],
            'date':      row['date'],
            'time':      f"{row['start_time']} - {row['end_time']}",
            'days_away': days_away
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
        today=today
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
        today=today
    )


@app.route('/admin/workshops/<int:workshop_id>/approve', methods=['POST'])
def approve_workshop(workshop_id):
    if not require_login(role='admin'):
        return redirect(url_for('login'))

    conn = get_db()
    workshop = conn.execute(
        'SELECT title FROM workshops WHERE id = ?', (workshop_id,)
    ).fetchone()

    if workshop:
        conn.execute(
            "UPDATE workshops SET status = 'approved' WHERE id = ?",
            (workshop_id,)
        )
        conn.commit()
        flash(f'"{workshop["title"]}" approved and is now visible to students.', 'success')
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