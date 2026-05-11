# Build Trigger: Force Refresh 2026-05-11
import os
import logging
import re
import threading
from flask import Flask, render_template, redirect, url_for, request, flash, session, jsonify, abort
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
from supabase import create_client
from models import db, User, Course, Enrollment, Assignment, Announcement, Attendance, Activity, Founder, Developer, Meeting, LessonMaterial, AdminAuditLog, SystemAuditLog, Notification, GlobalAlert, HomePageSection, SystemReport
from email_service import mail, send_approval_email, send_reset_email, send_verification_otp, build_external_url
from werkzeug.middleware.proxy_fix import ProxyFix
from lib.storage import upload_to_bucket

# --- Professional Logging ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('IAMSTECH_SYS')

# --- Non-Blocking Email Dispatcher ---
def send_async_email(app, email_func, *args, **kwargs):
    def send_task(app_context, func, a, k):
        with app_context:
            try:
                func(*a, **k)
            except Exception as e:
                logger.error(f"ASYNC EMAIL FAILURE: {e}")

    thread = threading.Thread(target=send_task, args=(app.app_context(), email_func, args, kwargs))
    thread.start()

# --- Flask App & Production Config ---
app = Flask(__name__)
# CRITICAL: ProxyFix for Railway (Fixes invalid _external=True URLs)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.secret_key = os.environ.get("SECRET_KEY", "iamstech_secret_2026")
app.config['DEV_MODE'] = os.environ.get("DEV_MODE", "false").lower() == "true"
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB Upload Limit
app.config['BASE_URL'] = os.environ.get('IAMSTECH_BASE_URL', '').strip().rstrip('/') or None
app.config['PREFERRED_URL_SCHEME'] = 'https'

# --- Email Configuration (SMTP Fallback) ---
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 465))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'false').lower() in ['true', 'on', '1']
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'true').lower() in ['true', 'on', '1']
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER') or os.environ.get('MAIL_USERNAME')
# NOTE: SERVER_NAME is intentionally NOT set — setting it causes Flask to
# return 404 for all routes when the configured value doesn't exactly match
# the Host header (e.g. after a Railway domain rename). ProxyFix handles
# correct external URL generation instead.

@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html', title="Page Not Found"), 404

@app.errorhandler(500)
def handle_500(e):
    import traceback
    db.session.rollback()
    error_details = traceback.format_exc()
    logger.critical(f"INTERNAL SERVER ERROR (500):\n{error_details}")
    
    # Capture to diagnostic file
    try:
        os.makedirs('scratch', exist_ok=True)
        with open('scratch/last_500_error.txt', 'w') as f:
            f.write(error_details)
    except: pass
    
    # Return professional error page with diagnostic info
    return render_template('errors/500.html', error=e, error_details=error_details), 500

@app.errorhandler(Exception)
def handle_exception(e):
    # This catches unhandled exceptions that aren't explicitly 500s
    return handle_500(e)


# --- Database Configuration ---
db_url = os.environ.get("DATABASE_URL", "").strip()
force_sqlite = os.environ.get("FORCE_SQLITE", "False").lower() == "true"

def _get_db_uri():
    """Parse DATABASE_URL safely. Returns a valid SQLAlchemy URI or falls back to SQLite."""
    if db_url and not force_sqlite:
        try:
            # Fix legacy postgres:// scheme
            url = db_url
            if url.startswith("postgres://"):
                url = url.replace("postgres://", "postgresql://", 1)
            
            # Remove pgbouncer=true if it exists in the query string as it can cause psycopg2 errors
            if "pgbouncer=true" in url:
                url = url.replace("pgbouncer=true", "")
                url = url.replace("??", "?").replace("?&", "?").rstrip("?&")
                logger.info("MIGRATION: Removed 'pgbouncer=true' from DATABASE_URL for compatibility.")

            # Validate it looks like a real URL (has @host:port pattern)
            if "@" not in url or "://" not in url:
                raise ValueError(f"DATABASE_URL appears malformed (missing @ or ://): {url[:60]}")
            
            logger.info(f"DB: Using PostgreSQL (host={url.split('@')[-1].split('/')[0]})")
            return url
        except Exception as e:
            logger.critical(f"DATABASE_URL PARSE ERROR: {e} — falling back to SQLite")

    # SQLite fallback
    if os.path.exists('/data'):
        db_path = '/data/iamstech.db'
    elif os.path.exists(app.instance_path):
        db_path = os.path.join(app.instance_path, 'iamstech.db')
    elif os.path.exists('/tmp'):
        db_path = '/tmp/iamstech.db'
    else:
        db_path = 'iamstech.db'

    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    logger.warning(f"DB: Using SQLite fallback at {db_path}")
    return f"sqlite:///{db_path}?timeout=30"

app.config['SQLALCHEMY_DATABASE_URI'] = _get_db_uri()
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 280,
    "pool_timeout": 30,
    "pool_size": 10,
    "max_overflow": 5,
    "connect_args": {"connect_timeout": 10} if "postgresql" in app.config['SQLALCHEMY_DATABASE_URI'] else {},
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- Initialize Extensions ---
db.init_app(app)
with app.app_context():
    try:
        db.create_all()
        # --- EXHAUSTIVE AUTO-MIGRATION (Full Spectrum) ---
        from sqlalchemy import text, inspect
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        # Helper to safely add column
        def safe_add_column(table_name, col_name, col_type):
            try:
                columns = [c['name'] for c in inspector.get_columns(table_name)]
                if col_name not in columns:
                    logger.info(f"MIGRATION: Adding column {col_name} to '{table_name}'...")
                    # Quote table name for reserved words like "user"
                    quoted_table = f'"{table_name}"' if table_name.lower() == 'user' else table_name
                    db.session.execute(text(f"ALTER TABLE {quoted_table} ADD COLUMN {col_name} {col_type}"))
                    db.session.commit()
            except Exception as ex:
                logger.error(f"MIGRATION FAILED for {table_name}.{col_name}: {ex}")
                db.session.rollback()

        # 1. User Table Hardening
        user_updates = {
            'registration_state': 'VARCHAR(30)',
            'otp_email_status': 'VARCHAR(20)',
            'is_suspended': 'BOOLEAN',
            'suspension_reason': 'TEXT',
            'is_email_verified': 'BOOLEAN',
            'points': 'INTEGER',
            'must_change_password': 'BOOLEAN',
            'setup_token': 'VARCHAR(100)',
            'setup_token_expiration': 'TIMESTAMP',
            'is_superadmin': 'BOOLEAN',
            'verification_code': 'VARCHAR(6)',
            'verification_code_expires': 'TIMESTAMP',
            'verification_attempts': 'INTEGER',
            'last_login_reward_date': 'DATE',
            'resend_cooldown': 'TIMESTAMP',
            'reset_token': 'VARCHAR(100)',
            'reset_token_expiration': 'TIMESTAMP'
        }
        if 'user' in tables:
            for col, col_type in user_updates.items():
                safe_add_column('user', col, col_type)

        # 2. Founder/Developer Table Hardening
        if 'founder' in tables:
            for col in ['bio', 'vision', 'mission', 'leadership_statement']:
                safe_add_column('founder', col, 'TEXT')
        if 'developer' in tables:
            safe_add_column('developer', 'bio', 'TEXT')

        # 3. Association/Metadata Columns
        if 'assignment' in tables: safe_add_column('assignment', 'points', 'INTEGER DEFAULT 100')
        if 'meeting' in tables: safe_add_column('meeting', 'course_id', 'INTEGER')
        if 'announcement' in tables: safe_add_column('announcement', 'course_id', 'INTEGER')
        
        # 4. Verify Critical Tables Exist (Double Check)
        for t in ['notification', 'system_report', 'homepage_section', 'global_alert', 'activity']:
            if t not in tables:
                logger.warning(f"MIGRATION: Table '{t}' missing after create_all. Attempting manual creation...")
                try:
                    # This is a fallback if create_all failed for some reason
                    db.create_all()
                    db.session.commit()
                except Exception as e:
                    logger.error(f"Manual table creation failed: {e}")

        from seed_sa_module import seed_sa_func
        seed_sa_func()
    except Exception as e:
        logger.critical(f"STARTUP RECOVERY FAILED: {e}")

mail.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# --- Role Configuration ---
ROLE_CHOICES = ['SuperAdmin', 'Admin', 'Teacher', 'Student', 'Staff', 'Applicant']
SUPERADMIN_ASSIGNABLE_ROLES = ['Admin', 'Teacher', 'Student', 'Staff', 'Applicant']
ADMIN_ASSIGNABLE_ROLES = ['Teacher', 'Student', 'Staff', 'Applicant']
DEFAULT_APPROVAL_ROLE = 'Student'

# --- Security Decorators ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role not in ['Admin', 'SuperAdmin']:
            flash('Admin access required.', 'danger')
            return redirect(url_for('dashboard'))
        if getattr(current_user, 'is_suspended', False):
            flash('Your account is suspended. Contact administration.', 'danger')
            return redirect(url_for('logout'))
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

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.role != 'Teacher':
            flash('Teacher access required.', 'danger')
            return redirect(url_for('dashboard'))
        if getattr(current_user, 'is_suspended', False):
            flash('Your account is suspended. Contact administration.', 'danger')
            return redirect(url_for('logout'))
        return f(*args, **kwargs)
    return decorated_function

# --- Safe Database Initialization ---
_db_initialized = False

@app.before_request
def first_request_init():
    global _db_initialized
    if not _db_initialized:
        # We don't call create_all here anymore to avoid thundering herd.
        # It's called at module level or via migrations.
        _db_initialized = True
        logger.info("Application initialized.")


@app.route('/health')
def health_check():
    return jsonify({
        "status": "healthy", 
        "database": str(db.engine.url.drivername),
        "initialized": _db_initialized
    }), 200

# --- File Upload Config ---
# Prefer persistent media storage configured via MEDIA_ROOT, else use /data if present, else fallback to static uploads.
UPLOAD_BASE = os.environ.get('MEDIA_ROOT') or ('/data' if os.path.exists('/data') else os.path.join(app.root_path, 'static'))
app.config['UPLOAD_FOLDER'] = os.path.join(UPLOAD_BASE, 'uploads')
app.config['MEDIA_URL_PATH'] = os.environ.get('MEDIA_URL_PATH', '/media')
app.config['ALLOWED_RESOURCE_EXTENSIONS'] = {'pdf', 'docx', 'pptx', 'xlsx', 'zip', 'png', 'jpg', 'jpeg', 'mp4', 'mp3', 'txt'}

# Supabase storage integration (optional, enables persistent object storage across deploys)
app.config['SUPABASE_URL'] = os.environ.get('SUPABASE_URL')
app.config['SUPABASE_KEY'] = (
    os.environ.get('SUPABASE_SERVICE_ROLE_KEY') or
    os.environ.get('SUPABASE_SERVICE_KEY') or
    os.environ.get('SUPABASE_KEY') or
    os.environ.get('SUPABASE_ANON_KEY')
)
app.config['SUPABASE_BUCKET'] = os.environ.get('SUPABASE_BUCKET', 'ianstechlib')
app.config['SUPABASE_STORAGE_PUBLIC'] = os.environ.get('SUPABASE_STORAGE_PUBLIC', 'true').lower() in ('1', 'true', 'yes')
app.config['SUPABASE_STORAGE_ENABLED'] = bool(app.config['SUPABASE_URL'] and app.config['SUPABASE_KEY'])
try:
    if app.config['SUPABASE_URL'] and app.config['SUPABASE_KEY']:
        # Auto-clean whitespace to prevent initialization errors
        clean_url = app.config['SUPABASE_URL'].strip()
        clean_key = app.config['SUPABASE_KEY'].strip()
        app.config['SUPABASE_CLIENT'] = create_client(clean_url, clean_key)
    else:
        app.config['SUPABASE_CLIENT'] = None
