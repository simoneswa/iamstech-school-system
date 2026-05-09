import os
from app import app, db
from sqlalchemy import text, inspect

def migrate_founder_schema():
    with app.app_context():
        print("--- STARTING ROBUST SCHEMA MIGRATION (V4) ---")
        
        # Check current columns in the 'founder' table
        inspector = inspect(db.engine)
        existing_cols = [c['name'] for c in inspector.get_columns('founder')]
        print(f"Existing columns in 'founder' table: {existing_cols}")
        
        # Required columns for the new CMS
        required_cols = {
            'bio': 'TEXT',
            'vision': 'TEXT',
            'mission': 'TEXT',
            'leadership_statement': 'TEXT'
        }
        
        # Also check developer table
        existing_dev_cols = [c['name'] for c in inspector.get_columns('developer')]
        dev_req_cols = {'bio': 'TEXT'}

        # Migration logic
        for col, col_type in required_cols.items():
            if col not in existing_cols:
                try:
                    print(f"Attempting to add {col} to founder...")
                    db.session.execute(text(f"ALTER TABLE founder ADD COLUMN {col} {col_type}"))
                    db.session.commit()
                    print(f"Successfully added column: {col}")
                except Exception as e:
                    db.session.rollback()
                    print(f"Failed to add {col}: {e}")
            else:
                print(f"Column {col} already exists in founder.")

        for col, col_type in dev_req_cols.items():
            if col not in existing_dev_cols:
                try:
                    print(f"Attempting to add {col} to developer...")
                    db.session.execute(text(f"ALTER TABLE developer ADD COLUMN {col} {col_type}"))
                    db.session.commit()
                    print(f"Successfully added column: {col}")
                except Exception as e:
                    db.session.rollback()
                    print(f"Failed to add {col}: {e}")
            else:
                print(f"Column {col} already exists in developer.")

        print("--- MIGRATION COMPLETE ---")

if __name__ == "__main__":
    migrate_founder_schema()
