import os
import psycopg2
from urllib.parse import urlparse

def migrate():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("DATABASE_URL not found. Skipping migration.")
        return

    result = urlparse(database_url)
    username = result.username
    password = result.password
    database = result.path[1:]
    hostname = result.hostname
    port = result.port

    try:
        conn = psycopg2.connect(
            database=database,
            user=username,
            password=password,
            host=hostname,
            port=port
        )
        cur = conn.cursor()

        print("Adding verification columns to 'user' table...")
        
        columns = [
            ("is_email_verified", "BOOLEAN DEFAULT FALSE"),
            ("verification_code", "VARCHAR(6)"),
            ("verification_code_expires", "TIMESTAMP"),
            ("verification_attempts", "INTEGER DEFAULT 0"),
            ("resend_cooldown", "TIMESTAMP")
        ]

        for col_name, col_type in columns:
            try:
                cur.execute(f"ALTER TABLE \"user\" ADD COLUMN {col_name} {col_type};")
                print(f"Added column: {col_name}")
            except Exception as e:
                conn.rollback()
                print(f"Column {col_name} might already exist or error: {e}")
                continue
        
        conn.commit()
        cur.close()
        conn.close()
        print("Migration complete.")

    except Exception as e:
        print(f"Migration error: {e}")

if __name__ == "__main__":
    migrate()
