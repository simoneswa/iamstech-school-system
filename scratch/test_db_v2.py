
from app import app, db
from models import User, Course
from sqlalchemy import text

with app.app_context():
    try:
        # Check DB URI
        print(f"DB URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
        
        # Check tables
        result = db.session.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
        tables = [row[0] for row in result]
        print(f"Tables: {tables}")
        
        # Check users count
        user_count = User.query.count()
        print(f"User count: {user_count}")
        
        # Check for SuperAdmin
        sa = User.query.filter_by(role='SuperAdmin').first()
        if sa:
            print(f"SuperAdmin found: {sa.email}")
        else:
            print("SuperAdmin NOT found")
            
    except Exception as e:
        print(f"Error during DB test: {e}")
