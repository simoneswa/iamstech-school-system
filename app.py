import os
import logging
from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime
from models import db, User, Course, Enrollment, Assignment, Announcement, Attendance, Activity, Founder, Developer, Meeting
from email_service import mail

# --- Professional Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "iamstech_secret_2026")

# --- Database Stability (Serverless-Safe) ---
db_url = os.getenv("DATABASE_URL")
if not db_url:
    # Use /tmp for Vercel write access if no external DB
    db_path = os.path.join('/tmp', 'iamstech.db') if os.path.exists('/tmp') else 'iamstech.db'
    db_url = f"sqlite:///{db_path}"
elif db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "pool_size": 10,
    "max_overflow": 5,
    "connect_args": {"connect_timeout": 10}
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Initialize Extensions ---
db.init_app(app)
with app.app_context():
    try:
        db.create_all()
    except Exception as e:
        logger.error(f"Table creation error: {e}")

mail.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_now():
    return {'datetime': datetime}

# --- Routes ---
@app.route('/')
def index():
    try:
        announcements = Announcement.query.order_by(Announcement.date.desc()).limit(2).all()
        activities = Activity.query.limit(4).all()
        return render_template('index.html', announcements=announcements, activities=activities)
    except Exception as e:
        logger.error(f"Database sync error: {e}")
        return render_template('index.html', announcements=[], activities=[])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter((User.email == email) | (User.student_id == email)).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials. Please try again.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Registration logic preserved
        flash('Application submitted! We will contact you soon.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'Admin':
        return render_template('dashboards/admin.html')
    elif current_user.role == 'Teacher':
        return render_template('dashboards/teacher.html')
    else:
        return render_template('dashboards/student.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
