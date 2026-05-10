import os
import sys
from sqlalchemy import create_engine, inspect, text
from app import app, db

def column_exists(table_name, column_name, engine):
    inspector = inspect(engine)
    if not inspector.has_table(table_name):
        return False
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def upgrade():
    print("Starting OTP Status Migration (v7)...")
    with app.app_context():
        engine = db.engine
        
        with engine.connect() as connection:
            if not column_exists('user', 'otp_email_status', engine):
                print("Adding otp_email_status column to user table...")
                try:
                    connection.execute(text('ALTER TABLE "user" ADD COLUMN otp_email_status VARCHAR(20) DEFAULT \'pending\''))
                    connection.commit()
                    print("Successfully added otp_email_status column.")
                except Exception as e:
                    print(f"Error adding column: {e}")
                    connection.rollback()
            else:
                print("otp_email_status column already exists.")
                
        print("Migration complete!")

if __name__ == "__main__":
    upgrade()
