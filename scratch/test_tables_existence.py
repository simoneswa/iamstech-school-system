
from app import app, db
from sqlalchemy import inspect

with app.app_context():
    inspector = inspect(db.engine)
    tables = inspector.get_table_names()
    print(f"Tables in DB: {tables}")
    
    if 'notification' not in tables:
        print("MISSING: 'notification' table is not in the database!")
    else:
        print("SUCCESS: 'notification' table exists.")
