import os
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db
from models import Developer

def seed_developer():
    with app.app_context():
        print("Seeding Developer Simone Swaray...")
        dev = Developer.query.first() or Developer()
        dev.name = "Simone Swaray"
        dev.role = "Systems Architect & Developer"
        dev.description = "Informatics Engineering student specializing in Networking. A visionary Liberian professional dedicated to bridging the technological gap through institutional digital solutions."
        dev.bio = "Dedicated to crafting premium, industry-grade platforms that empower the next generation of Liberian technology leaders."
        
        db.session.add(dev)
        db.session.commit()
        print("Developer Simone Swaray seeded successfully.")

if __name__ == "__main__":
    seed_developer()
