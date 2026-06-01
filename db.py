"""
Database layer using SQLite.

Privacy by design:
- Sessions store no participant identifiers.
- Answers store only answer text and a submission timestamp.
- No IP addresses, user agents, or cookies are persisted here.
"""
import sqlite3
import os
from typing import Optional

DB_PATH = os.environ.get("TWS_DB_PATH", "tws.db")


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                slug             TEXT    PRIMARY KEY,
                question         TEXT    NOT NULL,
                admin_token      TEXT    NOT NULL,
                status           TEXT    NOT NULL DEFAULT 'waiting',
                timer_seconds    INTEGER NOT NULL,
                timer_started_at REAL,
                created_at       REAL    NOT NULL,
                closed_at        REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS answers (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_slug TEXT    NOT NULL,
                answer_text  TEXT    NOT NULL,
                submitted_at REAL    NOT NULL,
                FOREIGN KEY (session_slug) REFERENCES sessions(slug)
            )
        """)
        conn.commit()


def get_session(slug: str) -> Optional[sqlite3.Row]:
    with _conn() as conn:
        return conn.execute(
            "SELECT * FROM sessions WHERE slug = ?", (slug,)
        ).fetchone()


def create_session(
    slug: str,
    question: str,
    admin_token: str,
    timer_seconds: int,
    created_at: float,
) -> None:
    with _conn() as conn:
        conn.execute(
            """INSERT INTO sessions
               (slug, question, admin_token, status, timer_seconds, created_at)
               VALUES (?, ?, ?, 'waiting', ?, ?)""",
            (slug, question, admin_token, timer_seconds, created_at),
        )
        conn.commit()


def start_timer(slug: str, started_at: float) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE sessions SET status='thinking', timer_started_at=? WHERE slug=?",
            (started_at, slug),
        )
        conn.commit()


def set_status(slug: str, status: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE sessions SET status=? WHERE slug=?",
            (status, slug),
        )
        conn.commit()


def close_session(slug: str, closed_at: float) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE sessions SET status='closed', closed_at=? WHERE slug=?",
            (closed_at, slug),
        )
        conn.commit()


def add_answer(session_slug: str, answer_text: str, submitted_at: float) -> None:
    # Privacy: only text + timestamp stored; no participant identifier.
    with _conn() as conn:
        conn.execute(
            "INSERT INTO answers (session_slug, answer_text, submitted_at) VALUES (?, ?, ?)",
            (session_slug, answer_text, submitted_at),
        )
        conn.commit()


def count_answers(session_slug: str) -> int:
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM answers WHERE session_slug=?",
            (session_slug,),
        ).fetchone()
        return row[0] if row else 0


def get_answers(session_slug: str) -> list:
    with _conn() as conn:
        return conn.execute(
            "SELECT answer_text, submitted_at FROM answers"
            " WHERE session_slug=? ORDER BY submitted_at",
            (session_slug,),
        ).fetchall()


def get_random_answer(session_slug: str) -> Optional[sqlite3.Row]:
    with _conn() as conn:
        return conn.execute(
            "SELECT answer_text FROM answers"
            " WHERE session_slug=? ORDER BY RANDOM() LIMIT 1",
            (session_slug,),
        ).fetchone()
