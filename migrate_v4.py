import os
from app import app, db
from models import Founder

def migrate():
    with app.app_context():
        print("Starting V4 database migration (Founder Seed)...")
        
        engine = db.engine
        from sqlalchemy import text
        
        # Ensure Founder table has title and message columns
        columns = [
            ('title', 'VARCHAR(100) DEFAULT \'Founder & CEO\''),
            ('message', 'TEXT'),
            ('bio', 'TEXT')
        ]
        for col_name, col_type in columns:
            try:
                with engine.connect() as conn:
                    conn.execute(text(f'ALTER TABLE founder ADD COLUMN {col_name} {col_type}'))
                    conn.commit()
                    print(f"Added {col_name} to Founder.")
            except Exception as e:
                print(f"Founder {col_name} already exists or error: {e}")
                
        # Check if founder already exists
        founder = Founder.query.first()
        if not founder:
            founder = Founder(
                name="Mr. Benaiah Kanawa",
                title="Founder & CEO",
                message="Mr. Benaiah Kanawa is committed to empowering the next generation of Liberian professionals through practical technology and business education. His vision for IAMSTECH LIBERIA focuses on innovation, integrity, leadership, and preparing students for success in the modern digital economy.",
                image_path="img/founder.jpg"
            )
            db.session.add(founder)
        else:
            founder.name = "Mr. Benaiah Kanawa"
            founder.title = "Founder & CEO"
            founder.message = "Mr. Benaiah Kanawa is committed to empowering the next generation of Liberian professionals through practical technology and business education. His vision for IAMSTECH LIBERIA focuses on innovation, integrity, leadership, and preparing students for success in the modern digital economy."
            founder.image_path = "img/founder.jpg"
            
        db.session.commit()
        print("Founder seeded successfully.")
        print("V4 Migration complete!")

if __name__ == "__main__":
    migrate()
