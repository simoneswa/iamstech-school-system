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
    users = conn.execute(text('SELECT email, is_superadmin, role, registration_state FROM "user"')).fetchall()
    for u in users:
        print(f"User: {u[0]}, SuperAdmin: {u[1]}, Role: {u[2]}, State: {u[3]}")
