import os
from app import app, db
from sqlalchemy import text

def migrate():
    with app.app_context():
        print("Starting V3 database migration (Gamification)...")
        
        engine = db.engine
        
        # Add last_login_reward_date to user table
        try:
            with engine.connect() as conn:
                conn.execute(text('ALTER TABLE "user" ADD COLUMN last_login_reward_date DATE'))
                conn.commit()
                print("Added last_login_reward_date column.")
        except Exception as e:
            print(f"last_login_reward_date column might already exist: {e}")

        print("V3 Migration complete!")

if __name__ == "__main__":
    migrate()
