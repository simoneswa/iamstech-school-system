import os
import logging
import re
from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime, timedelta
import uuid
import csv
import random
import io
from flask import send_file
from models import db, User, Course, Enrollment, Assignment, Announcement, Attendance, Activity, Founder, Developer, Meeting, AdminAuditLog, SystemAuditLog, Notification, GlobalAlert, HomePageSection
from email_service import mail, send_approval_email, send_reset_email

# --- Professional Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Flask App & Production Config ---
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "iamstech_secret_2026")

# --- Global Error Handlers ---
@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_server_error(e):
    db.session.rollback()
    return render_template('errors/500.html'), 500

@app.errorhandler(Exception)
def handle_exception(e):
    # Log the error
    logger.error(f"Unhandled Exception: {e}")
    db.session.rollback()
    # If we are in debug mode, let the default debugger handle it
    if app.debug:
        raise e
    return render_template('errors/500.html'), 500


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
mail.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- Security Decorators ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['Admin', 'SuperAdmin']:
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not getattr(current_user, 'is_superadmin', False):
            flash('SuperAdmin access required.', 'danger')
            # Log this unauthorized attempt if it was a regular Admin
            if current_user.role == 'Admin':
                log = AdminAuditLog(admin_id=current_user.id, action="Unauthorized SuperAdmin Access Attempt")
                db.session.add(log)
                db.session.commit()
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# --- Safe Database Initialization ---
_db_initialized = False

@app.before_request
def first_request_init():
    global _db_initialized
    if not _db_initialized:
        with app.app_context():
            try:
                db.create_all()
                # Auto-seed SuperAdmin if it doesn't exist
                super_admin = User.query.filter_by(email='simoneswaraykeepitup@founder').first()
                if not super_admin:
                    admin = User(
                        name='Lead Systems Developer',
                        email='simoneswaraykeepitup@founder',
                        school_email='super.admin@iamstech.edu',
                        password=generate_password_hash('2026Capt132005@'),
                        role='SuperAdmin',
                        registration_state='approved',
                        status='Approved',
                        must_change_password=False,
                        is_superadmin=True,
                        is_email_verified=True
                    )
                    db.session.add(admin)
                    db.session.commit()
                    logger.info("First-time setup: SuperAdmin account created.")
                elif super_admin.registration_state != 'approved':
                    super_admin.registration_state = 'approved'
                    super_admin.is_superadmin = True
                    super_admin.is_email_verified = True
                    db.session.commit()
                _db_initialized = True

            except Exception as e:
                logger.error(f"Startup Database Error: {e}")

@app.route('/health')
def health_check():
    return jsonify({
        "status": "healthy", 
        "database": str(db.engine.url.drivername),
        "initialized": _db_initialized
    }), 200

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
    context = {'datetime': datetime, 'notifications': [], 'global_alerts': []}
    try:
        if current_user.is_authenticated:
            unread_notifications = Notification.query.filter_by(
                user_id=current_user.id, is_read=False
            ).order_by(Notification.created_at.desc()).all()
            context['notifications'] = unread_notifications
    except Exception:
        pass

    try:
        active_alerts = GlobalAlert.query.filter_by(is_active=True).order_by(
            GlobalAlert.created_at.desc()
        ).all()
        context['global_alerts'] = active_alerts
    except Exception:
        pass

    return context

def log_audit(action, target_id=None, target_type=None):
    try:
        if current_user.is_authenticated:
            ip = request.remote_addr
            log = SystemAuditLog(
                user_id=current_user.id,
                action=action,
                target_id=target_id,
                target_type=target_type,
                ip_address=ip
            )
            db.session.add(log)
            db.session.commit()
    except Exception as e:
        logger.warning(f"Audit log write failed (non-critical): {e}")
        db.session.rollback()

# --- Utility Functions ---
def generate_institutional_id(role):
    prefix = "IAM2026-"
    if role == "Teacher":
        prefix = "TCH-IAM2026-"
    elif role == "Admin" or role == "SuperAdmin":
        prefix = "ADM-IAM2026-"
        
    last_user = User.query.filter(User.student_id.like(f"{prefix}%")).order_by(User.id.desc()).first()
    if last_user and last_user.student_id:
        try:
            last_num = int(last_user.student_id.split('-')[-1])
            new_num = last_num + 1
        except:
            new_num = 1
    else:
        new_num = 1
    return f"{prefix}{new_num:04d}"

