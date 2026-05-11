import os
import sys
from sqlalchemy import create_client
from sqlalchemy import create_engine, inspect, text
from dotenv import load_dotenv

load_dotenv()

db_url = os.environ.get("DATABASE_URL")
if not db_url:
    print("DATABASE_URL not set")
    sys.exit(1)

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

engine = create_engine(db_url)

def check_schema():
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    print(f"Tables found: {tables}")
    
    expected_tables = ['user', 'course', 'enrollment', 'assignment', 'attendance', 'announcement', 'meeting', 'lesson_material', 'activity', 'founder', 'developer', 'admin_audit_log', 'system_audit_log', 'notification', 'system_report', 'homepage_section', 'global_alert']
    
    for table in expected_tables:
        if table not in tables:
            print(f"MISSING TABLE: {table}")
            continue
        
        columns = [c['name'] for c in inspector.get_columns(table)]
        print(f"Table '{table}' columns: {columns}")

if __name__ == "__main__":
    try:
        check_schema()
    except Exception as e:
        print(f"Error: {e}")
