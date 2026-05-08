import os
from sqlalchemy import text
from werkzeug.security import generate_password_hash

def seed_sa_func():
    from app import db
    engine = db.engine
    with engine.connect() as conn:
        sa_email = 'simoneswaraykeepitup@founder'
        try:
            res = conn.execute(text('SELECT id FROM "user" WHERE email = :email'), {'email': sa_email}).fetchone()
            
            if not res:
                print("Seeding SuperAdmin...")
                pwd_hash = generate_password_hash('2026Capt132005@')
                conn.execute(text('''
                    INSERT INTO "user" (name, email, password, role, is_superadmin, registration_state, is_email_verified, must_change_password)
                    VALUES (:name, :email, :password, :role, :is_sa, :state, :verified, :must_change)
                '''), {
                    'name': 'Lead Systems Developer',
                    'email': sa_email,
                    'password': pwd_hash,
                    'role': 'SuperAdmin',
                    'is_sa': True,
                    'state': 'approved',
                    'verified': True,
                    'must_change': False
                })
                conn.commit()
                print("SuperAdmin seeded successfully.")
            else:
                print("SuperAdmin already exists.")
                conn.execute(text('UPDATE "user" SET registration_state = :state, is_superadmin = :is_sa, is_email_verified = :verified WHERE email = :email'), {
                    'state': 'approved',
                    'is_sa': True,
                    'verified': True,
                    'email': sa_email
                })
                conn.commit()
                print("SuperAdmin state updated.")
        except Exception as e:
            print(f"Seeding failed: {e}")