def generate_institutional_email(name, role):
    base_name = name.lower().replace(' ', '.')
    domain = "student.iamtech.edu.lr"
    if role == "Teacher":
        domain = "faculty.iamtech.edu.lr"
    elif role in ["Admin", "SuperAdmin"]:
        domain = "admin.iamtech.edu.lr"
        
    email = f"{base_name}@{domain}"
    counter = 1
    while User.query.filter_by(school_email=email).first():
        email = f"{base_name}{counter}@{domain}"
        counter += 1
    return email

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
        user = User.query.filter((User.email == email) | (User.student_id == email) | (User.school_email == email)).first()
        
        if user:
            if getattr(user, 'is_suspended', False):
                reason = getattr(user, 'suspension_reason', 'Violation of platform policies.')
                flash(f'Your account has been suspended. Reason: {reason}', 'danger')
                try:
                    ip = request.remote_addr
                    db.session.add(SystemAuditLog(user_id=user.id, action='Failed Login (Suspended)', ip_address=ip))
                    db.session.commit()
                except Exception:
                    db.session.rollback()
                return redirect(url_for('login'))
                
            if check_password_hash(user.password, password):
                if not user.is_email_verified and not user.is_superadmin:
                    flash('Please verify your personal email address first.', 'warning')
                    return redirect(url_for('verify_email', user_id=user.id))
                    
                if user.registration_state != 'approved':
                    flash('Your account is pending approval by the administrator.', 'warning')
                    return redirect(url_for('login'))
                login_user(user)
                log_audit('Successful Login')
                return redirect(url_for('dashboard'))
                
            # Incorrect password - log it but don't crash
            try:
                ip = request.remote_addr
                db.session.add(SystemAuditLog(user_id=user.id, action='Failed Login (Wrong Password)', ip_address=ip))
                db.session.commit()
            except Exception:
                db.session.rollback()
            
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
        # 1. Basic Validation & Normalization
        name = name.strip() if name else ""
        email = email.strip().lower() if email else ""
        
        if not name or not email:
            flash('Full Name and Email Address are required.', 'danger')
            return redirect(url_for('register'))

        # 2. Check for existing user (case-insensitive)
        existing_user = User.query.filter(db.func.lower(User.email) == email).first()
        
        if existing_user:
            # Block only fully active, approved, and verified accounts
            if existing_user.is_email_verified and existing_user.registration_state == 'approved':
                flash('This email is already registered and active. Please login.', 'info')
                return redirect(url_for('login'))
            
            # If application is in progress, reuse the record
            user_to_save = existing_user
            logger.info(f"Re-using existing onboarding record for {email}")
        else:
            # Create new user record
            user_to_save = User(email=email, role='Student', name=name)
            db.session.add(user_to_save)
            logger.info(f"Creating new onboarding record for {email}")

        try:
            # 3. Handle File Upload (inside transaction block)
            if photo and photo.filename:
                # Ensure filename is safe and unique
                ext = photo.filename.rsplit('.', 1)[1].lower() if '.' in photo.filename else 'jpg'
                safe_name = f"{uuid.uuid4().hex[:10]}.{ext}"
                filename = secure_filename(f"{email.split('@')[0]}_{safe_name}")
                
                # Ensure directory exists (redundant but safe)
                profile_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'profiles')
                os.makedirs(profile_dir, exist_ok=True)
                
                photo.save(os.path.join(profile_dir, filename))
                user_to_save.profile_photo = f"uploads/profiles/{filename}"

            # 4. Generate fresh OTP and update state
            otp = f"{random.randint(100000, 999999)}"
            user_to_save.name = name  # Sync name in case it changed
            user_to_save.phone = phone
            user_to_save.department = dept
            user_to_save.registration_state = 'pending_verification'
            user_to_save.is_email_verified = False
            user_to_save.verification_code = otp
            user_to_save.verification_code_expires = datetime.utcnow() + timedelta(minutes=15)
            user_to_save.verification_attempts = 0
            
            # Ensure a password exists (UUID fallback if new)
            if not user_to_save.password:
                user_to_save.password = generate_password_hash(uuid.uuid4().hex)
            
            db.session.commit()
            logger.info(f"Registration committed for {email}. Sending OTP...")
            
            # 5. Send OTP (non-blocking failure)
            send_verification_otp(user_to_save, otp)
            
            flash('Verification code sent to your personal email.', 'info')
            return redirect(url_for('verify_email', user_id=user_to_save.id))
        except Exception as e:
            db.session.rollback()
            logger.error(f"CRITICAL REGISTRATION ERROR for {email}: {str(e)}")
            flash(f'System Error: {str(e)}', 'danger') if app.debug else flash('A system error occurred. Please try again or contact support.', 'danger')
            return redirect(url_for('register'))


    return render_template('register.html')

