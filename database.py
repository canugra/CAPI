import sqlite3
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_FILE = "quickmeal.db"

def get_db():
    conn = sqlite3.connect(DATABASE_FILE)
    # Enable WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    print("Initializing database...")
    with get_db() as conn:
        with open('schema.sql', 'r') as f:
            conn.executescript(f.read())
    print("Database initialized.")

if __name__ == '__main__':
    init_db()
