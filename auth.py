"""
auth.py
--------
Handles user accounts: checking login, changing password, listing operators.
Uses a small SQLite database file (database.db) that is created
automatically the first time the app runs.
"""

import os
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")

# Default soldier accounts created the first time the app runs.
# PIN = 1234 for all — each operator changes their own PIN after first login.
DEFAULT_SOLDIERS = ["J1", "J2", "J3", "J4"]
DEFAULT_PIN = "1234"


def is_valid_pin(pin):
    """A valid PIN is exactly 4 digits, e.g. '4821'."""
    return isinstance(pin, str) and pin.isdigit() and len(pin) == 4


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Creates the users table and seeds default soldier accounts if needed."""
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        )
        """
    )
    conn.commit()

    # Seed each default soldier if they don't already have an account
    for soldier_id in DEFAULT_SOLDIERS:
        existing = conn.execute(
            "SELECT COUNT(*) AS c FROM users WHERE username = ?", (soldier_id,)
        ).fetchone()
        if existing["c"] == 0:
            conn.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                (soldier_id, generate_password_hash(DEFAULT_PIN), "user"),
            )
    conn.commit()
    conn.close()


def get_all_usernames():
    """Returns a sorted list of all operator usernames (for the login dropdown)."""
    conn = get_db()
    rows = conn.execute(
        "SELECT username FROM users WHERE role = 'user' ORDER BY username"
    ).fetchall()
    conn.close()
    return [row["username"] for row in rows]


def verify_login(username, password):
    """Returns the user row (as a dict) if username/password match, else None."""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()
    conn.close()

    if row and check_password_hash(row["password_hash"], password):
        return dict(row)
    return None


def change_password(username, old_password, new_password):
    """Changes the password only if old_password is correct. Returns (success, message)."""
    user = verify_login(username, old_password)
    if not user:
        return False, "Current PIN is incorrect."

    conn = get_db()
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE username = ?",
        (generate_password_hash(new_password), username),
    )
    conn.commit()
    conn.close()
    return True, "PIN updated successfully."
