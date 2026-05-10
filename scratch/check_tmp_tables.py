import sqlite3
conn = sqlite3.connect('/tmp/iamstech.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
print(f"Tables in /tmp/iamstech.db: {cur.fetchall()}")
cur.close()
conn.close()
