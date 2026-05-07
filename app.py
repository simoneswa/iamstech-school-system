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


# --- Flask App & Production Config ---
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "iamstech_secret_2026")

# --- Database Configuration ---
db_url = os.environ.get("DATABASE_URL")
force_sqlite = os.environ.get("FORCE_SQLITE", "False").lower() == "true"

if db_url and not force_sqlite:
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
else:
    # Priority 1: Railway Persistent Volume
    if os.path.exists('/data'):
        db_path = '/data/iamstech.db'
    # Priority 2: Vercel Temporary Store (non-persistent)
    elif os.path.exists('/tmp'):
        db_path = '/tmp/iamstech.db'
    # Priority 3: Local Development
    else:
        db_path = os.path.join(app.instance_path, 'iamstech.db')
        
    # Ensure the directory exists
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{db_path}"

app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Mail Config from Environment ---
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')

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

# --- File Upload Config ---
# Use Railway Volume if available, else fallback to static
UPLOAD_BASE = '/data' if os.path.exists('/data') else os.path.join(app.root_path, 'static')
app.config['UPLOAD_FOLDER'] = os.path.join(UPLOAD_BASE, 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'profiles'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'activities'), exist_ok=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_now():
    return {'datetime': datetime}

# --- Utility Functions ---
def generate_student_id():
    year = datetime.now().year
    count = User.query.filter(User.role == 'Student').count() + 1
    return f"IAM-{year}-{count:04d}"

# --- Routes ---
@app.route('/')
def index():
    try:
        announcements = Announcement.query.order_by(Announcement.date.desc()).limit(3).all()
        activities = Activity.query.order_by(Activity.date.desc()).limit(4).all()
        founders = Founder.query.all()
        developers = Developer.query.all()
        return render_template('index.html', 
                             announcements=announcements, 
                             activities=activities,
                             founders=founders,
                             developers=developers)
    except Exception as e:
        logger.error(f"Index error: {e}")
        return render_template('index.html', announcements=[], activities=[], founders=[], developers=[])

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter((User.email == email) | (User.student_id == email)).first()
        
        if user and check_password_hash(user.password, password):
            if user.status != 'Approved':
                flash('Your account is pending approval by the administrator.', 'warning')
                return redirect(url_for('login'))
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials. Please try again.', 'danger')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        dept = request.form.get('department')
        photo = request.files.get('profile_photo')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('register'))
            
        filename = None
        if photo:
            filename = secure_filename(f"{email}_{photo.filename}")
            photo.save(os.path.join(app.config['UPLOAD_FOLDER'], 'profiles', filename))
            
        new_user = User(
            name=name,
            email=email,
            phone=phone,
            department=dept,
            role='Student',
            status='Pending',
            profile_photo=f"uploads/profiles/{filename}" if filename else None,
            password=generate_password_hash('pending_activation')
        )
        db.session.add(new_user)
        db.session.commit()
        
        flash('Application submitted! Our admin team will review and contact you.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'Admin':
        users = User.query.all()
        applicants = User.query.filter_by(status='Pending').all()
        teachers = User.query.filter_by(role='Teacher').all()
        courses = Course.query.all()
        announcements = Announcement.query.all()
        return render_template('dashboards/admin_new.html', 
                             users=users, 
                             applicants=applicants, 
                             teachers=teachers, 
                             courses=courses, 
                             announcements=announcements)
    elif current_user.role == 'Teacher':
        meetings = Meeting.query.filter_by(teacher_id=current_user.id).all()
        return render_template('dashboards/teacher.html', meetings=meetings)
    else:
        courses = Course.query.all() # In a real app, join with Enrollments
        return render_template('dashboards/student.html', courses=courses)

# --- Admin Controls ---
@app.route('/admin/approve/<int:user_id>')
@login_required
def approve_user(user_id):
    if current_user.role != 'Admin': return redirect(url_for('dashboard'))
    user = User.query.get_or_404(user_id)
    user.status = 'Approved'
    user.student_id = generate_student_id()
    user.school_email = f"{user.name.lower().replace(' ', '.')}.{user.id}@iamstech.edu"
    db.session.commit()
    flash(f'User {user.name} approved. ID: {user.student_id}', 'success')
    return redirect(url_for('dashboard'))

@app.route('/admin/reject/<int:user_id>')
@login_required
def reject_user(user_id):
    if current_user.role != 'Admin': return redirect(url_for('dashboard'))
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash('Application rejected and removed.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/admin/courses', methods=['POST'])
@login_required
def admin_manage_courses():
    if current_user.role != 'Admin': return redirect(url_for('dashboard'))
    name = request.form.get('name')
    code = request.form.get('code')
    t_id = request.form.get('teacher_id')
    desc = request.form.get('description')
    
    new_course = Course(name=name, code=code, teacher_id=t_id, description=desc)
    db.session.add(new_course)
    db.session.commit()
    flash('Course added successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/admin/add-activity', methods=['POST'])
@login_required
def admin_add_activity():
    if current_user.role != 'Admin': return redirect(url_for('dashboard'))
    title = request.form.get('title')
    desc = request.form.get('desc')
    photo = request.files.get('image')
    
    if photo:
        filename = secure_filename(f"activity_{photo.filename}")
        photo.save(os.path.join(app.config['UPLOAD_FOLDER'], 'activities', filename))
        new_act = Activity(title=title, description=desc, image_path=f"uploads/activities/{filename}")
        db.session.add(new_act)
        db.session.commit()
        flash('Activity uploaded to gallery!', 'success')
    return redirect(url_for('dashboard'))

# --- Helper Routes ---
@app.route('/chatbot', methods=['POST'])
def chatbot():
    data = request.json
    msg = data.get('message', '').lower()
    # Simple rule-based chatbot for school info
    response = "I'm the IAMSTECH Assistant. You can ask about programs, admissions, or faculty."
    if 'admission' in msg or 'apply' in msg:
        response = "Admissions for 2026 are open! Click 'Join IAMSTECH' to apply."
    elif 'program' in msg or 'course' in msg:
        response = "We offer Microsoft Office, QuickBooks, AI Techniques, and Hardware Engineering."
    return jsonify({"response": response})

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

# --- Production Entry Point for Vercel ---
def handler(event, context):
    return app(event, context)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=bool(os.environ.get('FLASK_DEBUG', False)))
