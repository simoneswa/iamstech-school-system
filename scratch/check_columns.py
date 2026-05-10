import sqlite3
conn = sqlite3.connect('instance/iamstech.db')
cur = conn.cursor()
cur.execute("PRAGMA table_info(users);")
print(f"Columns in 'users': {cur.fetchall()}")
cur.close()
conn.close()
