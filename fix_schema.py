import os
import sqlite3
import psycopg2
from urllib.parse import urlparse

def get_connection():
    db_url = os.environ.get("DATABASE_URL")
    if db_url and not db_url.startswith("sqlite"):
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        
        result = urlparse(db_url)
        return psycopg2.connect(
            database=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port
        ), "postgres"
    else:
        # Determine local sqlite path
        if os.path.exists('/data/iamstech.db'):
            db_path = '/data/iamstech.db'
        elif os.path.exists('/tmp/iamstech.db'):
            db_path = '/tmp/iamstech.db'
        elif os.path.exists('instance/iamstech.db'):
            db_path = 'instance/iamstech.db'
        else:
            db_path = 'iamstech.db'
        
        print(f"Connecting to SQLite: {db_path}")
        return sqlite3.connect(db_path), "sqlite"

def fix_schema():
    conn, db_type = get_connection()
    cur = conn.cursor()
    
    print(f"Starting schema repair for {db_type}...")

    # 1. Handle table renames if necessary (Plural to Singular)
    # This addresses the case where old DB has 'users' but code expects 'user'
    table_renames = [
        ("users", "user"),
        ("courses", "course"),
        ("enrollments", "enrollment"),
        ("assignments", "assignment"),
        ("announcements", "announcement"),
        ("meetings", "meeting"),
        ("activities", "activity")
    ]

    for old_name, new_name in table_renames:
        try:
            if db_type == "sqlite":
                # Check if old table exists
                cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{old_name}'")
                if cur.fetchone():
                    # Check if new table exists
                    cur.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{new_name}'")
                    if not cur.fetchone():
                        print(f"Renaming table {old_name} to {new_name}...")
                        cur.execute(f"ALTER TABLE {old_name} RENAME TO {new_name}")
            else:
                # Postgres check
                cur.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{old_name}')")
                if cur.fetchone()[0]:
                    cur.execute(f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{new_name}')")
                    if not cur.fetchone()[0]:
                        print(f"Renaming table \"{old_name}\" to \"{new_name}\"...")
                        cur.execute(f"ALTER TABLE \"{old_name}\" RENAME TO \"{new_name}\"")
            conn.commit()
        except Exception as e:
            print(f"Error renaming {old_name}: {e}")
            conn.rollback() if db_type == "postgres" else None

    # 2. Ensure missing columns exist in the 'user' table
    columns = [
        ("is_email_verified", "BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT FALSE"),
        ("verification_code", "VARCHAR(6)", "VARCHAR(6)"),
        ("verification_code_expires", "TIMESTAMP", "TIMESTAMP"),
        ("verification_attempts", "INTEGER DEFAULT 0", "INTEGER DEFAULT 0"),
        ("resend_cooldown", "TIMESTAMP", "TIMESTAMP"),
        ("is_suspended", "BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT FALSE"),
        ("suspension_reason", "TEXT", "TEXT"),
        ("reset_token", "VARCHAR(100)", "VARCHAR(100)"),
        ("reset_token_expiration", "TIMESTAMP", "TIMESTAMP"),
        ("last_login_reward_date", "DATE", "DATE"),
        ("setup_token", "VARCHAR(100)", "VARCHAR(100)"),
        ("setup_token_expiration", "TIMESTAMP", "TIMESTAMP"),
        ("is_superadmin", "BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT FALSE"),
        ("must_change_password", "BOOLEAN DEFAULT 1", "BOOLEAN DEFAULT TRUE"),
        ("points", "INTEGER DEFAULT 0", "INTEGER DEFAULT 0"),
        ("school_email", "VARCHAR(120)", "VARCHAR(120)"),
        ("student_id", "VARCHAR(20)", "VARCHAR(20)")
    ]

    for col_name, type_sqlite, type_postgres in columns:
        col_type = type_sqlite if db_type == "sqlite" else type_postgres
        try:
            if db_type == "sqlite":
                cur.execute(f"ALTER TABLE user ADD COLUMN {col_name} {col_type}")
            else:
                cur.execute(f"ALTER TABLE \"user\" ADD COLUMN {col_name} {col_type}")
            print(f"Successfully added column: {col_name}")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                pass # Expected if already exists
            else:
                print(f"Error adding {col_name}: {e}")
            conn.rollback() if db_type == "postgres" else None
            continue
    
    conn.commit()
    cur.close()
    conn.close()
    print("Schema repair complete.")

if __name__ == "__main__":
    fix_schema()