@app.route('/verify-email/<int:user_id>', methods=['GET', 'POST'])
def verify_email(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_email_verified:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        code = request.form.get('otp')
        
        if user.verification_attempts >= 5:
            flash('Too many failed attempts. Please request a new code.', 'danger')
            return redirect(url_for('verify_email', user_id=user.id))
            
        if datetime.utcnow() > user.verification_code_expires:
            flash('Verification code expired. Please request a new one.', 'danger')
            return redirect(url_for('verify_email', user_id=user.id))
            
        if code == user.verification_code:
            user.is_email_verified = True
            user.registration_state = 'verified_awaiting_approval'  # Move to admin review
            user.verification_code = None
            db.session.commit()
            return render_template('verification_success.html', name=user.name)
        else:
            user.verification_attempts += 1
            db.session.commit()
            flash('Invalid verification code. Please try again.', 'danger')
            
    return render_template('verify_email.html', user_id=user.id, email=user.email)

@app.route('/resend-verification/<int:user_id>')
def resend_verification(user_id):
    user = User.query.get_or_404(user_id)
    
    # Check cooldown
    if user.resend_cooldown and datetime.utcnow() < user.resend_cooldown:
        flash('Please wait before requesting another code.', 'warning')
        return redirect(url_for('verify_email', user_id=user.id))
        
    otp = f"{random.randint(100000, 999999)}"
    user.verification_code = otp
    user.verification_code_expires = datetime.utcnow() + timedelta(minutes=15)
    user.verification_attempts = 0
    user.resend_cooldown = datetime.utcnow() + timedelta(seconds=60)
    db.session.commit()
    
    send_verification_otp(user, otp)
    flash('A new verification code has been sent.', 'success')
    return redirect(url_for('verify_email', user_id=user.id))

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        if user:
            user.reset_token = str(uuid.uuid4())
            user.reset_token_expiration = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            send_reset_email(user)
            
            # Log it
            try:
                ip = request.remote_addr
                db.session.add(SystemAuditLog(user_id=user.id, action='Password Reset Requested', ip_address=ip))
                db.session.commit()
            except Exception:
                db.session.rollback()
            
        # Always show the same message to prevent email enumeration
        flash('If that email exists in our system, a password reset link has been sent.', 'info')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    if not user or getattr(user, 'reset_token_expiration', datetime.min) < datetime.utcnow():
        flash('Invalid or expired reset link.', 'danger')
        return redirect(url_for('forgot_password'))
        
    if request.method == 'POST':
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')
        
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('reset_password', token=token))
            
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return redirect(url_for('reset_password', token=token))
            
        user.password = generate_password_hash(password)
        user.reset_token = None
        user.must_change_password = False
        db.session.commit()
        
        # Log it
        try:
            ip = request.remote_addr
            db.session.add(SystemAuditLog(user_id=user.id, action='Password Successfully Reset', ip_address=ip))
            db.session.commit()
        except Exception:
            db.session.rollback()
        
        flash('Password has been successfully reset. You can now log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('reset_password.html', token=token)

@app.route('/dashboard')
@login_required
def dashboard():
    # Force password change if required
    if getattr(current_user, 'must_change_password', False) and not current_user.setup_token:
        # If they don't have a setup token but must change, it's the SuperAdmin first login
        # We can just redirect them to a profile/password change page. For now, we'll
        # just let them in but they should probably have a force-change UI.
        pass

    if current_user.role == 'SuperAdmin':
        users = User.query.all()
        admins = User.query.filter_by(role='Admin').all()
        applicants = User.query.filter_by(status='Pending').all()
        
        try:
            audit_logs = SystemAuditLog.query.order_by(SystemAuditLog.timestamp.desc()).limit(50).all()
        except Exception:
            audit_logs = []
            
        return render_template('dashboards/superadmin.html', 
                             users=users, 
                             admins=admins,
                             applicants=applicants,
                             audit_logs=audit_logs)
    elif current_user.role == 'Admin':
        users = User.query.filter(User.role != 'SuperAdmin').all() # Hide SuperAdmin
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
        # Gamification: Daily Login Reward
        today = datetime.utcnow().date()
        if getattr(current_user, 'last_login_reward_date', None) != today:
            current_user.points = (current_user.points or 0) + 10
            current_user.last_login_reward_date = today
            db.session.commit()
            flash('🎉 +10 XP for logging in today! Keep up the great work.', 'success')

        # Fetch student data
        enrollments = Enrollment.query.filter_by(student_id=current_user.id).all()
        courses = Course.query.all()

        # Attendance calculation
        total_att = Attendance.query.filter_by(student_id=current_user.id).count()
        present_att = Attendance.query.filter_by(student_id=current_user.id, status='Present').count()
        att_percent = (present_att / total_att * 100) if total_att > 0 else 0

        # Assignments from enrolled courses
        enrolled_course_ids = [e.course_id for e in enrollments]
        assignments = Assignment.query.filter(Assignment.course_id.in_(enrolled_course_ids)).all() if enrolled_course_ids else []

        # All meetings (students see all published meetings)
        meetings = Meeting.query.order_by(Meeting.date.desc()).all()

        # Leaderboard
        top_students = User.query.filter_by(role='Student', status='Approved').order_by(User.points.desc()).limit(10).all()
        rank = User.query.filter_by(role='Student', status='Approved').filter(User.points > (current_user.points or 0)).count() + 1

        return render_template('dashboards/student.html',
                               enrollments=enrollments,
                               courses=courses,
                               att_percent=att_percent,
                               assignments=assignments,
                               meetings=meetings,
                               top_students=top_students,
                               my_rank=rank)

# --- Admin Controls ---
@app.route('/admin/update-founder', methods=['POST'])
@login_required
@admin_required
def admin_update_founder():
    name = request.form.get('name')
    title = request.form.get('title')
    message = request.form.get('message')
    photo = request.files.get('image')
    
    founder = Founder.query.first() or Founder()
    founder.name = name
    founder.title = title
    founder.message = message
    
    if photo:
        filename = secure_filename(f"founder_{photo.filename}")
        photo.save(os.path.join(app.config['UPLOAD_FOLDER'], 'branding', filename))
        founder.image_path = f"uploads/branding/{filename}"
        
    db.session.add(founder)
    db.session.commit()
    flash('Founder information updated!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/admin/update-developer', methods=['POST'])
@login_required
@admin_required
def admin_update_developer():
    name = request.form.get('name')
    role = request.form.get('role')
    desc = request.form.get('description')
    photo = request.files.get('image')
    
    dev = Developer.query.first() or Developer()
    dev.name = name
    dev.role = role
    dev.description = desc
    
    if photo:
        filename = secure_filename(f"dev_{photo.filename}")
        photo.save(os.path.join(app.config['UPLOAD_FOLDER'], 'branding', filename))
        dev.image_path = f"uploads/branding/{filename}"
        
    db.session.add(dev)
    db.session.commit()
    flash('Developer information updated!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/superadmin/system-reset', methods=['POST'])
@login_required
@superadmin_required
def system_reset():
    try:
        # Delete all users EXCEPT SuperAdmins
        # This will also delete related records via cascade
        
        # 1. Delete audit logs first
        AdminAuditLog.query.filter(AdminAuditLog.admin_id.in_(
            db.session.query(User.id).filter(User.is_superadmin == False)
        )).delete(synchronize_session=False)
        
        SystemAuditLog.query.filter(SystemAuditLog.user_id.in_(
            db.session.query(User.id).filter(User.is_superadmin == False)
        )).delete(synchronize_session=False)
        
        # 2. Delete main user records
        deleted_count = User.query.filter(User.is_superadmin == False).delete(synchronize_session=False)
        
        db.session.commit()
        flash(f'System Reset Successful: {deleted_count} records cleared.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Reset Error: {str(e)}', 'danger')
        
    return redirect(url_for('dashboard'))

@app.route('/superadmin/cleanup-abandoned', methods=['POST'])
@login_required
@superadmin_required
def cleanup_abandoned():
    try:
        # 1. Delete expired OTP records (not verified and expired > 1 hour ago)
        expired_cutoff = datetime.utcnow() - timedelta(hours=1)
        abandoned = User.query.filter(
            User.is_email_verified == False,
            User.verification_code_expires < expired_cutoff,
            User.is_superadmin == False
        ).all()
        
        count = 0
        for u in abandoned:
            db.session.delete(u)
            count += 1
            
        db.session.commit()
        flash(f'Cleanup Successful: {count} abandoned registration records removed.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Cleanup Error: {str(e)}', 'danger')
        
    return redirect(url_for('dashboard'))

@app.route('/admin/approve/<int:user_id>')
@app.route('/approve/<int:user_id>') # Alias for compatibility
@login_required
@admin_required
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    user.registration_state = 'approved'
    user.student_id = generate_institutional_id(user.role)
    user.school_email = generate_institutional_email(user.name, user.role)
    
    # Generate secure setup token
    user.setup_token = str(uuid.uuid4())
    user.setup_token_expiration = datetime.utcnow() + timedelta(days=3)
    user.must_change_password = True
    
    db.session.commit()
    
    # Send activation email
    email_sent = send_approval_email(user)
    
    # Audit log
    try:
        action_text = f"Approved {user.role}" if email_sent else f"Approved {user.role} (Email Failed)"
        log = AdminAuditLog(admin_id=current_user.id, action=action_text, target_user_id=user.id)
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()
    
    if email_sent:
        flash(f'Success! {user.name} approved and institutional email sent.', 'success')
    else:
        setup_link = url_for('setup_account', token=user.setup_token, _external=True)
        flash(f'User approved, but the WELCOME EMAIL FAILED TO SEND. Please check your Railway SMTP environment variables (MAIL_USERNAME/PASSWORD).', 'danger')
        flash(f'MANUAL ACTIVATION LINK: {setup_link}', 'warning')
        
    return redirect(url_for('dashboard'))

@app.route('/setup-account/<token>', methods=['GET', 'POST'])
def setup_account(token):
    user = User.query.filter_by(setup_token=token).first()
    
    if not user:
        flash('Invalid or expired setup link.', 'danger')
        return redirect(url_for('login'))
        
    if user.setup_token_expiration < datetime.utcnow():
        flash('Setup link expired. Please contact administration.', 'danger')
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')
        
        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('setup_account', token=token))
            
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return redirect(url_for('setup_account', token=token))
            
        user.password = generate_password_hash(password)
        user.setup_token = None # Invalidate token
        user.must_change_password = False
        db.session.commit()
        
        flash('Account setup complete! You can now log in.', 'success')
        return redirect(url_for('login'))
        
    return render_template('setup_account.html', user=user)

