"""
utils/db.py — Shared PostgreSQL helpers.

Public API
----------
get_conn()
ensure_company_table(conn)
get_details(conn, pool_id_link)         -> str | None
save_details(conn, pool_id, pool_id_link, details)
get_extracted_company(conn, pool_id_link) -> dict | None

# Per-scraper caches (each owns its own table)
CACHE_GENERAL, CACHE_ZOCDOC, CACHE_ZOCDOC_PROFILE, CACHE_ZOOMINFO, CACHE_STOCKS
ensure_cache_table(conn, table)
cache_get(conn, table, key)             -> list | None
cache_set(conn, table, key, results)
stocks_cache_key(sectors, sections, periods) -> str
cache_stats(conn)                       -> dict
cache_clear(conn, table)                -> int
"""

import hashlib
import json
import os

import psycopg2
import psycopg2.extras

_DEFAULT_URL = "postgresql://postgres:postgres@localhost:5432/vm_tools_cache"

# ── Table name constants ──────────────────────────────────────────────────────

CACHE_GENERAL        = "cache_general"
CACHE_ZOCDOC         = "cache_zocdoc"
CACHE_ZOCDOC_PROFILE = "cache_zocdoc_profile"
CACHE_ZOOMINFO       = "cache_zoominfo"
CACHE_STOCKS         = "cache_stocks"

ALL_CACHE_TABLES = [CACHE_GENERAL, CACHE_ZOCDOC, CACHE_ZOCDOC_PROFILE, CACHE_ZOOMINFO, CACHE_STOCKS]

_CREATE_COMPANY_TABLE = """
    CREATE TABLE IF NOT EXISTS company_information (
        id           SERIAL PRIMARY KEY,
        pool_id      TEXT,
        pool_id_link TEXT NOT NULL,
        name_check   BOOLEAN,
        website      TEXT,
        founded_year TEXT,
        revenue      TEXT,
        ownership    TEXT,
        employees    TEXT,
        details      TEXT,
        created_at   TIMESTAMP DEFAULT NOW()
    )
"""

_MIN_DETAIL_LEN = 100


# ── Connection ────────────────────────────────────────────────────────────────

def get_conn() -> psycopg2.extensions.connection:
    url = os.getenv("DATABASE_URL", _DEFAULT_URL)
    return psycopg2.connect(url)


# ── company_information helpers ───────────────────────────────────────────────

def ensure_company_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(_CREATE_COMPANY_TABLE)
    conn.commit()


def get_details(conn, pool_id_link: str) -> str | None:
    """Return cached grok details if >= 100 chars, else None."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT details FROM company_information WHERE pool_id_link = %s ORDER BY created_at DESC LIMIT 1",
            (pool_id_link,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    details = row[0] or ""
    return details if len(details) >= _MIN_DETAIL_LEN else None


def save_details(conn, pool_id: str, pool_id_link: str, details: str) -> None:
    """Update existing row for pool_id_link, or insert if absent."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM company_information WHERE pool_id_link = %s ORDER BY created_at DESC LIMIT 1",
            (pool_id_link,),
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE company_information SET details = %s, created_at = NOW() WHERE id = %s",
                (details, row[0]),
            )
        else:
            cur.execute(
                "INSERT INTO company_information (pool_id, pool_id_link, details) VALUES (%s, %s, %s)",
                (str(pool_id), str(pool_id_link), details),
            )
    conn.commit()


def get_extracted_company(conn, pool_id_link: str) -> dict | None:
    """Return extracted fields if name_check is already set, else None (forces LLM call)."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT name_check, website, founded_year, revenue, ownership, employees
               FROM company_information
               WHERE pool_id_link = %s AND name_check IS NOT NULL
               ORDER BY created_at DESC LIMIT 1""",
            (pool_id_link,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {
        "name_check":   row[0],
        "website":      row[1] or "",
        "founded_year": row[2] or "",
        "revenue":      row[3] or "",
        "ownership":    row[4] or "",
        "employees":    row[5] or "",
    }


# ── Generic scraper cache ─────────────────────────────────────────────────────

def ensure_cache_table(conn, table: str) -> None:
    with conn.cursor() as cur:
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {table} (
                key        TEXT PRIMARY KEY,
                results    JSONB NOT NULL,
                scraped_at TIMESTAMP DEFAULT NOW()
            )
        """)
    conn.commit()


def cache_get(conn, table: str, key: str) -> list | None:
    with conn.cursor() as cur:
        cur.execute(f"SELECT results FROM {table} WHERE key = %s", (key,))
        row = cur.fetchone()
    if row is None:
        return None
    val = row[0]
    return json.loads(val) if isinstance(val, str) else val


def cache_set(conn, table: str, key: str, results: list) -> None:
    with conn.cursor() as cur:
        cur.execute(f"""
            INSERT INTO {table} (key, results, scraped_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (key) DO UPDATE SET results = EXCLUDED.results, scraped_at = NOW()
        """, (key, json.dumps(results, ensure_ascii=False)))
    conn.commit()


def stocks_cache_key(sectors: list, sections: list, periods: list) -> str:
    parts = sorted(sectors) + ["||"] + sorted(sections) + ["||"] + sorted(periods)
    return "stocks:" + hashlib.md5("|".join(parts).encode()).hexdigest()


# ── Cache management (for /cache endpoints) ───────────────────────────────────

def cache_stats(conn) -> dict:
    stats = {}
    with conn.cursor() as cur:
        for table in ALL_CACHE_TABLES:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                stats[table] = cur.fetchone()[0]
            except Exception:
                conn.rollback()
                stats[table] = "table missing"
        try:
            cur.execute("SELECT COUNT(*) FROM company_information")
            stats["company_information"] = cur.fetchone()[0]
        except Exception:
            conn.rollback()
            stats["company_information"] = "table missing"
    return stats


def cache_clear(conn, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {table}")
        deleted = cur.rowcount
    conn.commit()
    return deleted
