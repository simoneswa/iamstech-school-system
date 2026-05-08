import os
from sqlalchemy import create_engine, text
from werkzeug.security import generate_password_hash

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    db_path = os.path.join(os.path.abspath(os.getcwd()), 'instance', 'iamstech.db')
    DATABASE_URL = f'sqlite:///{db_path}'
else:
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

engine = create_engine(DATABASE_URL)
with engine.connect() as conn:
    sa_email = 'simoneswaraykeepitup@founder'
    res = conn.execute(text('SELECT id FROM "user" WHERE email = :email'), {'email': sa_email}).fetchone()
    
    if not res:
        print("Seeding SuperAdmin...")
        pwd_hash = generate_password_hash('2026Capt132005@')
        # Use simple SQL to avoid model dependency issues
        # Note: We need to specify all required columns. 
        # Since I've checked columns earlier, I know what's there.
        conn.execute(text('''
            INSERT INTO "user" (name, email, password, role, is_superadmin, registration_state, status, is_email_verified, must_change_password)
            VALUES (:name, :email, :password, :role, :is_sa, :state, :status, :verified, :must_change)
        '''), {
            'name': 'Lead Systems Developer',
            'email': sa_email,
            'password': pwd_hash,
            'role': 'SuperAdmin',
            'is_sa': True,
            'state': 'approved',
            'status': 'Approved',
            'verified': True,
            'must_change': False
        })
        conn.commit()
        print("SuperAdmin seeded successfully.")
    else:
        print("SuperAdmin already exists.")
        # Ensure state is correct
        conn.execute(text('UPDATE "user" SET registration_state = :state, is_superadmin = :is_sa, is_email_verified = :verified WHERE email = :email'), {
            'state': 'approved',
            'is_sa': True,
            'verified': True,
            'email': sa_email
        })
        conn.commit()
        print("SuperAdmin state updated.")
