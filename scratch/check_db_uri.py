from app import app, db
print(f"DB URI: {app.config['SQLALCHEMY_DATABASE_URI']}")

from models import User
with app.app_context():
    try:
        users = User.query.all()
        print(f"Total Users: {len(users)}")
    except Exception as e:
        print(f"Error: {e}")
