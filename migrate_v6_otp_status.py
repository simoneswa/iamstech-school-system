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

        print("Adding 'otp_email_status' column to 'user' table...")
        
        try:
            cur.execute("ALTER TABLE \"user\" ADD COLUMN otp_email_status VARCHAR(20) DEFAULT 'pending';")
            print("Added column: otp_email_status")
        except Exception as e:
            conn.rollback()
            print(f"Column 'otp_email_status' might already exist or error: {e}")
        
        conn.commit()
        cur.close()
        conn.close()
        print("Migration complete.")

    except Exception as e:
        print(f"Migration error: {e}")

if __name__ == "__main__":
    migrate()
