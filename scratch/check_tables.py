import sqlite3
conn = sqlite3.connect('instance/iamstech.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
print(f"Tables: {cur.fetchall()}")
cur.close()
conn.close()
