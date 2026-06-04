"""
Database layer using SQLite.

Privacy by design:
- Sessions store no participant identifiers.
- Answers store only answer text and a submission timestamp.
- No IP addresses, user agents, or cookies are persisted here.
"""
import random
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
                slug                 TEXT    PRIMARY KEY,
                question             TEXT    NOT NULL,
                admin_token          TEXT    NOT NULL,
                status               TEXT    NOT NULL DEFAULT 'waiting',
                timer_seconds        INTEGER NOT NULL,
                timer_started_at     REAL,
                created_at           REAL    NOT NULL,
                closed_at            REAL,
                distribution_counter INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS answers (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                session_slug     TEXT    NOT NULL,
                answer_text      TEXT    NOT NULL,
                submitted_at     REAL    NOT NULL,
                distribution_idx INTEGER,
                FOREIGN KEY (session_slug) REFERENCES sessions(slug)
            )
        """)
        # Migrate existing databases that predate the distribution columns.
        for stmt in (
            "ALTER TABLE sessions ADD COLUMN distribution_counter INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE answers  ADD COLUMN distribution_idx INTEGER",
        ):
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError:
                pass  # column already exists
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
    """
    Close the session and assign a shuffled distribution_idx to every answer.

    The shuffle happens here, at close time, so the order is fixed once and
    distribution_counter can be incremented atomically per retrieval request,
    guaranteeing each answer is served to exactly one participant on the first
    pass (wrapping around only if more people request than submitted answers).
    """
    with _conn() as conn:
        rows = conn.execute(
            "SELECT id FROM answers WHERE session_slug = ? ORDER BY submitted_at",
            (slug,),
        ).fetchall()
        ids = [r[0] for r in rows]
        random.shuffle(ids)
        for idx, answer_id in enumerate(ids):
            conn.execute(
                "UPDATE answers SET distribution_idx = ? WHERE id = ?",
                (idx, answer_id),
            )
        conn.execute(
            "UPDATE sessions SET status='closed', closed_at=?, distribution_counter=0 WHERE slug=?",
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


def get_next_answer(session_slug: str) -> Optional[sqlite3.Row]:
    """
    Return the next answer in the pre-shuffled distribution sequence.

    Atomically increments distribution_counter and maps it to a
    distribution_idx so each answer is served exactly once on the first
    pass.  If more participants request than submitted answers the sequence
    wraps, so no one is ever left empty-handed.
    """
    with _conn() as conn:
        conn.execute(
            "UPDATE sessions SET distribution_counter = distribution_counter + 1 WHERE slug = ?",
            (session_slug,),
        )
        row = conn.execute(
            "SELECT distribution_counter FROM sessions WHERE slug = ?",
            (session_slug,),
        ).fetchone()
        counter = row[0] - 1  # 0-indexed slot for this caller

        count = conn.execute(
            "SELECT COUNT(*) FROM answers WHERE session_slug = ?",
            (session_slug,),
        ).fetchone()[0]

        if count == 0:
            return None

        idx = counter % count
        return conn.execute(
            "SELECT answer_text FROM answers"
            " WHERE session_slug = ? AND distribution_idx = ?",
            (session_slug, idx),
        ).fetchone()
