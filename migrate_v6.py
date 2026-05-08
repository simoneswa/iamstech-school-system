import os
import sys
import subprocess
from datetime import datetime, timedelta

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError

# -------------------------------------------------------------------
# 1. Load and validate DATABASE_URL
# -------------------------------------------------------------------
DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    # Fallback to local SQLite for development (creates a file backup later)
    db_path = os.path.join(os.path.abspath(os.getcwd()), 'instance', 'iamstech.db')
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    DATABASE_URL = f'sqlite:///{db_path}'
    print('INFO: Using SQLite fallback DB at', db_path)
else:
    # Convert legacy scheme for SQLAlchemy compatibility
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

engine = create_engine(DATABASE_URL, echo=False)
connection = engine.connect()
inspector = inspect(engine)

# -------------------------------------------------------------------
# 2. Safety – create a DB backup / snapshot before any mutation
# -------------------------------------------------------------------
def create_backup():
    print('=== Creating database backup ===')
    if DATABASE_URL.startswith('postgresql://'):
        # Use pg_dump – ensure pg_dump is available in the environment
        backup_file = f'backup_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}.sql'
        try:
            subprocess.run([
                'pg_dump',
                DATABASE_URL,
                '--format=c',  # custom format (compressed)
                '--file', backup_file
            ], check=True)
            print(f'Backup created: {backup_file}')
        except Exception as e:
            print('WARNING: pg_dump failed – proceeding without backup:', e)
    else:
        # SQLite – copy the file
        src = db_path
        dst = f'{src}.backup_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}'
        try:
            import shutil
            shutil.copy2(src, dst)
            print(f'SQLite backup created: {dst}')
        except Exception as e:
            print('WARNING: SQLite backup failed – proceeding without backup:', e)

create_backup()

# Helper: wrap DDL/DML in a transaction for atomicity
def execute_sql(stmt, params=None):
    try:
        # In SQLAlchemy 2.0, connection.execute() usually manages its own transaction if not explicit.
        # However, to be safe and ensure it's committed, we use the connection directly.
        # If we want a transaction, we should use connection.begin() at a higher level.
        if params:
            connection.execute(text(stmt), params)
        else:
            connection.execute(text(stmt))
        connection.commit()
    except Exception as exc:
        connection.rollback()
        raise exc


def column_exists(table_name, column_name):
    return column_name in [col['name'] for col in inspector.get_columns(table_name)]

def add_registration_state_column():
    # Idempotent – only add if missing
    if not column_exists('user', 'registration_state'):
        print('Adding registration_state column to user table...')
        try:
            # DDL usually doesn't need commit in some DBs but we ensure it here
            connection.execute(text("ALTER TABLE \"user\" ADD COLUMN registration_state VARCHAR(30) DEFAULT 'pending_verification'"))
            connection.commit()
        except OperationalError as e:
            print('ERROR adding registration_state column:', e)
            sys.exit(1)
    else:
        print('registration_state column already exists – skipping.')

def migrate_user_states():
    # Migrate legacy 'status' + verification flags into the new registration_state enum.
    print('Migrating existing user status values to registration_state...')
    # Fetch all users first to avoid open result set issues during updates
    result = connection.execute(text("SELECT id, status, is_email_verified FROM \"user\"")).fetchall()
    
    batch_size = 50
    for i in range(0, len(result), batch_size):
        batch = result[i:i+batch_size]
        for row in batch:
            uid, status, verified = row
            # Default to pending verification for most cases
            new_state = 'pending_verification'
            if verified and status == 'Approved':
                new_state = 'approved'
            elif verified:
                new_state = 'verified_awaiting_approval'
            elif status in ('Pending', 'Awaiting Verification'):
                new_state = 'pending_verification'
            elif status == 'Rejected':
                new_state = 'rejected'
            elif status == 'Suspended':
                new_state = 'suspended'
            
            # Perform update idempotently – only if changed
            connection.execute(text("UPDATE \"user\" SET registration_state = :state WHERE id = :uid AND (registration_state IS NULL OR registration_state != :state)"),
                        {'state': new_state, 'uid': uid})
        connection.commit()
        print(f'Processed batch of {len(batch)} users...')
    
    print('User registration_state migration completed.')

