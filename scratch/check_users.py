from app import app, db
from models import User

with app.app_context():
    users = User.query.all()
    print(f"Total Users: {len(users)}")
    for u in users:
        print(f"Email: {u.email}, Status: {u.status}, Verified: {u.is_email_verified}, Role: {u.role}")
