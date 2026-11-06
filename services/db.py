import sqlite3
from flask import g
from config import Config

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(Config.DB_PATH)
        g.db.row_factory = sqlite3.Row   # Access columns by name like a dict
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

def get_cursor(dictionary=True):
    """Get a cursor. The dictionary param is kept for compatibility but
    sqlite3.Row already provides dict-like access."""
    db = get_db()
    return db.cursor()

def commit_db():
    db = g.get('db')
    if db is not None:
        db.commit()

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()