@app.route('/admin/reject/<int:user_id>')
@login_required
@admin_required
def reject_user(user_id):
    user = User.query.get_or_404(user_id)
    
    try:
        log = AdminAuditLog(admin_id=current_user.id, action=f"Rejected {user.role}", target_user_id=user.id)
        db.session.add(log)
    except Exception:
        pass
    
    db.session.delete(user)
    db.session.commit()
    flash('Application rejected and removed.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/admin/courses', methods=['POST'])
@login_required
@admin_required
def admin_manage_courses():
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
@admin_required
def admin_add_activity():
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

# --- SuperAdmin Controls ---
@app.route('/superadmin/suspend/<int:user_id>', methods=['POST'])
@login_required
@superadmin_required
def suspend_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_superadmin:
        flash("Cannot suspend another SuperAdmin.", "danger")
        return redirect(url_for('dashboard'))
    
    reason = request.form.get('reason', 'Violation of platform policies.')
    user.is_suspended = True
    user.suspension_reason = reason
    db.session.commit()
    log_audit(f"Suspended {user.role}", target_id=user.id, target_type='User')
    flash(f'Account {user.email} suspended successfully.', 'warning')
    return redirect(url_for('dashboard'))

@app.route('/superadmin/reactivate/<int:user_id>', methods=['POST'])
@login_required
@superadmin_required
def reactivate_user(user_id):
    user = User.query.get_or_404(user_id)
    user.is_suspended = False
    user.suspension_reason = None
    db.session.commit()
    log_audit(f"Reactivated {user.role}", target_id=user.id, target_type='User')
    flash(f'Account {user.email} reactivated.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/superadmin/change-role/<int:user_id>', methods=['POST'])
