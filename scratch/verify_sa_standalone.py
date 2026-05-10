import os
from sqlalchemy import create_engine, text

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
    res = conn.execute(text('SELECT email, role, registration_state, is_superadmin, created_at FROM "user" WHERE email = :email'), {'email': sa_email}).fetchone()
    
    if res:
        print(f"SuperAdmin Found: {res[0]}")
        print(f"Role: {res[1]}")
        print(f"Registration State: {res[2]}")
        print(f"Is SuperAdmin Flag: {res[3]}")
        print(f"Created At: {res[4]}")
    else:
        print("CRITICAL: SuperAdmin account NOT FOUND!")
        all_res = conn.execute(text('SELECT email, role, registration_state FROM "user"')).fetchall()
        for r in all_res:
            print(f"User: {r[0]}, Role: {r[1]}, State: {r[2]}")
