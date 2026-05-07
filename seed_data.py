from app import app, db
from models import User, Activity, Course, Founder, Developer, Announcement
from werkzeug.security import generate_password_hash

def seed():
    with app.app_context():
        # Drop and recreate for schema changes
        db.drop_all()
        db.create_all()

        # Seed Admin
        admin = User(
            name='System Administrator',
            email='admin@iamstech.com',
            school_email='admin@iamstech.edu',
            password=generate_password_hash('2026iloveiamstech'),
            role='Admin',
            status='Approved',
            must_change_password=False
        )
        db.session.add(admin)

        # Seed Sample Teacher
        teacher = User(
            name='James Kollie',
            email='james@example.com',
            school_email='james.kollie@students.iamstech.edu', # Simulating school email
            password=generate_password_hash('teacher123'),
            role='Teacher',
            status='Approved',
            must_change_password=False
        )
        db.session.add(teacher)

        # Seed Founder
        f = Founder(
            name='Benaiah Kanawa',
            title='Founder & CEO',
            message='Building the future of Liberia through advanced technological training.',
            image_path='https://via.placeholder.com/200'
        )
        db.session.add(f)

        # Seed Developer
        d = Developer(
            name='IAMSTECH Dev Group',
            role='Senior Systems Architects',
            description='Crafting digital experiences for educational transformation.',
            image_path='https://via.placeholder.com/200'
        )
        db.session.add(d)

        # Seed Announcement
        a = Announcement(
            title='University Portal Upgraded',
            message='Welcome to the official IAMSTECH University Academic Portal. Digital IDs and assignment modules are now live!',
            posted_by=1
        )
        db.session.add(a)

        db.session.commit()
        print("University Portal Seeded Successfully!")

if __name__ == '__main__':
    seed()