except Exception as e:
    logger.error(f"Failed to initialize Supabase client: {e}")
    app.config['SUPABASE_STORAGE_ENABLED'] = False
    app.config['SUPABASE_CLIENT'] = None

logger.info(f"SUPABASE_STORAGE_ENABLED={app.config['SUPABASE_STORAGE_ENABLED']}, bucket={app.config['SUPABASE_BUCKET']}, public={app.config['SUPABASE_STORAGE_PUBLIC']}")

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'profiles'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'activities'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'resources'), exist_ok=True)
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'branding'), exist_ok=True)


# --- Media helpers ---
def static_file_exists(path):
    static_path = os.path.join(app.static_folder, path.lstrip('/'))
    return os.path.exists(static_path)


def get_media_url(path, fallback=None):
    if not path:
        if fallback:
            if fallback.lower().startswith('http'):
                return fallback
            return url_for('static', filename=fallback) if static_file_exists(fallback) else url_for('static', filename='img/placeholder.png')
        return url_for('static', filename='img/placeholder.png')

    if isinstance(path, str) and path.startswith(('http://', 'https://')):
        return path

    if path.startswith('uploads/') or path.startswith('resources/') or path.startswith('profiles/') or path.startswith('activities/') or path.startswith('branding/'):
        storage_path = path[len('uploads/'):] if path.startswith('uploads/') else path
        
        # 1. Try Cloud
        if app.config['SUPABASE_STORAGE_ENABLED']:
            try:
                if app.config['SUPABASE_STORAGE_PUBLIC']:
                    return f"{app.config['SUPABASE_URL']}/storage/v1/object/public/{app.config['SUPABASE_BUCKET']}/{storage_path}"
                response = app.config['SUPABASE_CLIENT'].storage.from_(app.config['SUPABASE_BUCKET']).create_signed_url(storage_path, 3600)
                if response and response.get('signedURL'):
                    return response.get('signedURL')
            except Exception as e:
                logger.warning(f"Supabase media URL generation failed: {e}")

        # 2. Try Local (Verified)
        local_path = os.path.join(app.config['UPLOAD_FOLDER'], storage_path)
        if os.path.exists(local_path):
            return url_for('media_file', filepath=path)
        
        # 3. Fallback to placeholder if file is missing (Railway wiped local storage)
        if fallback:
            return url_for('static', filename=fallback) if static_file_exists(fallback) else url_for('static', filename='img/placeholder.png')
        return url_for('static', filename='img/placeholder.png')

    if path.startswith('/'):
        return url_for('static', filename=path.lstrip('/'))

    if any(path.startswith(prefix) for prefix in ('img/', 'css/', 'js/', 'fonts/')):
        return url_for('static', filename=path)

    return url_for('static', filename=path)


def find_brand_media_path(prefix):
    branding_folder = os.path.join(app.config['UPLOAD_FOLDER'], 'branding')
    if os.path.isdir(branding_folder):
        candidates = sorted(os.listdir(branding_folder), reverse=True)
        for filename in candidates:
            if filename.startswith(prefix):
                return f"uploads/branding/{filename}"

    if app.config['SUPABASE_STORAGE_ENABLED']:
        try:
            # Consistent with lib/storage folder structure
            listing = app.config['SUPABASE_CLIENT'].storage.from_(app.config['SUPABASE_BUCKET']).list('branding')
            if isinstance(listing, list):
                for item in sorted(listing, key=lambda x: x.get('name', ''), reverse=True):
                    name = item.get('name') if isinstance(item, dict) else None
                    if name and name.startswith(prefix):
                        return f"uploads/branding/{name}"
        except Exception as e:
            logger.warning(f"Could not list Supabase branding objects: {e}")

    return None