@login_required
@superadmin_required
def change_role(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_superadmin:
        flash("Cannot modify SuperAdmin role.", "danger")
        return redirect(url_for('dashboard'))
        
    new_role = request.form.get('role')
    if new_role in ['Admin', 'Teacher', 'Student']:
        old_role = user.role
        user.role = new_role
        # Optional: regenerate ID based on new role
        db.session.commit()
        log_audit(f"Changed role from {old_role} to {new_role}", target_id=user.id, target_type='User')
        flash(f'Role updated to {new_role}.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/superadmin/broadcast', methods=['POST'])
@login_required
@superadmin_required
def broadcast_alert():
    message = request.form.get('message')
    alert_type = request.form.get('type', 'info')
    if message:
        alert = GlobalAlert(message=message, type=alert_type, created_by=current_user.id)
        db.session.add(alert)
        db.session.commit()
        log_audit("Created Global Alert")
        flash('Alert broadcasted across the system.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/superadmin/export/<data_type>')
@login_required
@superadmin_required
def export_data(data_type):
    si = io.StringIO()
    cw = csv.writer(si)
    
    if data_type == 'users':
        cw.writerow(['ID', 'Name', 'Email', 'Role', 'Status', 'Suspended'])
        users = User.query.all()
        for u in users:
            cw.writerow([u.student_id, u.name, u.email, u.role, u.registration_state, u.is_suspended])

        filename = f"iamstech_users_{datetime.now().strftime('%Y%m%d')}.csv"
        
    elif data_type == 'attendance':
        cw.writerow(['Date', 'Student ID', 'Course ID', 'Status'])
        records = Attendance.query.all()
        for a in records:
            cw.writerow([a.date.strftime('%Y-%m-%d'), a.student_id, a.course_id, a.status])
        filename = f"iamstech_attendance_{datetime.now().strftime('%Y%m%d')}.csv"
        
    else:
        flash("Invalid export type.", "danger")
        return redirect(url_for('dashboard'))
        
    log_audit(f"Exported {data_type} data")
    
    output = io.BytesIO()
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)
    
    return send_file(output, mimetype='text/csv', as_attachment=True, download_name=filename)

