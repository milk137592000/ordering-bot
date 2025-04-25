#!/usr/bin/env python3
import sqlite3, os
db_path = "db2.sqlite3"
print(f"Database exists: {os.path.exists(db_path)}")
if os.path.exists(db_path):
    print(f"File size: {os.path.getsize(db_path)} bytes")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type=\"table\"")
    tables = cursor.fetchall()
    print(f"Tables: {tables}")
    if not tables:
        print("DB needs to be initialized")
    conn.close()