@app.route('/api/upload', methods=['POST'])
@login_required
def api_upload():
    """
    Unified API endpoint for uploading media.
    Follows the pattern suggested by the user.
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    try:
        # Use our hardened save_media_file which now uses cloud-native storage
        public_url = save_media_file(file, 'uploads')
        return jsonify({"url": public_url, "success": True})
    except Exception as e:
        logger.error(f"API Upload Failure: {e}")
        return jsonify({"error": str(e), "success": False}), 500


def save_media_file(uploaded_file, folder, prefix=None, filename=None):
    if not uploaded_file or not uploaded_file.filename:
        return None

    ext = uploaded_file.filename.rsplit('.', 1)[1].lower() if '.' in uploaded_file.filename else 'jpg'
    if filename:
        safe_name = secure_filename(filename)
    else:
        safe_name = secure_filename(f"{prefix or uuid.uuid4().hex[:10]}_{uuid.uuid4().hex[:10]}.{ext}")
    storage_path = f"{folder}/{safe_name}".lstrip('/')

    # 1. Save a local fallback copy always (for immediate access/debugging)
    local_folder = os.path.join(app.config['UPLOAD_FOLDER'], folder)
    os.makedirs(local_folder, exist_ok=True)
    local_path = os.path.join(local_folder, safe_name)
    uploaded_file.seek(0)
    uploaded_file.save(local_path)

    # 2. Cloud Upload via Library (Returns permanent public URL)
    try:
        uploaded_file.seek(0)
        file_bytes = uploaded_file.read()
        public_url = upload_to_bucket(
            file_bytes=file_bytes,
            filename=safe_name,
            content_type=uploaded_file.content_type,
            folder=folder
        )
        if public_url:
            logger.info(f"Cloud upload success: {public_url}")
            return public_url
    except Exception as e:
        logger.error(f"Cloud upload integration failed: {e}")

    # Fallback to local path if cloud upload fails
    return f"uploads/{storage_path}"


@app.route('/media/<path:filepath>')
def media_file(filepath):
    filepath = filepath.lstrip('/')
    if filepath.startswith('uploads/'):
        filepath = filepath[len('uploads/'):]

    safe_root = os.path.abspath(app.config['UPLOAD_FOLDER'])
    full_path = os.path.abspath(os.path.join(safe_root, filepath))

    if not full_path.startswith(safe_root):
        abort(404)
    if os.path.exists(full_path):
        return send_file(full_path)

    if app.config['SUPABASE_STORAGE_ENABLED']:
        storage_path = filepath.replace('\\', '/')
        try:
            signed = app.config['SUPABASE_CLIENT'].storage.from_(app.config['SUPABASE_BUCKET']).create_signed_url(storage_path, 3600)
            if signed and signed.get('signedURL'):
                return redirect(signed['signedURL'])
        except Exception as e:
            logger.warning(f"Supabase media file redirect failed: {e}")

    abort(404)


@app.template_global()
def media_url(path, fallback=None):
    return get_media_url(path, fallback)


def sync_local_media_to_supabase():
    if not app.config['SUPABASE_STORAGE_ENABLED']:
        return

    bucket = app.config['SUPABASE_BUCKET']
    storage_client = app.config['SUPABASE_CLIENT']
    for root, _, files in os.walk(app.config['UPLOAD_FOLDER']):
        for filename in files:
            local_file = os.path.join(root, filename)
            relpath = os.path.relpath(local_file, app.config['UPLOAD_FOLDER']).replace('\\', '/')
            try:
                with open(local_file, 'rb') as f:
                    data = f.read()
                storage_client.storage.from_(bucket).upload(relpath, data)
            except Exception as e:
                logger.warning(f"Could not sync local media to Supabase for {relpath}: {e}")


def ensure_media_storage():
    if app.config['SUPABASE_STORAGE_ENABLED']:
        sync_local_media_to_supabase()


if hasattr(app, 'before_serving'):
    @app.before_serving
    def _ensure_media_storage():
        ensure_media_storage()
elif hasattr(app, 'before_first_request'):
    @app.before_first_request
    def _ensure_media_storage():
        ensure_media_storage()
else:
    ensure_media_storage()

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.context_processor
def inject_now():
    context = {
        'datetime': datetime,
        'notifications': [],
        'global_alerts': [],
        'brand_logo_path': find_brand_media_path('logo') or 'img/logo.png',
        'brand_hero_path': find_brand_media_path('hero') or 'img/placeholder.png'
    }
    try:
        if current_user.is_authenticated:
            # Safer query for notifications to prevent crashes if table is missing or partially migrated
            try:
                unread_notifications = Notification.query.filter_by(
                    user_id=current_user.id, is_read=False
                ).order_by(Notification.created_at.desc()).limit(10).all()
                context['notifications'] = unread_notifications
            except Exception as e:
                logger.error(f"Notification context error: {e}")
                
        try:
            active_alerts = GlobalAlert.query.filter_by(is_active=True).order_by(
                GlobalAlert.created_at.desc()
            ).all()
            context['global_alerts'] = active_alerts
        except Exception as e:
            logger.error(f"GlobalAlert context error: {e}")
            
    except Exception as e:
        logger.error(f"Context processor error: {e}")
        
    context['build_external_url'] = build_external_url
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

# --- Auth State Guard ---
def check_auth_state(user, current_step):
    """
    Intelligently redirects user based on their current onboarding state.
    """
    if not user: return None
    
    if user.is_email_verified and current_step == 'verify':
        return redirect(url_for('login'))
    
    if user.registration_state == 'approved' and current_step in ['verify', 'pending']:
        return redirect(url_for('login'))
        
    return None

# --- Routes ---
@app.route('/')
def index():
    try:
        # 1. Branding Paths
        brand_logo_path = find_brand_media_path('logo')
        brand_hero_path = find_brand_media_path('hero')

        # 2. Hardened Queries
        def safe_query(query_func, default_val=[]):
            try:
                return query_func()
            except Exception as ex:
                logger.warning(f"Index: Query failed: {ex}")
                return default_val

        # Only show OVERALL institutional announcements
        announcements = safe_query(lambda: Announcement.query.filter_by(course_id=None).order_by(Announcement.date.desc()).limit(3).all())
        activities = safe_query(lambda: Activity.query.order_by(Activity.date.desc()).limit(6).all())
        founders = safe_query(lambda: Founder.query.all())
        developers = safe_query(lambda: Developer.query.all())
        home_sections = safe_query(lambda: HomePageSection.query.filter_by(is_active=True).order_by(HomePageSection.display_order.asc()).all())
        
        # Individual records for highlighting
        founder = safe_query(lambda: Founder.query.first(), None)
        dev = safe_query(lambda: Developer.query.first(), None)

        return render_template('index.html', 
                             announcements=announcements, 
                             activities=activities,
                             brand_logo_path=brand_logo_path,
                             brand_hero_path=brand_hero_path,
                             founders=founders,
                             developers=developers,
                             home_sections=home_sections,
                             founder=founder,
                             dev=dev)
    except Exception as e:
        logger.error(f"Index route critical failure: {e}")
        return render_template('errors/500.html', error=e), 500

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            email = request.form.get('email', '').strip().lower() # Normalize for case-insensitive search
            password = request.form.get('password')
            
            # Search by any of the identification fields
            user = User.query.filter(
                (db.func.lower(User.email) == email) | 
                (db.func.lower(User.student_id) == email) | 
                (db.func.lower(User.school_email) == email)
            ).first()
            
            if user:
                if getattr(user, 'is_suspended', False):
                    reason = getattr(user, 'suspension_reason', 'Violation of platform policies.')
                    flash(f'Your account has been suspended. Reason: {reason}', 'danger')
                    return redirect(url_for('login'))
                
                # Check if approved but password not set yet
                if user.registration_state == 'approved' and getattr(user, 'must_change_password', False):
                    flash('Your account is approved. Please check your email for the account activation link to set your password.', 'info')
                    return redirect(url_for('login'))
                
            if user and user.password and check_password_hash(user.password, password):
                # 1. SuperAdmin bypass
                if user.role == 'SuperAdmin' or getattr(user, 'is_superadmin', False):
                    login_user(user)
                    flash('SuperAdmin access granted.', 'success')
                    return redirect(url_for('dashboard'))
                    
                # 2. Verification Check
                if not getattr(user, 'is_email_verified', False):
                    flash('Please verify your personal email address first.', 'warning')
                    return redirect(url_for('verify_email', user_id=user.id))
                    
                # 3. Registration State Check (Only for students/applicants)
                # Admins, Teachers, and Staff should be able to log in if they have credentials
                if user.role in ['Student', 'Applicant']:
                    if user.registration_state != 'approved':
                        flash('Your student account is pending final approval by the administrator.', 'warning')
                        return redirect(url_for('login'))
                
                login_user(user)
                log_audit('Successful Login')
                return redirect(url_for('dashboard'))
                
            # Incorrect password or user not found - log it safely
            try:
                if user:
                    ip = request.remote_addr
                    db.session.add(SystemAuditLog(user_id=user.id, action='Failed Login Attempt', ip_address=ip))
                    db.session.commit()
            except Exception:
                db.session.rollback()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Critical login error: {e}")
            
        flash('Invalid credentials. Please try again.', 'danger')
        return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        logger.info("[REG] --- NEW REGISTRATION REQUEST RECEIVED ---")
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        dept = request.form.get('department')
        photo = request.files.get('profile_photo')
        
        # 1. Basic Validation & Normalization
        name = name.strip() if name else ""
        email = email.strip().lower() if email else ""
        logger.info(f"[REG] Processing registration for: {email}")
        
        if not name or not email:
            logger.warning("[REG] Missing name or email, redirecting back.")
            flash('Full Name and Email Address are required.', 'danger')
            return redirect(url_for('register'))

        # 2. Check for existing user (case-insensitive)
        existing_user = User.query.filter(db.func.lower(User.email) == email).first()
        
        if existing_user:
            # Block only fully active, approved, and verified accounts
            if existing_user.is_email_verified and existing_user.registration_state == 'approved':
                logger.info(f"[REG] User {email} already active, redirecting to login.")
                flash('This email is already registered and active. Please login.', 'info')
                return redirect(url_for('login'))
            
            # If application is in progress, reuse the record
            user_to_save = existing_user
            logger.info(f"[REG] Re-using existing onboarding record for {email} (ID: {user_to_save.id})")
        else:
            # Create new user record with all required fields set immediately to avoid validation 500s
            user_to_save = User(
                email=email, 
                role='Applicant', 
                name=name,
                password=generate_password_hash(uuid.uuid4().hex)
            )
            db.session.add(user_to_save)
            logger.info(f"[REG] Creating new onboarding record for {email}")

        try:
            logger.info(f"[REG] Step 1: Handling File Upload for {email}")
            if photo and photo.filename:
                user_to_save.profile_photo = save_media_file(photo, 'profiles', prefix=email.split('@')[0])
                logger.info(f"[REG] Photo saved to: {user_to_save.profile_photo}")

            logger.info(f"[REG] Step 2: Preparing User Record for {email}")
            otp = f"{random.randint(100000, 999999)}"
            user_to_save.name = name
            user_to_save.phone = phone
            user_to_save.department = dept
            user_to_save.registration_state = 'pending_verification'
            user_to_save.role = user_to_save.role or 'Applicant'
            user_to_save.status = 'Pending'
            user_to_save.is_email_verified = False
            user_to_save.verification_code = otp
            user_to_save.verification_code_expires = datetime.utcnow() + timedelta(minutes=15)
            user_to_save.verification_attempts = 0
            
            if hasattr(user_to_save, 'otp_email_status'):
                user_to_save.otp_email_status = 'pending'
            
            logger.info(f"[REG] Step 3: Committing to Database for {email}...")
            db.session.commit()
            logger.info(f"[REG] Step 4: DB commit SUCCESS for {email}. ID: {getattr(user_to_save, 'id', 'NEW')}")
            
        except Exception as e:
            db.session.rollback()
            err_msg = f"[REG] STEP FAILURE for {email}: {str(e)}"
            logger.error(err_msg, exc_info=True)
            flash(f'Registration error: {str(e)}', 'danger')
            return redirect(url_for('register'))

        # SAFE_MODE: skip email logic if env var is set
        is_safe_mode = os.environ.get('IAMSTECH_REG_SAFE_MODE', '').lower() == 'true'
        if is_safe_mode:
            logger.info(f"[REG] SAFE_MODE detected. Skipping email dispatch for {email}")
            logger.info(f"[REG] SAFE_MODE OTP for {email} is: {otp}")
            flash('Registration successful! Redirecting to verification (SAFE MODE)', 'success')
            redirect_url = url_for('verify_email', user_id=user_to_save.id, _external=True)
            logger.info(f"[REG] SAFE_MODE Redirecting to: {redirect_url}")
            return redirect(redirect_url)

        # 5. Send OTP (async, NON-BLOCKING)
        try:
            logger.info(f"[REG] Dispatching OTP email for {email}")
            send_verification_otp(user_to_save, otp)
        except Exception as e:
            logger.error(f"[REG] Async email dispatch failed: {str(e)}")

        flash('Registration successful! Please check your email.', 'success')
        # Generate the absolute URL to avoid proxy issues
        redirect_url = url_for('verify_email', user_id=user_to_save.id, _external=True)
        logger.info(f"[REG] SUCCESS: Redirecting {email} (ID: {user_to_save.id}) to {redirect_url}")
        return redirect(redirect_url)

    return render_template('register.html')

@app.route('/debug_errors')
def debug_errors():
    try:
        with open('scratch/registration_errors.txt', 'r') as f:
            return f.read(), 200, {'Content-Type': 'text/plain'}
    except:
        return "No errors logged yet."



@app.route('/verify-email/<int:user_id>', methods=['GET', 'POST'])
@app.route('/verify-email/<int:user_id>/', methods=['GET', 'POST'])
def verify_email(user_id):
    logger.info(f"[VERIFY] Incoming request for ID: {user_id} (Path: {request.path})")
    
    # Robust lookup: try session.get first, then fallback to query
    user = db.session.get(User, user_id)
    if not user:
        user = User.query.filter_by(id=user_id).first()
    
    if not user:
        # DEEP DIAGNOSTICS
        total_users = User.query.count()
        db_type = "PostgreSQL" if "postgresql" in app.config['SQLALCHEMY_DATABASE_URI'].lower() else "SQLite"
        return render_template('errors/404.html', 
                             message=f"Verification record (ID: {user_id}) not found. DB Type: {db_type}"), 404

    # State Guard
    state_redirect = check_auth_state(user, 'verify')
    if state_redirect: return state_redirect

    if user.is_email_verified:
        logger.info(f"[VERIFY] User {user.email} already verified, redirecting to login.")
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        try:
            logger.info(f"[VERIFY] Processing OTP submission for {user.email}")
            code = request.form.get('otp')
            
            if (user.verification_attempts or 0) >= 5:
                flash('Too many failed attempts. Please request a new code.', 'danger')
                return redirect(url_for('verify_email', user_id=user.id))
                
            if datetime.utcnow() > (user.verification_code_expires or datetime.min):
                flash('Verification code expired. Please request a new one.', 'danger')
                return redirect(url_for('verify_email', user_id=user.id))
                
            if code == user.verification_code:
                user.is_email_verified = True
                user.registration_state = 'verified_awaiting_approval'
                user.verification_code = None
                db.session.commit()
                return render_template('verification_success.html', name=user.name)
            else:
                user.verification_attempts = (user.verification_attempts or 0) + 1
                db.session.commit()
                flash('Invalid verification code. Please try again.', 'danger')
        except Exception as e:
            db.session.rollback()
            logger.error(f"Verification POST error: {e}")
            flash('A technical error occurred. Please try again.', 'warning')
    if app.config['DEV_MODE']:
        flash(f'DEV MODE - Your OTP is: {user.verification_code}', 'warning')
        
    if getattr(user, 'otp_email_status', None) == 'failed':
        flash('We are currently unable to deliver the verification email. Please contact our Technical Support Team on WhatsApp for immediate assistance with your account verification.', 'danger')

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
    if hasattr(user, 'otp_email_status'):
        user.otp_email_status = 'pending'
    db.session.commit()
    
    send_verification_otp(user, otp)
    flash('A new verification code delivery attempt has started.', 'info')
        
    return redirect(url_for('verify_email', user_id=user.id))



@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        try:
            email = request.form.get('email')
            user = User.query.filter_by(email=email).first()
            if user:
                user.reset_token = f"{random.randint(100000, 999999)}"
                user.reset_token_expiration = datetime.utcnow() + timedelta(minutes=15)
                db.session.commit()
                send_reset_email(user)
                log_audit('Password Reset OTP Requested', target_id=user.id, target_type='User')
        except Exception as e:
            db.session.rollback()
            logger.error(f"Forgot password error: {e}")
            
        # Always show the same message to prevent email enumeration
        flash('If that email exists in our system, a password reset OTP has been sent.', 'info')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        email = request.form.get('email')
        otp = request.form.get('otp')
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')
        
        user = User.query.filter_by(email=email).first()
        if user and user.reset_token == otp and user.reset_token_expiration > datetime.utcnow():
            if password != confirm or len(password) < 8:
                flash('Passwords do not match or are too short.', 'danger')
                return redirect(url_for('reset_password'))
            
            user.password = generate_password_hash(password)
            user.reset_token = None
            user.reset_token_expiration = None
            user.must_change_password = False
            db.session.commit()
            
            # Log it
            try:
                ip = request.remote_addr
                db.session.add(SystemAuditLog(user_id=user.id, action='Password Successfully Reset', ip_address=ip))
                db.session.commit()
            except Exception:
                db.session.rollback()
            
            flash('Password reset successful. You can now log in.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Invalid email or OTP.', 'danger')
    return render_template('reset_password.html')

@app.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        password = request.form.get('password')
        confirm = request.form.get('confirm_password')

        if password != confirm:
            flash('Passwords do not match.', 'danger')
            return redirect(url_for('change_password'))
        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'danger')
            return redirect(url_for('change_password'))

        current_user.password = generate_password_hash(password)
        current_user.must_change_password = False
        db.session.commit()

        flash('Your password has been updated successfully.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('change_password.html')

@app.route('/dashboard')
@login_required
def dashboard():
    # Force password change if required
    if getattr(current_user, 'must_change_password', False) and not current_user.setup_token:
        return redirect(url_for('change_password'))

    if current_user.role == 'SuperAdmin':
        try:
            # Main Queries - Wrapped individually for maximum resilience
            def safe_query(query_func, default_val=[]):
                try:
                    return query_func()
                except Exception as ex:
                    logger.warning(f"SuperAdmin Dashboard: Query failed: {ex}")
                    return default_val

            users = safe_query(lambda: User.query.all())
            admins = safe_query(lambda: User.query.filter_by(role='Admin').all())
            applicants = safe_query(lambda: User.query.filter_by(registration_state='verified_awaiting_approval').all())
            unverified_applicants = safe_query(lambda: User.query.filter_by(registration_state='pending_verification').all())
            
            otp_requests = safe_query(lambda: User.query.filter(
                User.reset_token.isnot(None), 
                User.reset_token_expiration > datetime.utcnow(), 
                db.func.length(User.reset_token) == 6
            ).all())
            
            audit_logs = safe_query(lambda: SystemAuditLog.query.order_by(SystemAuditLog.timestamp.desc()).limit(50).all())
            notifications = safe_query(lambda: Notification.query.order_by(Notification.created_at.desc()).limit(20).all())
            founders = safe_query(lambda: Founder.query.all())
            developers = safe_query(lambda: Developer.query.all())
            activities = safe_query(lambda: Activity.query.order_by(Activity.id.desc()).all())
            announcements = safe_query(lambda: Announcement.query.order_by(Announcement.date.desc()).all())
            system_reports = safe_query(lambda: SystemReport.query.filter_by(status='open').order_by(SystemReport.created_at.desc()).limit(10).all())
            home_sections = safe_query(lambda: HomePageSection.query.order_by(HomePageSection.display_order.asc()).all())

            return render_template('dashboards/superadmin.html', 
                                 users=users, 
                                 admins=admins,
                                 applicants=applicants,
                                 unverified_applicants=unverified_applicants,
                                 otp_requests=otp_requests,
                                 audit_logs=audit_logs,
                                 notifications=notifications,
                                 system_reports=system_reports,
                                 founders=founders,
                                 developers=developers,
                                 activities=activities,
                                 announcements=announcements,
                                 home_sections=home_sections,
                                 cloud_storage_enabled=app.config['SUPABASE_STORAGE_ENABLED'])
        except Exception as e:
            logger.error(f"SuperAdmin dashboard critical error: {e}", exc_info=True)
            flash(f'Dashboard loading error: {str(e)}', 'danger')
            return render_template('errors/500.html', error=str(e)), 500
    elif current_user.role == 'Admin':
        def safe_query(query_func, default_val=[]):
            try:
                return query_func()
            except Exception as ex:
                logger.warning(f"Admin Dashboard: Query failed: {ex}")
                return default_val

        users = safe_query(lambda: User.query.filter(User.role != 'SuperAdmin').all())
        applicants = safe_query(lambda: User.query.filter(User.registration_state.in_(['pending_verification', 'verified_awaiting_approval'])).all())
        teachers = safe_query(lambda: User.query.filter_by(role='Teacher').all())
        courses = safe_query(lambda: Course.query.all())
        announcements = safe_query(lambda: Announcement.query.all())
        activities = safe_query(lambda: Activity.query.order_by(Activity.id.desc()).all())
        home_sections = safe_query(lambda: HomePageSection.query.order_by(HomePageSection.display_order.asc()).all())
        
        return render_template('dashboards/admin_new.html', 
                             users=users, 
                             applicants=applicants, 
                             teachers=teachers, 
                             courses=courses, 
                             announcements=announcements,
                             activities=activities,
                             home_sections=home_sections,
                             cloud_storage_enabled=app.config['SUPABASE_STORAGE_ENABLED'])
                             
    elif current_user.role == 'Teacher':
        def safe_query(query_func, default_val=[]):
            try:
                return query_func()
            except Exception as ex:
                logger.warning(f"Teacher Dashboard: Query failed: {ex}")
                return default_val

        courses = safe_query(lambda: Course.query.filter_by(teacher_id=current_user.id).all())
        meetings = safe_query(lambda: Meeting.query.filter_by(teacher_id=current_user.id).order_by(Meeting.date.asc(), Meeting.time.asc()).all())
        total_students = sum(len(course.enrollments) for course in courses)
        course_announcements = safe_query(lambda: Announcement.query.filter_by(posted_by=current_user.id).order_by(Announcement.date.desc()).limit(20).all())
        course_resources = safe_query(lambda: LessonMaterial.query.filter_by(teacher_id=current_user.id).order_by(LessonMaterial.uploaded_at.desc()).all())
        attendance_records = safe_query(lambda: Attendance.query.join(Course, Attendance.course_id == Course.id).filter(Course.teacher_id == current_user.id).order_by(Attendance.date.desc()).limit(50).all())

        attendance_summary = []
        for course in courses:
            try:
                total = Attendance.query.filter_by(course_id=course.id).count()
                present = Attendance.query.filter_by(course_id=course.id, status='Present').count()
                attendance_summary.append({
                    'course': course,
                    'total': total,
                    'present': present,
                    'percent': round((present / total * 100), 1) if total else 0
                })
            except Exception as e:
                logger.warning(f"Teacher Dashboard: Attendance summary failed for course {course.id}: {e}")

        return render_template('dashboards/teacher_new.html', 
                               courses=courses,
                               meetings=meetings,
                               total_students=total_students,
                               attendance_records=attendance_records,
                               attendance_summary=attendance_summary,
                               course_resources=course_resources,
                               course_announcements=course_announcements)
        
    elif current_user.role in ['Student', 'Staff']:
        # Gamification: Daily Login Reward (Hardened)
        try:
            today = datetime.utcnow().date()
            if getattr(current_user, 'last_login_reward_date', None) != today:
                current_user.points = (current_user.points or 0) + 10
                current_user.last_login_reward_date = today
                db.session.commit()
                flash('🎉 +10 XP for logging in today! Keep up the great work.', 'success')
        except Exception as e:
            db.session.rollback()
            logger.warning(f"Gamification update failed: {e}")
            
        def safe_query(query_func, default_val=[]):
            try:
                return query_func()
            except Exception as ex:
                logger.warning(f"Student Dashboard: Query failed: {ex}")
                return default_val

        enrollments = safe_query(lambda: Enrollment.query.filter_by(student_id=current_user.id).all())
        courses = safe_query(lambda: Course.query.all())

        # Attendance calculation
        try:
            total_att = Attendance.query.filter_by(student_id=current_user.id).count()
            present_att = Attendance.query.filter_by(student_id=current_user.id, status='Present').count()
            att_percent = (present_att / total_att * 100) if total_att > 0 else 0
        except Exception as e:
            logger.warning(f"Attendance calculation failed: {e}")
            att_percent = 0

        # Assignments from enrolled courses
        enrolled_course_ids = [e.course_id for e in enrollments]
        assignments = safe_query(lambda: Assignment.query.filter(Assignment.course_id.in_(enrolled_course_ids)).all() if enrolled_course_ids else [])
        meetings = safe_query(lambda: Meeting.query.order_by(Meeting.date.desc()).all())

        # Announcements for portal: Overall + Enrolled Courses
        announcements = safe_query(lambda: Announcement.query.filter(
            (Announcement.course_id == None) | (Announcement.course_id.in_(enrolled_course_ids))
        ).order_by(Announcement.date.desc()).limit(10).all())

        # Leaderboard — Students ONLY
        top_students = safe_query(lambda: User.query.filter(
            User.role == 'Student',
            User.registration_state == 'approved',
            User.is_superadmin == False
        ).order_by(User.points.desc()).limit(10).all())

        # Rank calculation
        try:
            current_points = getattr(current_user, 'points', 0) or 0
            rank = User.query.filter(
                User.role == 'Student',
                User.registration_state == 'approved',
                User.is_superadmin == False,
                User.points > current_points
            ).count() + 1
        except Exception:
            rank = "N/A"

        return render_template('dashboards/student.html',
                               enrollments=enrollments,
                               courses=courses,
                               att_percent=att_percent,
                               assignments=assignments,
                               meetings=meetings,
                               top_students=top_students,
                               my_rank=rank,
                               announcements=announcements,
                               user_role=current_user.role)
    elif current_user.role == 'Applicant':
        announcements = Announcement.query.order_by(Announcement.date.desc()).limit(5).all()
        return render_template('dashboards/applicant.html', announcements=announcements)
    else:
        flash('Your role does not have a dashboard yet. Please contact administration.', 'warning')
        announcements = Announcement.query.order_by(Announcement.date.desc()).limit(5).all()
        return render_template('dashboards/applicant.html', announcements=announcements)

# --- Teacher Controls ---
@app.route('/teacher/post_assignment', methods=['POST'])
@login_required
@teacher_required
def post_assignment():
    title = request.form.get('title')
    content = request.form.get('content')
    due_date = request.form.get('due_date')
    course_id = request.form.get('course_id')
    points = request.form.get('points') or 100

    course = Course.query.filter_by(id=course_id, teacher_id=current_user.id).first()
    if not course:
        flash('Course selection invalid.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        assignment = Assignment(course_id=course.id, title=title, content=content, due_date=due_date, points=int(points))
        db.session.add(assignment)
        db.session.commit()
        flash('Assignment published successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Assignment creation failed: {e}')
        flash('Could not publish assignment at this time.', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/teacher/add_meeting', methods=['POST'])
@login_required
@teacher_required
def add_meeting():
    title = request.form.get('title')
    meet_link = request.form.get('link')
    date = request.form.get('date')
    time = request.form.get('time')
    course_id = request.form.get('course_id')

    course = Course.query.filter_by(id=course_id, teacher_id=current_user.id).first()
    if not course:
        flash('Invalid course selection for meeting.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        meeting = Meeting(teacher_id=current_user.id, course_id=course.id, title=title, meet_link=meet_link, date=date, time=time)
        db.session.add(meeting)
        db.session.commit()
        flash('Live session scheduled successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Meeting creation failed: {e}')
        flash('Could not schedule meeting at this time.', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/teacher/mark_attendance', methods=['POST'])
@login_required
@teacher_required
def mark_attendance():
    course_id = request.form.get('course_id')
    date_str = request.form.get('attendance_date') or datetime.utcnow().date().isoformat()
    attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()

    course = Course.query.filter_by(id=course_id, teacher_id=current_user.id).first()
    if not course:
        flash('Invalid attendance submission.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        for enrollment in course.enrollments:
            status = request.form.get(f'status_{enrollment.student_id}', 'Absent')
            record = Attendance.query.filter_by(student_id=enrollment.student_id, course_id=course.id, date=attendance_date).first()
            if record:
                record.status = status
            else:
                record = Attendance(student_id=enrollment.student_id, course_id=course.id, date=attendance_date, status=status)
                db.session.add(record)
        db.session.commit()
        flash('Attendance saved successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Attendance save failed: {e}')
        flash('Could not save attendance.', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/teacher/upload_material', methods=['POST'])
@login_required
@teacher_required
def upload_material():
    course_id = request.form.get('course_id')
    title = request.form.get('title')
    description = request.form.get('description')
    file = request.files.get('resource_file')

    course = Course.query.filter_by(id=course_id, teacher_id=current_user.id).first()
    if not course or not file or not allowed_resource_file(file.filename):
        flash('Invalid resource upload. Please choose a valid course file.', 'danger')
        return redirect(url_for('dashboard'))

    saved_path = save_media_file(file, 'resources')

    try:
        material = LessonMaterial(course_id=course.id, teacher_id=current_user.id, title=title, description=description, file_name=file.filename, file_path=saved_path.replace('uploads/', '') if saved_path else None)
        db.session.add(material)
        db.session.commit()
        flash('Lesson material uploaded successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Material upload failed: {e}')
        flash('Could not upload material.', 'danger')
    return redirect(url_for('dashboard'))

    return redirect(url_for('dashboard'))

@app.route('/teacher/post_announcement', methods=['POST'])
@login_required
@teacher_required
def post_announcement():
    title = request.form.get('title')
    content = request.form.get('content')
    course_id = request.form.get('course_id')

    course = Course.query.filter_by(id=course_id, teacher_id=current_user.id).first()
    if not course:
        flash('Invalid course selection for announcement.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        announcement = Announcement(title=title, content=content, posted_by=current_user.id, course_id=course.id)
        db.session.add(announcement)
        db.session.commit()
        flash('Course announcement posted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Announcement creation failed: {e}')
        flash('Could not post announcement.', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/admin/post_announcement', methods=['POST'])
@login_required
@admin_required
def admin_post_announcement():
    title = request.form.get('title')
    content = request.form.get('content')
    is_overall = request.form.get('is_overall') == 'true'

    try:
        # Admin can post overall (course_id=None)
        announcement = Announcement(
            title=title, 
            content=content, 
            posted_by=current_user.id, 
            course_id=None
        )
        db.session.add(announcement)
        db.session.commit()
        flash('Overall institutional announcement posted successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Admin Announcement creation failed: {e}')
        flash('Could not post institutional announcement.', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/admin/delete_announcement/<int:ann_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_announcement(ann_id):
    ann = Announcement.query.get_or_404(ann_id)
    try:
        db.session.delete(ann)
        db.session.commit()
        flash('Announcement deleted.', 'info')
    except Exception as e:
        db.session.rollback()
        flash('Error deleting announcement.', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/teacher/download_resource/<int:resource_id>')
@login_required
@teacher_required
def download_resource(resource_id):
    material = LessonMaterial.query.get_or_404(resource_id)
    if material.teacher_id != current_user.id:
        flash('Resource access denied.', 'danger')
        return redirect(url_for('dashboard'))

    local_path = os.path.join(app.config['UPLOAD_FOLDER'], material.file_path)
    if os.path.exists(local_path):
        return send_file(local_path, as_attachment=True, download_name=material.file_name)

    if app.config['SUPABASE_STORAGE_ENABLED']:
        try:
            signed = app.config['SUPABASE_CLIENT'].storage.from_(app.config['SUPABASE_BUCKET']).create_signed_url(material.file_path, 3600)
            if signed and signed.get('signedURL'):
                return redirect(signed['signedURL'])
        except Exception as e:
            logger.error(f'Lesson material download failed via Supabase: {e}')

    flash('Resource file is unavailable.', 'danger')
    return redirect(url_for('dashboard'))

# --- Admin Controls ---
@app.route('/admin/update-branding', methods=['POST'])
@login_required
@admin_required
def admin_update_branding():
    b_type = request.form.get('type')
    photo = request.files.get('image')
    
    if not photo:
        flash('No image selected.', 'warning')
        return redirect(url_for('dashboard'))

    try:
        if b_type == 'logo':
            saved_path = save_media_file(photo, 'branding', prefix='logo')
            if saved_path:
                flash('Institutional Logo updated successfully!', 'success')
            else:
                flash('Logo uploaded, but storage failed.', 'warning')
        elif b_type == 'hero':
            hero_path = save_media_file(photo, 'branding', prefix='hero')
            if hero_path:
                flash('Homepage Hero updated successfully!', 'success')
            else:
                flash('Hero image uploaded, but storage failed.', 'warning')
        elif b_type == 'founder':
            saved_path = save_media_file(photo, 'branding', prefix='founder')
            founder = Founder.query.first() or Founder()
            founder.image_path = saved_path
            db.session.add(founder)
            db.session.commit()
            flash('Founder photo updated successfully!', 'success')
        elif b_type == 'developer':
            saved_path = save_media_file(photo, 'branding', prefix='developer')
            dev = Developer.query.first() or Developer()
            dev.image_path = saved_path
            db.session.add(dev)
            db.session.commit()
            flash('Developer spotlight photo updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Branding update DB error: {e}")
        flash('Image saved but database record could not be updated due to schema sync. Our team is fixing it!', 'warning')
        
    return redirect(url_for('dashboard'))

@app.route('/admin/update-founder', methods=['POST'])
@login_required
@admin_required
def admin_update_founder():
    name = request.form.get('name')
    title = request.form.get('title')
    message = request.form.get('message')
    photo = request.files.get('image')
    
    try:
        founder = Founder.query.first() or Founder()
        if name: founder.name = name
        if title: founder.title = title
        if message: founder.message = message
        
        if photo:
            founder.image_path = save_media_file(photo, 'branding', prefix='founder')
            
        db.session.add(founder)
        db.session.commit()
        flash('Founder information updated!', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Founder update error: {e}")
        flash('Could not update founder info in database. Please check back shortly.', 'danger')
        
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
    if name: dev.name = name
    if role: dev.role = role
    if desc: dev.description = desc
    
    if photo:
        dev.image_path = save_media_file(photo, 'branding', prefix='developer')
        
    db.session.add(dev)
    db.session.commit()
    flash('Developer information updated!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/admin/homepage-section', methods=['POST'])
@login_required
@admin_required
def admin_add_homepage_section():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    display_order = request.form.get('display_order', '').strip() or 0
    image = request.files.get('image')

    if not title or not description:
        flash('Section title and description are required.', 'warning')
        return redirect(url_for('dashboard'))

    section = HomePageSection(
        title=title,
        description=description,
        display_order=int(display_order),
        is_active=True
    )

    if image and image.filename:
        section.image_path = save_media_file(image, 'branding', prefix='section')

    try:
        db.session.add(section)
        db.session.commit()
        flash('Homepage section added successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Homepage section creation failed: {e}')
        flash('Could not add homepage section. Please try again.', 'danger')

    return redirect(url_for('dashboard'))

@app.route('/admin/homepage-section/delete/<int:section_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_homepage_section(section_id):
    section = HomePageSection.query.get_or_404(section_id)
    try:
        db.session.delete(section)
        db.session.commit()
        flash('Homepage section removed successfully.', 'info')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Homepage section deletion failed: {e}')
        flash('Could not delete the homepage section.', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/admin/homepage-section/update/<int:section_id>', methods=['POST'])
@login_required
@admin_required
def admin_update_homepage_section(section_id):
    section = HomePageSection.query.get_or_404(section_id)
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    display_order = request.form.get('display_order', '').strip() or 0
    is_active = request.form.get('is_active') == 'on'
    image = request.files.get('image')

    if not title or not description:
        flash('Section title and description are required.', 'warning')
        return redirect(url_for('dashboard'))

    section.title = title
    section.description = description
    section.display_order = int(display_order)
    section.is_active = is_active

    if image and image.filename:
        section.image_path = save_media_file(image, 'branding', prefix=f'section-{section.id}')

    try:
        db.session.commit()
        flash('Homepage section updated successfully.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f'Homepage section update failed: {e}')
        flash('Could not update the homepage section. Please try again.', 'danger')

    return redirect(url_for('dashboard'))

@app.route('/superadmin/download-documentation')
@login_required
@superadmin_required
def superadmin_download_documentation():
    """Generates an exhaustive, institutionally branded System Demo PDF."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer, Image, Table, TableStyle
    from reportlab.graphics.barcode import code128, qr
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics import renderPDF

    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    styles = getSampleStyleSheet()
    
    # Custom Styles
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=24, textColor=colors.HexColor('#0d1b3e'), alignment=1, spaceAfter=20)
    heading_style = ParagraphStyle('HeadingStyle', parent=styles['Heading2'], fontSize=16, textColor=colors.HexColor('#ff6f00'), spaceBefore=15, spaceAfter=10)
    body_style = ParagraphStyle('BodyStyle', parent=styles['Normal'], fontSize=11, leading=14, spaceAfter=10)

    def draw_header_footer(canvas_obj):
        # Header
        canvas_obj.setStrokeColor(colors.HexColor('#0d1b3e'))
        canvas_obj.setLineWidth(1)
        canvas_obj.line(0.5*inch, height-0.75*inch, width-0.5*inch, height-0.75*inch)
        
        logo_path = os.path.join(app.root_path, 'static', 'img', 'logo.png')
        if os.path.exists(logo_path):
            try:
                canvas_obj.drawImage(logo_path, 0.5*inch, height-0.65*inch, width=1.2*inch, preserveAspectRatio=True, mask='auto')
            except: pass
        
        canvas_obj.setFont("Helvetica-Bold", 10)
        canvas_obj.setFillColor(colors.HexColor('#0d1b3e'))
        canvas_obj.drawRightString(width-0.5*inch, height-0.5*inch, "IAMSTECH LIBERIA - Official System Documentation")
        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.drawRightString(width-0.5*inch, height-0.65*inch, f"Generated on: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")

        # Footer
        canvas_obj.line(0.5*inch, 0.75*inch, width-0.5*inch, 0.75*inch)
        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.setFillColor(colors.grey)
        canvas_obj.drawString(0.5*inch, 0.5*inch, "Confidential - Institutional Property of IAMSTECH")
        canvas_obj.drawRightString(width-0.5*inch, 0.5*inch, f"Page {canvas_obj.getPageNumber()}")

    def draw_watermark(canvas_obj):
        logo_path = os.path.join(app.root_path, 'static', 'img', 'logo.png')
        if os.path.exists(logo_path):
            try:
                canvas_obj.saveState()
                canvas_obj.setFillAlpha(0.05)
                canvas_obj.drawImage(logo_path, width/2 - 2*inch, height/2 - 2*inch, width=4*inch, preserveAspectRatio=True, mask='auto')
                canvas_obj.restoreState()
            except: pass

    def draw_barcode(canvas_obj, x, y, data):
        try:
            barcode = code128.Code128(data, barHeight=0.4*inch, barWidth=1.2)
            barcode.drawOn(canvas_obj, x, y)
        except:
            canvas_obj.drawString(x, y, f"[BARCODE: {data}]")
        canvas_obj.setFont("Helvetica", 6)
        canvas_obj.drawCentredString(x + 1*inch, y - 10, f"VERIFICATION ID: {data}")

    # --- PAGE 1: COVER ---
    draw_header_footer(p)
    draw_watermark(p)
    
    p.setFont("Helvetica-Bold", 32)
    p.setFillColor(colors.HexColor('#0d1b3e'))
    p.drawCentredString(width/2, height/2 + 1*inch, "IAMSTECH LIBERIA")
    
    p.setFont("Helvetica", 18)
    p.setFillColor(colors.HexColor('#ff6f00'))
    p.drawCentredString(width/2, height/2 + 0.5*inch, "School Management System")
    
    p.setFont("Helvetica-Bold", 14)
    p.setFillColor(colors.black)
    p.drawCentredString(width/2, height/2 - 0.5*inch, "ADMINISTRATION & SYSTEM DEMO GUIDE")
    
    p.setFont("Helvetica", 10)
    p.drawCentredString(width/2, height/2 - 1.5*inch, "Modernizing Education through Technology & Innovation")
    
    # Verification Barcode on Cover
    draw_barcode(p, width/2 - 1*inch, 1.5*inch, f"IAM-{uuid.uuid4().hex[:8].upper()}")
    
    p.showPage()

    # --- PAGE 2: CORE FEATURES & AUTHENTICATION ---
    draw_header_footer(p)
    draw_watermark(p)
    
    y_pos = height - 1.5*inch
    
    p.setFont("Helvetica-Bold", 16)
    p.setFillColor(colors.HexColor('#0d1b3e'))
    p.drawString(0.5*inch, y_pos, "1. Institutional Branding & Verification")
    y_pos -= 0.4*inch
    
    p.setFont("Helvetica", 11)
    p.setFillColor(colors.black)
    text_lines = [
        "The IAMSTECH system utilizes multi-layered visual and digital branding to ensure document integrity:",
        "• Institutional Logo: Present on all official headers to confirm institutional origin.",
        "• Digital Watermarking: Faded background branding prevents unauthorized duplication.",
        "• Barcode/QR Verification: Unique tracking IDs allow for real-time verification of generated reports.",
        "• Secure Signatures: Digital audit trails for all administrative actions."
    ]
    for line in text_lines:
        p.drawString(0.7*inch, y_pos, line)
        y_pos -= 0.2*inch
    
    y_pos -= 0.3*inch
    p.setFont("Helvetica-Bold", 16)
    p.setFillColor(colors.HexColor('#0d1b3e'))
    p.drawString(0.5*inch, y_pos, "2. AI Chatbot & Navigation Efficiency")
    y_pos -= 0.4*inch
    
    p.setFont("Helvetica", 11)
    p.setFillColor(colors.black)
    text_lines = [
        "Our integrated AI Assistant acts as a 24/7 technical and academic advisor:",
        "• Academic Guidance: Explains course requirements and institutional policies.",
        "• Navigation Support: Directs users to dashboards, profiles, and resources.",
        "• Error Recovery: Provides immediate help for OTP delivery and password resets.",
        "• Real-time Alerts: Informs users of global system status and updates."
    ]
    for line in text_lines:
        p.drawString(0.7*inch, y_pos, line)
        y_pos -= 0.2*inch

    y_pos -= 0.3*inch
    p.setFont("Helvetica-Bold", 16)
    p.setFillColor(colors.HexColor('#0d1b3e'))
    p.drawString(0.5*inch, y_pos, "3. Technical Support & SuperAdmin Integration")
    y_pos -= 0.4*inch
    
    p.setFont("Helvetica", 11)
    p.setFillColor(colors.black)
    text_lines = [
        "The SuperAdmin portal provides centralized control and rapid support escalation:",
        "• WhatsApp Escalation: Direct link to technical support for registration hurdles.",
        "• User Management: Full control over Student, Teacher, and Admin accounts.",
        "• Audit Logging: Complete transparency of system modifications and logins.",
        "• Database Resilience: Self-healing architecture with automated backups."
    ]
    for line in text_lines:
        p.drawString(0.7*inch, y_pos, line)
        y_pos -= 0.2*inch

    p.showPage()

    # --- PAGE 3: ACADEMIC WORKFLOWS ---
    draw_header_footer(p)
    draw_watermark(p)
    
    y_pos = height - 1.5*inch
    p.setFont("Helvetica-Bold", 16)
    p.setFillColor(colors.HexColor('#0d1b3e'))
    p.drawString(0.5*inch, y_pos, "4. Academic & Administrative Workflows")
    y_pos -= 0.4*inch
    
    p.setFont("Helvetica", 11)
    p.setFillColor(colors.black)
    text_lines = [
        "Integrated modules for a seamless educational experience:",
        "• Course Management: Instructors can upload resources, assignments, and schedule meetings.",
        "• Attendance Tracking: Real-time attendance monitoring for students and staff.",
        "• Gradebook: Transparent performance tracking and progress reporting.",
        "• Announcements: Role-based communication for courses and institutional updates."
    ]
    for line in text_lines:
        p.drawString(0.7*inch, y_pos, line)
        y_pos -= 0.2*inch

    y_pos -= 0.3*inch
    p.setFont("Helvetica-Bold", 16)
    p.setFillColor(colors.HexColor('#0d1b3e'))
    p.drawString(0.5*inch, y_pos, "5. Security, Privacy & User Experience")
    y_pos -= 0.4*inch
    
    p.setFont("Helvetica", 11)
    p.setFillColor(colors.black)
    text_lines = [
        "Built with modern standards for security and usability:",
        "• Data Encryption: Secure hashing for passwords and sensitive user data.",
        "• Role-Based Access (RBAC): Strict permission boundaries for all user types.",
        "• Responsive Design: Optimized for Desktop, Tablet, and Mobile devices.",
        "• Modern Aesthetics: Glassmorphism and premium design for a professional feel."
    ]
    for line in text_lines:
        p.drawString(0.7*inch, y_pos, line)
        y_pos -= 0.2*inch

    # Final Verification Section
    p.setStrokeColor(colors.HexColor('#ff6f00'))
    p.rect(0.5*inch, 1*inch, width-1*inch, 1.5*inch)
    p.setFont("Helvetica-Bold", 12)
    p.drawString(0.7*inch, 2.2*inch, "DOCUMENT VERIFICATION")
    p.setFont("Helvetica", 9)
    p.drawString(0.7*inch, 2.0*inch, "This document is a certified system demonstration generated by the IAMSTECH Management Portal.")
    p.drawString(0.7*inch, 1.85*inch, "Scan the QR code or verify the Barcode ID at support.iamstech.edu.lr")
    
    try:
        # Add a QR code representation
        qr_code = qr.QrCodeWidget('https://iamstech.edu.lr/verify')
        bounds = qr_code.getBounds()
        qr_width = bounds[2] - bounds[0]
        qr_height = bounds[3] - bounds[1]
        d = Drawing(1*inch, 1*inch, transform=[1*inch/qr_width, 0, 0, 1*inch/qr_height, 0, 0])
        d.add(qr_code)
        renderPDF.draw(d, p, width-1.7*inch, 1.2*inch)
    except: pass

    p.save()
    buffer.seek(0)
    return send_file(buffer, as_attachment=True, download_name=f'IAMSTECH_System_Documentation_{datetime.utcnow().strftime("%Y%m%d")}.pdf', mimetype='application/pdf')

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