def cleanup_duplicate_emails():
    # Remove duplicate email entries while preserving the SuperAdmin account.
    print('Cleaning duplicate email records (preserving SuperAdmin)...')
    dup_query = text('''
        SELECT email FROM "user" GROUP BY email HAVING COUNT(*) > 1
    ''')
    duplicate_emails = [row[0] for row in connection.execute(dup_query)]
    total_removed = 0
    for email in duplicate_emails:
        # Skip critical email addresses that belong to SuperAdmin or essential entities.
        if email.lower() == 'simoneswaraykeepitup@founder':
            continue
        users = connection.execute(text('SELECT id, is_superadmin, created_at FROM "user" WHERE email = :email ORDER BY created_at DESC'), {'email': email}).fetchall()
        # Keep the newest non‑SuperAdmin record, delete the rest.
        keep_id = None
        for user in users:
            if keep_id is None and not user['is_superadmin']:
                keep_id = user['id']
                continue
            # Delete any extra records (including stray SuperAdmin copies – unlikely)
            connection.execute(text('DELETE FROM "user" WHERE id = :uid'), {'uid': user['id']})
            total_removed += 1
        connection.commit()
    print(f'Duplicate email cleanup removed {total_removed} rows.')

def cleanup_abandoned_otps():
    # Delete user rows that never completed verification and whose OTP expired > 1h.
    print('Cleaning up abandoned OTP/verification records...')
    cutoff = datetime.utcnow() - timedelta(hours=1)
    delete_stmt = text('''
        DELETE FROM "user"
        WHERE is_email_verified = FALSE
          AND verification_code_expires IS NOT NULL
          AND verification_code_expires < :cutoff
          AND is_superadmin = FALSE
    ''')
    result = connection.execute(delete_stmt, {'cutoff': cutoff})
    connection.commit()
    print(f'Abandoned verification cleanup removed {result.rowcount} rows.')

def ensure_homepage_section_table():
    # Preserve existing homepage content – only create if missing.
    if not inspector.has_table('homepage_section'):
        print('Creating homepage_section table...')
        connection.execute(text('''
            CREATE TABLE homepage_section (
                id SERIAL PRIMARY KEY,
                title VARCHAR(200) NOT NULL,
                description TEXT,
                image_path VARCHAR(200),
                display_order INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        '''))
        connection.commit()
    else:
        print('homepage_section table already exists – skipping creation.')

def add_indexes():
    # Ensure an index on registration_state for fast look‑ups.
    existing_indexes = inspector.get_indexes('user')
    index_names = [idx['name'] for idx in existing_indexes]
    if 'ix_user_registration_state' not in index_names:
        print('Creating index on user.registration_state')
        connection.execute(text('CREATE INDEX ix_user_registration_state ON "user" (registration_state)'))
        connection.commit()
    else:
        print('Index on registration_state already exists – skipping.')

def add_timestamps():
    is_sqlite = 'sqlite' in DATABASE_URL
    if not column_exists('user', 'created_at'):
        print('Adding created_at column to user table...')
        if is_sqlite:
            connection.execute(text("ALTER TABLE \"user\" ADD COLUMN created_at TIMESTAMP"))
            connection.execute(text("UPDATE \"user\" SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
        else:
            connection.execute(text("ALTER TABLE \"user\" ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
        connection.commit()
    if not column_exists('user', 'updated_at'):
        print('Adding updated_at column to user table...')
        if is_sqlite:
            connection.execute(text("ALTER TABLE \"user\" ADD COLUMN updated_at TIMESTAMP"))
            connection.execute(text("UPDATE \"user\" SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"))
        else:
            connection.execute(text("ALTER TABLE \"user\" ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
        connection.commit()


def run_all():
    add_registration_state_column()
    add_timestamps()
    migrate_user_states()
    cleanup_duplicate_emails()
    cleanup_abandoned_otps()
    ensure_homepage_section_table()
    add_indexes()
    print('Database migration and repair completed successfully.')


if __name__ == '__main__':
    run_all()
    connection.close()
