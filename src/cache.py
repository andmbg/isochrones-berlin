import json
import os
import sqlite3
from contextlib import contextmanager

_DB_PATH = os.getenv("CACHE_DB", "data/cache.db")


@contextmanager
def _connect():
    con = sqlite3.connect(_DB_PATH)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS stop_cache (
            stop_id   TEXT PRIMARY KEY,
            stops     TEXT NOT NULL,
            cached_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    try:
        yield con
    finally:
        con.close()


def get(stop_id: str) -> list[dict] | None:
    """Return cached stops for stop_id, or None if not cached."""
    with _connect() as con:
        row = con.execute(
            "SELECT stops FROM stop_cache WHERE stop_id = ?", (stop_id,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def set(stop_id: str, stops: list[dict]) -> None:
    """Store stops for stop_id in the cache."""
    with _connect() as con:
        con.execute(
            """
            INSERT INTO stop_cache (stop_id, stops)
            VALUES (?, ?)
            ON CONFLICT(stop_id) DO UPDATE SET stops = excluded.stops,
                                               cached_at = datetime('now')
            """,
            (stop_id, json.dumps(stops)),
        )
        con.commit()