@app.route('/admin/request-otp-help/<int:user_id>')
@login_required
@admin_required
def request_otp_help(user_id):
    target_user = User.query.get_or_404(user_id)
    superadmins = User.query.filter_by(role='SuperAdmin').all()
    
    for sa in superadmins:
        n = Notification(
            user_id=sa.id,
            message=f"Admin {current_user.name} requested OTP support for applicant {target_user.name} ({target_user.email}).",
            type='warning',
            link=f"/dashboard?search={target_user.email}"
        )
        db.session.add(n)
    
    db.session.commit()
    flash(f"OTP Support request for {target_user.name} has been sent to the SuperAdmin.", "success")
    return redirect(url_for('dashboard'))

@app.route('/notification/read/<int:n_id>')
@login_required
def mark_notification_read(n_id):
    n = Notification.query.get_or_404(n_id)
    if n.user_id == current_user.id:
        n.is_read = True
        db.session.commit()
    return redirect(n.link if n.link else url_for('dashboard'))

@app.route('/superadmin/force-verify/<int:user_id>')
@login_required
@superadmin_required
def force_verify_user(user_id):
    try:
        user = User.query.get_or_404(user_id)
        if user.is_email_verified:
            flash('User is already verified.', 'info')
        else:
            user.is_email_verified = True
            user.registration_state = 'verified_awaiting_approval'
            user.verification_code = None
            db.session.commit()
            log_audit(f"Force Verified User {user.email}", target_id=user.id, target_type='User')
            flash(f'Account {user.email} successfully force verified. You can now approve them.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Force Verify Error: {e}")
        flash('Could not force verify user.', 'danger')
        
    return redirect(url_for('dashboard'))

@app.route('/admin/approve/<int:user_id>', methods=['GET','POST'])
@app.route('/approve/<int:user_id>', methods=['GET','POST']) # Alias for compatibility
@login_required
@admin_required
def approve_user(user_id):
    user = User.query.get_or_404(user_id)
    requested_role = request.form.get('role') if request.method == 'POST' else None
    new_role = requested_role or DEFAULT_APPROVAL_ROLE

    if new_role not in ROLE_CHOICES:
        new_role = DEFAULT_APPROVAL_ROLE

    if current_user.role != 'SuperAdmin' and new_role not in ADMIN_ASSIGNABLE_ROLES:
        flash('You are not authorized to approve a user with that role.', 'danger')
        return redirect(url_for('dashboard'))

    user.role = new_role
    user.registration_state = 'approved'
    user.status = 'Approved'
    user.student_id = generate_institutional_id(user.role)
    user.school_email = generate_institutional_email(user.name, user.role)
    
    # Generate secure setup token
    user.setup_token = str(uuid.uuid4())
    user.setup_token_expiration = datetime.utcnow() + timedelta(days=3)
    user.must_change_password = True
    
    db.session.commit()

    # Send activation email (fully isolated)
    email_sent = False
    try:
        email_sent = send_approval_email(user)
    except Exception as e:
        logger.error(f"NON-BLOCKING: Failed to send approval email for {user.email}: {str(e)}")
        try:
            with open('scratch/registration_errors.txt', 'a') as f:
                f.write(f"NON-BLOCKING EMAIL ERROR (approval): {str(e)}\n")
        except:
            pass

    # Audit log
    try:
        action_text = f"Approved {user.role}" if email_sent else f"Approved {user.role} (Email Failed)"
        log = AdminAuditLog(admin_id=current_user.id, action=action_text, target_user_id=user.id)
        db.session.add(log)
        db.session.commit()
    except Exception:
        db.session.rollback()

    setup_link = build_external_url('setup_account', token=user.setup_token)
    if email_sent:
        flash(f'Success! {user.name} approved and institutional email sent.', 'success')
        flash(f'MANUAL ACTIVATION LINK: {setup_link}', 'info')
    else:
        flash(f'User approved, but the WELCOME EMAIL FAILED TO SEND. Please check your Railway SMTP environment variables (MAIL_USERNAME/PASSWORD).', 'danger')
        flash(f'MANUAL ACTIVATION LINK: {setup_link}', 'warning')

    return redirect(url_for('dashboard'))

@app.route('/setup-password/<token>', methods=['GET', 'POST'])
@app.route('/setup-account/<token>', methods=['GET', 'POST'])
def setup_account(token):
    # Clear any existing session to prevent "fails to recognize" conflicts
    if current_user.is_authenticated:
        logout_user()
        
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
        user.setup_token = None  # Invalidate token
        user.must_change_password = False
        user.is_email_verified = True   # FIX: approved users bypass OTP verification flow
        user.registration_state = 'approved'  # FIX: ensure state is correct after setup
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

@app.route('/admin/resend_otp/<int:user_id>')
@login_required
@admin_required
def resend_otp(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.reset_token and len(user.reset_token) == 6:
        # Regenerate OTP
        new_otp = f"{random.randint(100000, 999999)}"
        user.reset_token = new_otp
        user.reset_token_expiration = datetime.utcnow() + timedelta(minutes=15)
        db.session.commit()
        
        # Send email
        send_reset_email(user)
        
        flash(f'New OTP sent to {user.email}.', 'success')
    else:
        flash('No active OTP request for this user.', 'warning')
    
    return redirect(url_for('dashboard'))

@app.route('/admin/resend_setup/<int:user_id>')
@login_required
@admin_required
def resend_setup(user_id):
    user = User.query.get_or_404(user_id)

    if user.registration_state == 'approved':
        user.setup_token = str(uuid.uuid4())
        user.setup_token_expiration = datetime.utcnow() + timedelta(days=3)
        user.must_change_password = True
        db.session.commit()

        try:
            email_sent = send_approval_email(user)
            if email_sent:
                flash(f'Success! A new activation link has been sent to {user.email}.', 'success')
            else:
                flash('The activation email failed to send, but a new token has been generated.', 'warning')
        except Exception as e:
            logger.error(f"Failed to resend setup for {user.email}: {e}")
            flash('Internal error sending setup email.', 'danger')
            
        setup_link = build_external_url('setup_account', token=user.setup_token)
        flash(f'MANUAL ACTIVATION LINK: {setup_link}', 'info')
    else:
        flash('This user is not in an approved state.', 'warning')
        
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
        saved_path = save_media_file(photo, 'activities', prefix='activity')
        new_act = Activity(title=title, description=desc, image_path=saved_path)
        db.session.add(new_act)
        db.session.commit()
        flash('Activity uploaded to gallery!', 'success')
    return redirect(url_for('dashboard'))


@app.route('/admin/delete-activity/<int:activity_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_activity(activity_id):
    try:
        act = Activity.query.get_or_404(activity_id)
        # Try to remove the local file too (non-blocking)
        try:
            if act.image_path:
                local_path = os.path.join(app.config['UPLOAD_FOLDER'], act.image_path.replace('uploads/', '', 1))
                if os.path.exists(local_path):
                    os.remove(local_path)
        except Exception:
            pass
        db.session.delete(act)
        db.session.commit()
        log_audit(f"Deleted Activity #{activity_id}", target_id=activity_id, target_type='Activity')
        flash('Activity removed from gallery.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Activity delete error: {e}")
        flash('Could not delete activity.', 'danger')
    return redirect(url_for('dashboard'))


# --- SuperAdmin Controls ---
@app.route('/superadmin/suspend/<int:user_id>', methods=['GET', 'POST'])
@login_required
@superadmin_required
def suspend_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_superadmin:
        flash("Cannot suspend another SuperAdmin.", "danger")
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        reason = request.form.get('reason', 'Violation of platform policies.')
    else:
        reason = 'Administrative Suspension.'

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

@app.route('/admin/change-role/<int:user_id>', methods=['POST'])
@app.route('/superadmin/change-role/<int:user_id>', methods=['POST'])
@login_required
def change_role(user_id):
    if current_user.role not in ['Admin', 'SuperAdmin']:
        flash('Admin access required.', 'danger')
        return redirect(url_for('dashboard'))

    user = User.query.get_or_404(user_id)
    if user.is_superadmin:
        flash('Cannot modify SuperAdmin role.', 'danger')
        return redirect(url_for('dashboard'))

    new_role = request.form.get('role')
    permitted_roles = SUPERADMIN_ASSIGNABLE_ROLES if current_user.role == 'SuperAdmin' else ADMIN_ASSIGNABLE_ROLES

    if new_role not in permitted_roles:
        flash('You are not authorized to assign that role.', 'danger')
        return redirect(url_for('dashboard'))

    old_role = user.role
    user.role = new_role
    if user.registration_state == 'approved':
        user.status = 'Approved'
    db.session.commit()

    if current_user.id == user.id:
        login_user(user, remember=True, fresh=True)

    log_audit(f'Changed role from {old_role} to {new_role}', target_id=user.id, target_type='User')
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

# ===== ADMIN ASSISTANCE / ISSUE REPORTING =====

@app.route('/admin/report-issue', methods=['GET', 'POST'])
@login_required
@admin_required
def report_issue():
    """Admin can report system issues or request assistance"""
    if request.method == 'POST':
        try:
            report_type = request.form.get('report_type', 'assistance')
            title = request.form.get('title', '').strip()
            description = request.form.get('description', '').strip()
            severity = request.form.get('severity', 'medium')
            
            if not title or not description:
                flash('Title and description are required.', 'warning')
                return redirect(url_for('report_issue'))
            
            report = SystemReport(
                user_id=current_user.id,
                report_type=report_type,
                title=title,
                description=description,
                severity=severity,
                status='open'
            )
            db.session.add(report)
            db.session.commit()
            
            # Notify SuperAdmin
            superadmins = User.query.filter_by(role='SuperAdmin').all()
            for admin in superadmins:
                notif = Notification(
                    user_id=admin.id,
                    message=f"New {report_type} report: {title}",
                    type='danger' if severity == 'critical' else 'warning',
                    link=url_for('superadmin_view_reports')
                )
                db.session.add(notif)
            db.session.commit()
            
            flash(f'Your {report_type} report has been submitted. The SuperAdmin has been notified.', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Issue report error: {e}")
            flash('Failed to submit report. Please try again.', 'danger')
    
    return render_template('admin_report_issue.html')

@app.route('/superadmin/reports', methods=['GET'])
@login_required
@superadmin_required
def superadmin_view_reports():
    """SuperAdmin view all submitted reports"""
    try:
        page = request.args.get('page', 1, type=int)
        status_filter = request.args.get('status', '')
        severity_filter = request.args.get('severity', '')
        
        query = SystemReport.query.order_by(SystemReport.created_at.desc())
        
        if status_filter:
            query = query.filter_by(status=status_filter)
        if severity_filter:
            query = query.filter_by(severity=severity_filter)
        
        reports = query.paginate(page=page, per_page=20)
        return render_template('superadmin_reports.html', reports=reports, 
                             status_filter=status_filter, severity_filter=severity_filter)
    except Exception as e:
        logger.error(f"SuperAdmin reports view error: {e}")
        flash('Error loading reports.', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/superadmin/report/<int:report_id>/update', methods=['POST'])
@login_required
@superadmin_required
def update_report_status(report_id):
    """Update report status and add resolution notes"""
    try:
        report = SystemReport.query.get_or_404(report_id)
        status = request.form.get('status', 'open')
        notes = request.form.get('resolution_notes', '')
        
        report.status = status
        if notes:
            report.resolution_notes = notes
        report.updated_at = datetime.utcnow()
        db.session.commit()
        
        log_audit(f"Updated report #{report_id} status to {status}")
        flash(f'Report status updated to {status}.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Report update error: {e}")
        flash('Failed to update report.', 'danger')
    
    return redirect(request.referrer or url_for('superadmin_view_reports'))

# ===== SUPER ADMIN CONTENT MANAGEMENT =====

@app.route('/superadmin/delete-activity/<int:activity_id>', methods=['POST'])
@login_required
@superadmin_required
def superadmin_delete_activity(activity_id):
    """SuperAdmin can delete activities"""
    try:
        activity = Activity.query.get_or_404(activity_id)
        db.session.delete(activity)
        db.session.commit()
        log_audit(f"Deleted activity: {activity.title}")
        flash(f'Activity "{activity.title}" has been deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Activity deletion error: {e}")
        flash('Failed to delete activity.', 'danger')
    
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/superadmin/delete-announcement/<int:ann_id>', methods=['POST'])
@login_required
@superadmin_required
def superadmin_delete_announcement(ann_id):
    """SuperAdmin can delete announcements"""
    try:
        announcement = Announcement.query.get_or_404(ann_id)
        db.session.delete(announcement)
        db.session.commit()
        log_audit(f"Deleted announcement: {announcement.title}")
        flash(f'Announcement "{announcement.title}" has been deleted.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Announcement deletion error: {e}")
        flash('Failed to delete announcement.', 'danger')
    
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/superadmin/delete-user/<int:user_id>', methods=['POST'])
@login_required
@superadmin_required
def superadmin_delete_user(user_id):
    """SuperAdmin can deactivate/delete users"""
    try:
        if user_id == current_user.id:
            flash('You cannot delete your own account.', 'danger')
            return redirect(url_for('dashboard'))
        
        user = User.query.get_or_404(user_id)
        # Soft delete: mark as suspended instead
        user.is_suspended = True
        user.suspension_reason = "Account removed by Super Administrator"
        db.session.commit()
        log_audit(f"Deactivated user: {user.email}")
        flash(f'User {user.email} has been deactivated.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"User deletion error: {e}")
        flash('Failed to deactivate user.', 'danger')
    
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/superadmin/toggle-feature/<feature_name>', methods=['POST'])
@login_required
@superadmin_required
def toggle_feature(feature_name):
    """SuperAdmin can disable/enable system features"""
    try:
        # This would require a SystemConfig table in production
        # For now, we'll just log and notify
        action = request.form.get('action', 'disable')
        log_audit(f"Feature toggle: {feature_name} set to {action}")
        flash(f'Feature "{feature_name}" has been {action}d.', 'success')
    except Exception as e:
        logger.error(f"Feature toggle error: {e}")
        flash('Failed to toggle feature.', 'danger')
    
    return redirect(request.referrer or url_for('dashboard'))


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
        
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = f"attachment; filename={filename}"
    output.headers["Content-type"] = "text/csv"
    return output



@app.route('/chatbot', methods=['POST'])
def chatbot():
    data = request.json
    msg = data.get('message', '').lower()
    
    # Dynamic Context from Database
    founder_data = Founder.query.first()
    f_name = founder_data.name if founder_data else "Beniah Success Kanawa"
    f_vision = founder_data.vision if (founder_data and founder_data.vision) else "To become Liberia’s premier center of excellence for technology and business education."
    f_mission = founder_data.mission if (founder_data and founder_data.mission) else "To deliver industry-relevant, hands-on education in Information Technology and Accounting."
    f_bio = founder_data.bio if (founder_data and founder_data.bio) else "Our founder is a visionary leader dedicated to bridging the technological gap in Liberia."
    f_leadership = founder_data.leadership_statement if (founder_data and founder_data.leadership_statement) else "Cultivating the architects of Liberia's digital future."

    responses = {
        "greetings": [
            "Hello! I'm the IAMSTECH AI Assistant. How can I help you today? Ask me about our programs, admissions, or even how I was built!",
            "Greetings from IAMSTECH LIBERIA! What would you like to know about our institute? I'm ready to assist!",
            "Hi there! Ready to start your professional journey? Ask me anything about IAMSTECH—I promise I'm more helpful than a broken pencil! ✏️",
            "Welcome! I'm here to assist you. Ask me about our courses, fees, or even how to fix those pesky OTP issues."
        ],
        "founder": [
            f"Our Founder & CEO is {f_name}. {f_bio}",
            f"IAMSTECH LIBERIA was founded by {f_name}, a visionary leader committed to transforming technology education in Liberia. {f_leadership}",
            f"{f_name} founded IAMSTECH with a bold vision: to bridge the digital skills gap in Liberia and create world-class IT professionals."
        ],
        "developer": [
            "I was built with pride by a young, ambitious developer from Liberia! 🇱🇷 He is a student of Information Engineering who is passionate about solving real-world problems through technology. My creation aligns perfectly with the mission and vision of IAMSTECH Liberia to innovate and educate!",
            "My 'parent' is a Liberian Information Engineering student! He's dedicated to building tech solutions for Liberia's future. He's the brains behind my circuits, and he's a huge believer in the IAMSTECH mission.",
            "I'm a product of Liberian innovation! Developed by an Information Engineering student, I represent the problem-solving spirit that IAMSTECH instills in all its students."
        ],
        "vision": [
            f"IAMSTECH's Vision: {f_vision}",
            f"Our institutional vision, as set by our founder, is: {f_vision}",
            "We envision a Liberia where every young person has access to world-class technology and vocational education."
        ],
        "mission": [
            f"IAMSTECH's Mission: {f_mission}",
            f"Our mission drives everything we do: {f_mission}",
            "IAMSTECH is on a mission to deliver industry-relevant, hands-on education in IT, Accounting, and modern business skills."
        ],
        "programs": [
            "IAMSTECH offers professional certification programs in: 🖥️ Microsoft Office Suite, 📊 QuickBooks Accounting, 🤖 AI & Machine Learning Techniques, 🔧 Computer Hardware Engineering, and 💼 Business Administration. Which program interests you?",
            "Our programs include: Microsoft Office Suite, QuickBooks Accounting, AI Techniques, Computer Hardware Engineering, Graphic Design, and Networking. All are hands-on and industry-focused with certificates upon completion.",
            "We offer short-term (3–6 months) professional certification courses in IT, Accounting, and Business. All programs are practical, affordable, and designed for employment readiness."
        ],
        "career_guidance": [
            "Choosing a course is like choosing a superpower! 🦸‍♂️ For example, **MS Office** makes you an administrative wizard. **QuickBooks** turns you into a financial mastermind. **Hardware Engineering** means you can fix the systems that run the world, and **AI**? Well, that's like learning to talk to the future!",
            "Our courses are designed for the job market. **MS Office** students often find roles as office managers or project assistants. **QuickBooks** graduates are highly sought after as bookkeepers and accountants. **Hardware** experts run IT departments, and **AI** specialists are building the next generation of software!",
            "Skills you'll gain: Problem-solving, technical mastery, and professional confidence. Real-world applications are everywhere—from local businesses in Monrovia to global tech firms. Your future is what you build with the skills you learn here at IAMSTECH!"
        ],
        "otp_support": [
            "OTP issues can be frustrating, but don't worry, I'm here to help! 🛠️ Step 1: Check your Spam or Junk folder (sometimes they like to hide there!). Step 2: Make sure your email/phone is correct. Step 3: If it's still missing, you can request a new one on the verification page. If all else fails, our Admin team can 'Force Verify' you in seconds—just ask them!",
            "Missing your code? 🕵️‍♂️ Check your Junk folder first. If it's not there, try requesting a resend. Email delivery can sometimes be slow like a Monday morning, so give it a minute! If you're still stuck, reach out to support on WhatsApp (+231 880 864 187) and we'll get you in!",
            "To get a new OTP, simply click 'Resend Code' on the verification screen. If you're having login trouble, ensure you're using the correct email. We're here to make sure you get in smoothly—stay positive, we've got this! 😊"
        ],
        "location": [
            "IAMSTECH LIBERIA is located on Hotel Africa Road, Sinkor, Monrovia, Liberia 🇱🇷. We are easily accessible by public transport from central Monrovia.",
            "You can find us at Hotel Africa Road, Sinkor, Monrovia, Liberia. Our campus is open Monday–Saturday, 8am–6pm. For directions, call +231 775 478 90.",
            "Our campus is on Hotel Africa Road, Monrovia, Liberia. Come visit us — we're happy to give you a tour and walk you through our programs in person!"
        ],
        "fees": [
            "Our tuition fees are affordable and vary by program. For the exact fee schedule, please visit our Admissions office at Hotel Africa Road, Monrovia, or WhatsApp us at +231 880 864 187.",
            "IAMSTECH offers flexible and affordable payment plans. Contact us at +231 880 864 187 (WhatsApp) for a full fee breakdown by program.",
            "We believe quality education should be accessible. Our fees are competitively priced. Reach out via WhatsApp at +231 880 864 187 for a detailed fee schedule."
        ],
        "duration": [
            "Most of our professional certificate programs run for 3 to 6 months of intensive, hands-on training — perfect for those who want to skill up fast!",
            "Our courses are designed to get you job-ready quickly. Programs typically run 3–6 months depending on the subject. Some advanced courses may run up to 12 months.",
            "IAMSTECH programs are short, focused, and powerful. Expect 3–6 months per certification, with options to stack multiple certificates."
        ],
        "support": [
            "For technical support, contact our team via WhatsApp at 📱 +231 880 864 187. You can also use the Technical Support Center inside your student dashboard.",
            "Need help? Our support team is available Monday–Saturday, 8am–6pm. Reach us on WhatsApp: +231 880 864 187 or visit us on Hotel Africa Road, Monrovia.",
            "If you're experiencing login issues, email delivery problems, or portal errors, our tech team is ready to help. WhatsApp: +231 880 864 187."
        ],
        "motto": [
            "IAMSTECH's motto is: 'Empowering Liberia Through Technology & Excellence.' 🌟 We believe education is the greatest equalizer.",
            "Our guiding principle: Excellence, Innovation, and Empowerment. We are committed to cultivating the architects of Liberia's digital future.",
            "At IAMSTECH, we live by the words: 'Building Tomorrow's Leaders Today' — through hands-on technical and vocational education."
        ],
        "about": [
            "IAMSTECH LIBERIA (Institute of Advanced Management Science & Technology) is a premier professional vocational and technology institute based in Monrovia, Liberia. We specialize in IT, Accounting, and modern business skills.",
            "We are IAMSTECH LIBERIA — Liberia's dedicated center for practical technology and business education. Our programs are hands-on, industry-aligned, and designed to produce employment-ready graduates.",
            "IAMSTECH is a specialized vocational institute in Monrovia, Liberia, focused on equipping students with cutting-edge skills in Information Technology and Accounting since its founding."
        ],
        "contact": [
            "You can reach IAMSTECH at: 📱 WhatsApp: +231 880 864 187 | 📍 Hotel Africa Road, Sinkor, Monrovia, Liberia | 🌐 Through this portal's registration page.",
            "Contact us via WhatsApp at +231 880 864 187, visit our campus on Hotel Africa Road, Monrovia, or use the Support Center in your student dashboard."
        ],
        "certificate": [
            "Yes! All IAMSTECH programs come with an official certificate upon successful completion. Our certificates are recognized by employers across Liberia and the region.",
            "Every graduate receives a professional certificate from IAMSTECH LIBERIA. Our credentials are respected by leading employers in IT, Finance, and Business sectors."
        ],
        "admission": [
            "Admission to IAMSTECH is straightforward! Complete our online application, verify your email, and submit required documents. Our team reviews applications within 24-48 hours. For questions, WhatsApp us at +231 880 864 187.",
            "To join IAMSTECH, fill out the online registration form, verify your email with the OTP, and upload your documents. We accept applications year-round with rolling admissions. Contact admissions at +231 880 864 187 for guidance.",
            "Our admission process is simple: Register online, verify your email, submit documents, and await approval. We offer flexible start dates and payment plans. Reach out via WhatsApp for personalized assistance."
        ],
        "requirements": [
            "Basic requirements: Valid ID, high school diploma or equivalent, basic computer skills. Specific program requirements vary—contact us at +231 880 864 187 for details on your chosen course.",
            "You'll need: Government-issued ID, educational certificates, and proof of address. Some programs require prior experience. WhatsApp +231 880 864 187 for a complete requirements checklist.",
            "Admission requirements include ID verification, educational background check, and basic computer literacy. Program-specific prerequisites apply. Call our admissions office for detailed guidance."
        ]
    }

    # Intent Matching — SPECIFIC intents checked BEFORE generic ones
    matched_intent = None

    # 1. Greetings — first to avoid false matches
    if re.search(r'\b(hello|hi|hey|greetings|good morning|good afternoon|good evening|yo|howdy|welcome|help)\b', msg):
        matched_intent = "greetings"

    # 2. OTP & Login Assistance (Priority Support)
    elif re.search(r'\b(otp|code|received|verify|login|access|setup|trouble|password|stuck)\b', msg):
        matched_intent = "otp_support"

    # 3. Career Guidance
    elif re.search(r'\b(career|job|opportunity|skill|benefit|application|why study|value|future|work|hire|employ)\b', msg):
        matched_intent = "career_guidance"

    # 4. Developer — MUST come before "about"
    elif re.search(r'\b(developer|who made|creator|author|build me|brain|student|information engineering)\b', msg):
        matched_intent = "developer"

    # 5. Founder
    elif re.search(r'\b(founder|ceo|director|president|leader|who started|who founded|benaiah|kanawa|simone|swaray)\b', msg) or \
         ('who' in msg and ('start' in msg or 'found' in msg or 'creat' in msg or 'build' in msg or 'establish' in msg)):
        matched_intent = "founder"

    # 6. Vision
    elif re.search(r'\b(vision|future|long.?term goal)\b', msg):
        matched_intent = "vision"

    # 7. Mission
    elif re.search(r'\b(mission|purpose|aim|objective)\b', msg):
        matched_intent = "mission"

    # 8. Programs/Courses
    elif re.search(r'\b(program|course|study|learn|department|accounting|quickbooks|microsoft|hardware|networking|graphic|ai|certificate|certification)\b', msg):
        matched_intent = "programs"

    # 9. Location
    elif re.search(r'\b(location|where|address|locate|map|situated|campus|find you|directions?)\b', msg):
        matched_intent = "location"

    # 10. Fees/Cost
    elif re.search(r'\b(fees?|cost|price|pay|tuition|amount|dollar|money)\b', msg):
        matched_intent = "fees"

    # 11. Duration
    elif re.search(r'\b(long|duration|time|how many months|period|length)\b', msg):
        matched_intent = "duration"

    # 12. Support
    elif re.search(r'\b(support|technical|tech|problem|error|crash|broken|help me)\b', msg):
        matched_intent = "support"

    # 13. Motto
    elif re.search(r'\b(motto|slogan|principle|value|empower)\b', msg):
        matched_intent = "motto"

    # 14. Contact
    elif re.search(r'\b(contact|phone|number|whatsapp|email|reach|call)\b', msg):
        matched_intent = "contact"

    # 15. About (Fallback for general info)
    elif re.search(r'\b(about|who are you|what is iamstech|tell me more|information|info)\b', msg):
        matched_intent = "about"

    # 16. Admission
    elif re.search(r'\b(admission|enrollment|apply|join|register|admit)\b', msg):
        matched_intent = "admission"

    # 17. Requirements
    elif re.search(r'\b(requirement|qualification|eligible|need|prerequisite)\b', msg):
        matched_intent = "requirements"

    # Final Selection Logic
    if matched_intent and matched_intent in responses:
        response = random.choice(responses[matched_intent])
    else:
        # Slightly humorous default response
        response = random.choice([
            "I'm not 100% sure I caught that—my gears might need a little oil! ⚙️ But I can definitely help you with Course Info, Career Guidance, or OTP/Login issues. What's on your mind?",
            "Hmm, that's a tough one! Even my circuits are scratching their heads. 🤖 Maybe try asking about our courses or how to fix OTP issues? I'm much better at those!",
            "I'm sorry, I didn't quite get that. I'm still learning! (It's hard being an AI sometimes, you know? 😅) Ask me about our founder, programs, or career opportunities instead!"
        ])
    
    return jsonify({"response": response})

@app.route('/update-profile-photo', methods=['POST'])
@login_required
def update_profile_photo():
    """Allows any logged-in user to update their profile photo."""
    photo = request.files.get('profile_photo')
    if not photo or not photo.filename:
        flash('No photo selected.', 'warning')
        return redirect(request.referrer or url_for('dashboard'))
    try:
        saved_path = save_media_file(photo, 'profiles', prefix=current_user.email.split('@')[0])
        if saved_path:
            current_user.profile_photo = saved_path
            db.session.commit()
            flash('Profile photo updated successfully!', 'success')
        else:
            flash('Photo upload failed. Please try again.', 'danger')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Profile photo update error: {e}")
        flash('An error occurred while updating your photo.', 'danger')
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/my_eid')
@login_required
def my_eid():
    if current_user.role == 'Applicant' and current_user.registration_state != 'approved':
        flash("Your E-ID is not generated yet. You must be fully approved.", "warning")
        return redirect(url_for('dashboard'))
    return redirect(url_for('view_eid', user_id=current_user.id))

@app.route('/view_eid/<int:user_id>')
@login_required
def view_eid(user_id):
    if current_user.id != user_id and current_user.role not in ['Admin', 'SuperAdmin']:
        flash("Unauthorized access.", "danger")
        return redirect(url_for('dashboard'))
        
    user = User.query.get_or_404(user_id)
    if not user.student_id:
        if user.role in ['SuperAdmin', 'Admin', 'Teacher', 'Staff'] or user.registration_state == 'approved':
            # Auto-generate ID if missing for approved/staff roles
            user.student_id = generate_institutional_id(user.role)
            db.session.commit()
        else:
            flash("This user does not have an ID number assigned.", "warning")
            return redirect(url_for('dashboard'))
        
    return render_template('dashboards/eid_card.html', user=user)
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/debug_sys')
def debug_sys():
    import os, sys
    from sqlalchemy import inspect
    try:
        db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', 'NOT SET')
        # Strip query params like ?timeout=20
        db_file = db_uri.split('?')[0].replace('sqlite:///', '') if db_uri.startswith('sqlite:///') else 'NOT SQLITE'
        
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        
        info = {
            'cwd': os.getcwd(),
            'db_uri': db_uri,
            'db_file': db_file,
            'db_file_exists': os.path.exists(db_file) if db_file != 'NOT SQLITE' else 'N/A',
            'tables': tables,
            'data_dir_exists': os.path.exists('/data'),
            'instance_path': app.instance_path,
            'migration_success_exists': os.path.exists('/tmp/migration_success')
        }
        return jsonify(info)
    except Exception as e:
        return str(e), 500


# --- Production Entry Point for Vercel ---
def handler(event, context):
    return app(event, context)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=bool(os.environ.get('FLASK_DEBUG', False)))
