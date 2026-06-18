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
from datetime import datetime
from pathlib import Path
from typing import Optional

import psycopg2
import psycopg2.extras
import pandas as pd
from dotenv import load_dotenv
from fastapi.responses import FileResponse

load_dotenv()

DATA_DIR = Path("data")
os.makedirs(DATA_DIR, exist_ok=True)


# ─────────────────────────────────────────────
#  URL cache
# ─────────────────────────────────────────────

class _Cache:
    """
    PostgreSQL-backed URL cache.

    Each row is one key (URL or derived hash) → JSON-serialised results list.
    Per-URL for: general, ZocDoc listings, ZocDoc profiles, ZoomInfo.
    Per-request-hash for: Indian Stocks (params, not a single URL).
    """
    _DB_URL: str = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/vm_tools_cache")
    _conn: Optional[psycopg2.extensions.connection] = None

    @classmethod
    def _connect(cls) -> psycopg2.extensions.connection:
        if cls._conn is None or cls._conn.closed != 0:
            cls._conn = psycopg2.connect(cls._DB_URL)
            with cls._conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS cache (
                        key        TEXT PRIMARY KEY,
                        scraped_at TEXT NOT NULL,
                        results    JSONB NOT NULL
                    )
                """)
            cls._conn.commit()
        return cls._conn

    @classmethod
    def get(cls, key: str) -> Optional[list]:
        """Return cached results for *key*, or None on a miss."""
        with cls._connect().cursor() as cur:
            cur.execute("SELECT results FROM cache WHERE key = %s", (key,))
            row = cur.fetchone()
        if row is None:
            return None
        try:
            return json.loads(row[0]) if isinstance(row[0], str) else row[0]
        except (json.JSONDecodeError, TypeError):
            return None

    @classmethod
    def set(cls, key: str, results: list) -> None:
        """Store *results* under *key* (upsert)."""
        try:
            conn = cls._connect()
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO cache (key, scraped_at, results)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (key) DO UPDATE
                        SET scraped_at = EXCLUDED.scraped_at,
                            results    = EXCLUDED.results
                    """,
                    (key, datetime.now().isoformat(timespec="seconds"), json.dumps(results, ensure_ascii=False)),
                )
            conn.commit()
        except psycopg2.Error as exc:
            print(f"[cache] write failed: {exc}")

    @classmethod
    def delete(cls, key: str) -> bool:
        """Delete one entry. Returns True if it existed."""
        conn = cls._connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cache WHERE key = %s", (key,))
            deleted = cur.rowcount
        conn.commit()
        return deleted > 0

    @classmethod
    def clear_all(cls) -> int:
        """Delete every entry. Returns the number of rows removed."""
        conn = cls._connect()
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cache")
            deleted = cur.rowcount
        conn.commit()
        return deleted

    @classmethod
    def stats(cls) -> dict:
        """Return entry count and table size."""
        conn = cls._connect()
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM cache")
            count = cur.fetchone()[0]
            cur.execute("SELECT pg_total_relation_size('cache')")
            size_bytes = cur.fetchone()[0]
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
