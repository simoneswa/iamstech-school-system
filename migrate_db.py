import os
from app import app, db
from sqlalchemy import text

def migrate():
    with app.app_context():
        print("Starting safe database migration...")
        
        engine = db.engine
        
        # 1. Add setup_token to User
        try:
            with engine.connect() as conn:
                conn.execute(text('ALTER TABLE "user" ADD COLUMN setup_token VARCHAR(100)'))
                conn.commit()
                print("Added setup_token column.")
        except Exception as e:
            print(f"setup_token column might already exist: {e}")

        # 2. Add setup_token_expiration to User
        try:
            with engine.connect() as conn:
                conn.execute(text('ALTER TABLE "user" ADD COLUMN setup_token_expiration DATETIME'))
                conn.commit()
                print("Added setup_token_expiration column.")
        except Exception as e:
            # PostgreSQL uses TIMESTAMP instead of DATETIME in raw sql sometimes, but let's try
            try:
                with engine.connect() as conn:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN setup_token_expiration TIMESTAMP'))
                    conn.commit()
                    print("Added setup_token_expiration column (PostgreSQL).")
            except Exception as e2:
                print(f"setup_token_expiration column might already exist: {e2}")

        # 3. Add is_superadmin to User
        try:
            with engine.connect() as conn:
                conn.execute(text('ALTER TABLE "user" ADD COLUMN is_superadmin BOOLEAN DEFAULT FALSE'))
                conn.commit()
                print("Added is_superadmin column.")
        except Exception as e:
            print(f"is_superadmin column might already exist: {e}")

        # 4. Create new tables (AdminAuditLog)
        try:
            db.create_all()
            print("Ensured all new tables are created.")
        except Exception as e:
            print(f"Error creating new tables: {e}")
            
        print("Migration complete!")

if __name__ == "__main__":
    migrate()
