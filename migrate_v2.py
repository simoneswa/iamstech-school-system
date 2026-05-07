import os
from app import app, db
from sqlalchemy import text

def migrate():
    with app.app_context():
        print("Starting V2 safe database migration...")
        
        engine = db.engine
        
        # Add new columns to user table safely
        columns = [
            ('is_suspended', 'BOOLEAN DEFAULT FALSE'),
            ('suspension_reason', 'TEXT'),
            ('reset_token', 'VARCHAR(100)'),
            ('reset_token_expiration', 'TIMESTAMP')
        ]
        
        for col_name, col_type in columns:
            try:
                with engine.connect() as conn:
                    conn.execute(text(f'ALTER TABLE "user" ADD COLUMN {col_name} {col_type}'))
                    conn.commit()
                    print(f"Added {col_name} column.")
            except Exception as e:
                print(f"{col_name} column might already exist: {e}")

        # Ensure all new tables (Notification, GlobalAlert, SystemAuditLog) are created
        try:
            db.create_all()
            print("Ensured all new tables are created.")
        except Exception as e:
            print(f"Error creating new tables: {e}")
            
        print("V2 Migration complete!")

if __name__ == "__main__":
    migrate()
