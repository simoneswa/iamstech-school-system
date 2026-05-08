import os
import psycopg2
from urllib.parse import urlparse

def cleanup():
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        print("DATABASE_URL not found.")
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

        print("Executing Deep Cleanup of Test/Abandoned Records...")
        
        # 1. Delete audit logs first (FK dependencies)
        cur.execute("DELETE FROM admin_audit_log WHERE admin_id IN (SELECT id FROM \"user\" WHERE is_superadmin = FALSE);")
        cur.execute("DELETE FROM system_audit_log WHERE user_id IN (SELECT id FROM \"user\" WHERE is_superadmin = FALSE);")
        
        # 2. Delete all non-superadmin users (Resetting the system)
        cur.execute("DELETE FROM \"user\" WHERE is_superadmin = FALSE;")
        
        conn.commit()
        print(f"Deep Cleanup Successful.")
        cur.close()
        conn.close()

    except Exception as e:
        print(f"Cleanup error: {e}")

if __name__ == "__main__":
    cleanup()
