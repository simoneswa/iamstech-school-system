from app import app, db
from sqlalchemy import inspect
with app.app_context():
    columns = [c['name'] for c in inspect(db.engine).get_columns('user')]
    print(columns)
