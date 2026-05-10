import os
from sqlalchemy import create_engine, inspect

DATABASE_URL = os.getenv('DATABASE_URL')
if not DATABASE_URL:
    db_path = os.path.join(os.path.abspath(os.getcwd()), 'instance', 'iamstech.db')
    DATABASE_URL = f'sqlite:///{db_path}'
else:
    if DATABASE_URL.startswith('postgres://'):
        DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

engine = create_engine(DATABASE_URL)
columns = [c['name'] for c in inspect(engine).get_columns('user')]
print(columns)
