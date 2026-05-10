import os
path = "/tmp/iamstech.db"
print(f"Path: {path}")
print(f"Exists: {os.path.exists(path)}")
if os.path.exists(path):
    print(f"Size: {os.path.getsize(path)}")
