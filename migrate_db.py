import os
from app import app, db
from sqlalchemy import text

def migrate():
    with app.app_context():
        print("Starting safe database migration (V1)...")
        engine = db.engine

        columns = [
            ('setup_token', 'VARCHAR(100)'),
            ('setup_token_expiration', 'TIMESTAMP'),
            ('is_superadmin', 'BOOLEAN DEFAULT FALSE'),
            ('must_change_password', 'BOOLEAN DEFAULT TRUE'),
            ('points', 'INTEGER DEFAULT 0'),
        ]
        for col_name, col_type in columns:
            try:
                with engine.connect() as conn:
                    conn.execute(text(f'ALTER TABLE "user" ADD COLUMN {col_name} {col_type}'))
                    conn.commit()
                    print(f"Added {col_name} column.")
            except Exception as e:
                print(f"{col_name} already exists or error: {e}")

        # Always call create_all to ensure all tables exist
        try:
            db.create_all()
            print("All tables ensured (create_all).")
        except Exception as e:
            print(f"create_all error: {e}")

        # Seed SuperAdmin
        try:
            from models import User
            from werkzeug.security import generate_password_hash
            sa = User.query.filter_by(is_superadmin=True).first()
            if not sa:
                su = User(
                    name='System Administrator',
                    email='simoneswaraykeepitup@founder',
                    password=generate_password_hash('2026Capt132005@'),
                    role='SuperAdmin',
                    status='Approved',
                    is_superadmin=True,
                    must_change_password=True,
                    points=0
                )
                db.session.add(su)
                db.session.commit()
                print("SuperAdmin seeded.")
            else:
                print("SuperAdmin already exists.")
        except Exception as e:
            print(f"SuperAdmin seeding error: {e}")

        print("V1 Migration complete!")

if __name__ == "__main__":
    migrate()
