from app import app, db
from models import User

with app.app_context():
    sa = User.query.filter_by(email='simoneswaraykeepitup@founder').first()
    if sa:
        print(f"SuperAdmin Found: {sa.email}")
        print(f"Role: {sa.role}")
        print(f"Registration State: {sa.registration_state}")
        print(f"Is SuperAdmin Flag: {sa.is_superadmin}")
        print(f"Created At: {sa.created_at}")
    else:
        print("CRITICAL: SuperAdmin account NOT FOUND!")
        # List all users to see what's there
        all_users = User.query.all()
        for u in all_users:
            print(f"User: {u.email}, Role: {u.role}, State: {u.registration_state}")