# --- Helper Routes ---
@app.route('/chatbot', methods=['POST'])
def chatbot():
    data = request.json
    msg = data.get('message', '').lower()
    # Institutional Knowledge Base
    responses = {
        "location": [
            "IAMSTECH LIBERIA is located at Hotel Africa Road, Banjor Junction, Brewerville City, Monrovia, Liberia. We are easily accessible from the main highway.",
            "You can find us in Brewerville City, specifically at the Banjor Junction on Hotel Africa Road. We welcome visitors during office hours!"
        ],
        "motto": [
            "Our institutional motto is: “Technology & Business Education for Future Professionals”. This guides every program we offer.",
            "“Technology & Business Education for Future Professionals” — that's the motto we live by at IAMSTECH."
        ],
        "about": [
            "IAMSTECH LIBERIA is a specialized institution dedicated to equipping students with cutting-edge skills in Information Technology and Accounting. We pride ourselves on hands-on vocational training.",
            "We are a premier technical institute in Liberia, focusing on practical IT and Accounting education to build the next generation of professionals."
        ],
        "vision": [
            "To become Liberia’s premier center of excellence for technology and business education, producing globally competitive professionals who lead digital transformation.",
            "Our vision is to lead digital transformation in Liberia by producing world-class tech and business professionals."
        ],
        "mission": [
            "To deliver industry-relevant, hands-on education in Information Technology and Accounting, empowering students with technical competence and ethical leadership.",
            "Our mission is simple: empower students through hands-on technical training and ethical leadership development."
        ],
        "programs": [
            "We offer professional certifications in Microsoft Office Suite, QuickBooks Accounting, AI Techniques, Computer Hardware Engineering, and more. Which one interests you?",
            "Our programs include Microsoft Office, QuickBooks, AI applications, and Hardware Engineering. All courses are hands-on and industry-focused."
        ],
        "admission": [
            "Admissions for the 2026 academic year are now open! You can register on this portal, verify your email, and wait for administrative approval.",
            "You can join IAMSTECH today! Just head over to the Registration page to start your application process."
        ],
        "founder": [
            "Mr. Benaiah Kanawa is our Founder & CEO. He is a visionary leader dedicated to bridging the technological gap in Liberia.",
            "Our institution was founded by Mr. Benaiah Kanawa, who serves as the CEO and Lead Visionary."
        ],
        "support": [
            "If you encounter any technical issues, please contact our support team via WhatsApp at +231 880 864 187 or visit the Technical Support Center in your dashboard.",
            "Need help? You can reach our technical support team at +231 880 864 187 (WhatsApp) or through your student dashboard."
        ],
        "fees": [
            "Tuition and registration fees vary by program. Please visit the Admissions office at our Banjor campus for a detailed fee schedule.",
            "For the most accurate fee information, we recommend visiting our campus office or contacting the finance department through the support line."
        ],
        "duration": [
            "Most of our certificate programs run for 3 to 6 months of intensive, hands-on training.",
            "Our professional courses typically take 3-6 months to complete, depending on the specific program."
        ],
        "greetings": [
            "Hello! I'm the IAMSTECH Assistant. How can I help you today?",
            "Greetings from IAMSTECH! What would you like to know about our programs or admissions?",
            "Hi there! Ready to start your professional journey with us? Ask me anything!"
        ]
    }

    # Intent Matching
    matched_intent = None
    if re.search(r'\b(location|where|address|locate|map|situated)\b', msg):
        matched_intent = "location"
    elif re.search(r'\b(motto|slogan|saying)\b', msg):
        matched_intent = "motto"
    elif re.search(r'\b(about|who|what|institution|iamstech|school|college|institute)\b', msg):
        matched_intent = "about"
    elif re.search(r'\b(vision|future|goal)\b', msg):
        matched_intent = "vision"
    elif re.search(r'\b(mission|purpose|aim)\b', msg):
        matched_intent = "mission"
    elif re.search(r'\b(program|course|study|learn|department|it|accounting|quickbooks|microsoft|ai|hardware)\b', msg):
        matched_intent = "programs"
    elif re.search(r'\b(admission|apply|join|enroll|register|form|apply)\b', msg):
        matched_intent = "admission"
    elif re.search(r'\b(founder|ceo|leader|benaiah|kanawa|head)\b', msg):
        matched_intent = "founder"
    elif re.search(r'\b(support|help|contact|phone|email|whatsapp|technical|broken|error)\b', msg):
        matched_intent = "support"
    elif re.search(r'\b(fee|cost|price|tuition|pay|money|scholarship)\b', msg):
        matched_intent = "fees"
    elif re.search(r'\b(duration|time|long|period|month|week|graduate)\b', msg):
        matched_intent = "duration"
    elif re.search(r'\b(hello|hi|hey|greetings|good morning|good afternoon|good evening|yo)\b', msg):
        matched_intent = "greetings"

    if matched_intent:
        response = random.choice(responses[matched_intent])
    else:
        # Contextual Fallback
        fallbacks = [
            "I'm not quite sure about that. Would you like to know about our IT and Accounting programs?",
            "I didn't catch that perfectly. I can help with admissions, location, or technical support. Which one do you need?",
            "Could you please rephrase? I'm specifically trained to help with IAMSTECH institutional information."
        ]
        response = random.choice(fallbacks)

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
