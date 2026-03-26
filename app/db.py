import os
import sqlite3

# Path to the SQLite database file, relative to the project root
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(_BASE_DIR, 'data', 'karo_cashflow.db')


def get_db():
    """Return a new SQLite connection to the database."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create all tables and seed initial data if they don't exist."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS transactions (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            entity       TEXT NOT NULL,
            doc_type     TEXT NOT NULL,
            doc_number   TEXT,
            date         DATE NOT NULL,
            due_date     DATE,
            amount       REAL NOT NULL,
            category     TEXT,
            counterparty TEXT,
            nip          TEXT,
            status       TEXT,
            is_internal  INTEGER DEFAULT 0,
            source       TEXT,
            synced_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS bank_statements (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            account      TEXT NOT NULL,
            date         DATE NOT NULL,
            amount       REAL NOT NULL,
            description  TEXT,
            balance      REAL,
            imported_at  DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ai_reports (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            period       TEXT NOT NULL,
            entity       TEXT NOT NULL,
            report_text  TEXT NOT NULL,
            tokens_used  INTEGER,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS ceo_notes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            period       TEXT,
            note         TEXT NOT NULL,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS category_rules (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            nip          TEXT,
            name_pattern TEXT,
            category     TEXT NOT NULL,
            is_internal  INTEGER DEFAULT 0
        );
    """)

    # Seed known category rules (INSERT OR IGNORE to avoid duplicates)
    cursor.executemany(
        "INSERT OR IGNORE INTO category_rules (nip, category, is_internal) VALUES (?, ?, ?)",
        [
            ('8911634021', 'WEWNETRZNE', 1),
            ('8911135105', 'WYPLATY_WLASCICIEL', 0),
            ('8133605829', 'PALIWO_FLOTEX', 0),
        ]
    )

    conn.commit()
    conn.close()
    print(f"[db] Database initialised at {DB_PATH}")
