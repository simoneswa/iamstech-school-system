import os
import sys

# Add parent directory to path to find app and models
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, db
from models import Founder, Developer
from sqlalchemy import text

def fix_schema():
    with app.app_context():
        print("Starting schema migration...")
        
        # Determine if we are using SQLite or PostgreSQL
        is_sqlite = db.engine.url.drivername == 'sqlite'
        
        # Columns to add to Founder
        founder_cols = {
            'bio': 'TEXT',
            'vision': 'TEXT',
            'mission': 'TEXT',
            'leadership_statement': 'TEXT'
        }
        
        # Columns to add to Developer
        dev_cols = {
            'bio': 'TEXT'
        }
        
        # Add columns to Founder
        for col, col_type in founder_cols.items():
            try:
                db.session.execute(text(f"ALTER TABLE founder ADD COLUMN {col} {col_type}"))
                db.session.commit()
                print(f"Added column {col} to founder table.")
            except Exception as e:
                db.session.rollback()
                print(f"Column {col} might already exist or error: {e}")
                
        # Add columns to Developer
        for col, col_type in dev_cols.items():
            try:
                db.session.execute(text(f"ALTER TABLE developer ADD COLUMN {col} {col_type}"))
                db.session.commit()
                print(f"Added column {col} to developer table.")
            except Exception as e:
                db.session.rollback()
                print(f"Column {col} might already exist or error: {e}")

        # Seed Founder info for Beniah Success Kanawa
        founder = Founder.query.first()
        if not founder:
            founder = Founder(name="Beniah Success Kanawa")
            
        founder.name = "Beniah Success Kanawa"
        founder.title = "Founder & CEO"
        founder.vision = "To be Liberia's premier gateway for industry-ready vocational and technical expertise, bridging the digital divide through accessible, world-class education."
        founder.mission = "To empower the next generation of Liberian professionals with hands-on technical skills, innovative thinking, and institutional excellence."
        founder.leadership_statement = "At IAMSTECH, we don't just teach technology; we cultivate the architects of Liberia's digital future. Our commitment is to transform every student into a highly skilled, industry-ready professional capable of leading in a global economy."
        founder.bio = "Beniah Success Kanawa is a visionary leader and educational pioneer dedicated to transforming Liberia's technological landscape. With a background in institutional development and technology management, he founded IAMSTECH to provide a professional haven for vocational excellence."
        
        db.session.add(founder)
        db.session.commit()
        print("Founder 'Beniah Success Kanawa' seeded successfully.")

if __name__ == "__main__":
    fix_schema()
