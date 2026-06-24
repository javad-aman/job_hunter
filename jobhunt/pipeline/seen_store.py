"""SQLite-backed store of previously seen job URLs.

Idempotent runs: on each execution we filter out any URL that already exists
in the DB, then insert the new ones after scoring so the next run skips them.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from jobhunt.models import Posting


class SeenStore:
    def __init__(self, db_path: Path) -> None:
        self._path = db_path
        self._conn = sqlite3.connect(str(db_path))
        self._create_table()

    def _create_table(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seen_jobs (
                url     TEXT PRIMARY KEY,
                title   TEXT,
                company TEXT,
                seen_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        self._conn.commit()

    def filter_new(self, postings: list[Posting]) -> list[Posting]:
        """Return only postings whose URL has not been seen before."""
        if not postings:
            return []
        urls = [p.dedup_key() for p in postings]
        placeholders = ",".join("?" * len(urls))
        rows = self._conn.execute(
            f"SELECT url FROM seen_jobs WHERE url IN ({placeholders})", urls
        ).fetchall()
        seen = {row[0] for row in rows}
        return [p for p in postings if p.dedup_key() not in seen]

    def mark_seen(self, postings: list[Posting]) -> None:
        """Persist URLs so future runs skip them."""
        self._conn.executemany(
            "INSERT OR IGNORE INTO seen_jobs (url, title, company) VALUES (?, ?, ?)",
            [(p.dedup_key(), p.title, p.company) for p in postings],
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SeenStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
