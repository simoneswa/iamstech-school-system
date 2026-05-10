from app import app, db
with app.app_context():
    db.create_all()
    print("db.create_all() finished.")

import sqlite3
conn = sqlite3.connect('instance/iamstech.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
print(f"Tables after create_all: {cur.fetchall()}")
cur.close()
conn.close()
