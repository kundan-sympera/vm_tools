"""
shared.py — State and utilities shared across all router modules.

Exports:
  DATA_DIR        Path to output directory
  _Cache          URL-keyed persistent cache
  _stocks_key()   Cache key for Indian-Stocks requests
  _ts()           Timestamp string
  _file_response()  FastAPI FileResponse helper
  _respond()      Save results list → CSV/JSON FileResponse
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from fastapi.responses import FileResponse

DATA_DIR = Path("data")
os.makedirs(DATA_DIR, exist_ok=True)


# ─────────────────────────────────────────────
#  URL cache
# ─────────────────────────────────────────────

class _Cache:
    """
    SQLite-backed URL cache stored at data/scraper_cache.db.

    Each row is one key (URL or derived hash) → JSON-serialised results list.
    Reads and writes touch only the single matching row — no full-file I/O
    regardless of how many entries are stored.

    Per-URL for: general, ZocDoc listings, ZocDoc profiles, ZoomInfo.
    Per-request-hash for: Indian Stocks (params, not a single URL).
    """
    _DB_PATH: Path = DATA_DIR / "scraper_cache.db"
    _conn: Optional[sqlite3.Connection] = None

    @classmethod
    def _connect(cls) -> sqlite3.Connection:
        if cls._conn is None:
            cls._conn = sqlite3.connect(str(cls._DB_PATH), check_same_thread=False)
            cls._conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key        TEXT PRIMARY KEY,
                    scraped_at TEXT NOT NULL,
                    results    TEXT NOT NULL
                )
            """)
            cls._conn.commit()
        return cls._conn

    @classmethod
    def get(cls, key: str) -> Optional[list]:
        """Return cached results for *key*, or None on a miss."""
        row = cls._connect().execute(
            "SELECT results FROM cache WHERE key = ?", (key,)
        ).fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return None

    @classmethod
    def set(cls, key: str, results: list) -> None:
        """Store *results* under *key* (upsert)."""
        try:
            conn = cls._connect()
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, scraped_at, results) VALUES (?, ?, ?)",
                (key, datetime.now().isoformat(timespec="seconds"), json.dumps(results, ensure_ascii=False)),
            )
            conn.commit()
        except sqlite3.Error as exc:
            print(f"[cache] write failed: {exc}")

    @classmethod
    def delete(cls, key: str) -> bool:
        """Delete one entry. Returns True if it existed."""
        conn = cls._connect()
        cursor = conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        conn.commit()
        return cursor.rowcount > 0

    @classmethod
    def clear_all(cls) -> int:
        """Delete every entry. Returns the number of rows removed."""
        conn = cls._connect()
        cursor = conn.execute("DELETE FROM cache")
        conn.commit()
        return cursor.rowcount

    @classmethod
    def stats(cls) -> dict:
        """Return entry count and DB file size."""
        conn = cls._connect()
        count = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
        size_bytes = cls._DB_PATH.stat().st_size if cls._DB_PATH.exists() else 0
        return {"entries": count, "db_size_kb": round(size_bytes / 1024, 1)}


# ─────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────

def _stocks_key(sectors: list, sections: list, periods: list) -> str:
    """Stable cache key for an Indian-Stocks request (hash of sorted params)."""
    parts = sorted(sectors) + ["||"] + sorted(sections) + ["||"] + sorted(periods)
    return "stocks:" + hashlib.md5("|".join(parts).encode()).hexdigest()


def _ts() -> str:
    return datetime.now().strftime("%Y_%m_%d_%H_%M_%S")


def _file_response(path: str, media_type: str, filename: str) -> FileResponse:
    return FileResponse(path=path, media_type=media_type, filename=filename)


def _respond(results: list, output_format: str, stem: str):
    """Save *results* list and return a FileResponse (CSV or JSON)."""
    ts = _ts()
    output_format = output_format.lower()

    if output_format == "json":
        fpath = str(DATA_DIR / f"{stem}_{ts}.json")
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(
                {"scraped_at": ts, "total": len(results), "results": results},
                f, indent=2, ensure_ascii=False,
            )
        return _file_response(fpath, "application/json", f"{stem}_{ts}.json")

    fpath = str(DATA_DIR / f"{stem}_{ts}.csv")
    pd.DataFrame(results).to_csv(fpath, index=False)
    return _file_response(fpath, "text/csv", f"{stem}_{ts}.csv")
