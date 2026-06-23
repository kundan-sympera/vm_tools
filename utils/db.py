"""
utils/db.py — Shared PostgreSQL helpers.

Provides a connection factory and operations on the company_information table
so that probes, services, and routers don't each re-implement the same boilerplate.

Public API
----------
get_conn()                                             -> connection
ensure_company_table(conn)                             -> None
get_details(conn, pool_id_link)                        -> str | None
save_details(conn, pool_id, pool_id_link, details)     -> None
"""

import os

import psycopg2
import psycopg2.extras

_DEFAULT_URL = "postgresql://postgres:postgres@localhost:5432/vm_tools_cache"

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

# Minimum detail length considered a valid cache hit
_MIN_DETAIL_LEN = 100


def get_conn() -> psycopg2.extensions.connection:
    """Return a new psycopg2 connection from DATABASE_URL (or a local default)."""
    url = os.getenv("DATABASE_URL", _DEFAULT_URL)
    return psycopg2.connect(url)


def ensure_company_table(conn) -> None:
    """Create company_information if it does not already exist."""
    with conn.cursor() as cur:
        cur.execute(_CREATE_COMPANY_TABLE)
    conn.commit()


def get_details(conn, pool_id_link: str) -> str | None:
    """
    Return the most-recent details for pool_id_link if they are >= 100 chars,
    otherwise return None (caller should re-scrape).
    """
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
    """
    Update existing row for pool_id_link, or insert a new one if absent.
    Only writes the raw details column; extracted fields are set by company_extractor.
    """
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
