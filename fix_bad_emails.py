import os
from app import app, db
from models import User

def fix_emails():
    with app.app_context():
        print("Starting Bad Email Cleanup Script...")
        
        users = User.query.filter(User.school_email.isnot(None)).all()
        fixed_count = 0
        
        for user in users:
            # Skip the true SuperAdmin
            if user.email == 'simoneswaraykeepitup@founder':
                continue
                
            old_email = user.school_email
            
            # Determine correct domain
            if user.role == "Teacher":
                domain = "faculty.iamtech.edu.lr"
            elif user.role in ["Admin", "SuperAdmin"]:
                domain = "admin.iamtech.edu.lr"
            else:
                domain = "student.iamtech.edu.lr"
                
            base_name = user.name.lower().replace(' ', '.')
            
            # Check if it's already perfectly correct
            if old_email.startswith(base_name) and old_email.endswith(domain) and "keepitup" not in old_email:
                continue
                
            # It's bad. Let's fix it.
            new_email = f"{base_name}@{domain}"
            counter = 1
            
            # Ensure unique
            while User.query.filter(User.school_email == new_email, User.id != user.id).first():
                new_email = f"{base_name}{counter}@{domain}"
                counter += 1
                
            user.school_email = new_email
            db.session.commit()
            print(f"Fixed: {old_email} -> {new_email}")
            fixed_count += 1
            
        print(f"Cleanup complete. {fixed_count} records corrected.")

if __name__ == "__main__":
    fix_emails()
