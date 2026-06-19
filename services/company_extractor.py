"""
services/company_extractor.py — Extract structured company data from a CSV using DeepSeek.

Input CSV columns : id, company_name, company_address, details, status
Output CSV columns: pool_id_link, field, value  (one row per field, name_check=True only)

DB table          : company_information (one row per company)
"""

import io
import os
from datetime import datetime

import pandas as pd
import psycopg2

from prompts.company_extraction import SYSTEM_PROMPT, build_user_prompt
from utils.llm import get_deepseek_response, parse_llm_response

_FIELDS = ["website", "founded_year", "revenue", "ownership", "employees"]

_CREATE_TABLE = """
    CREATE TABLE IF NOT EXISTS company_information (
        id           SERIAL PRIMARY KEY,
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


def _get_conn():
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set")
    return psycopg2.connect(url)


def _ensure_table(conn):
    with conn.cursor() as cur:
        cur.execute(_CREATE_TABLE)
    conn.commit()


def _upsert_company(conn, pool_id_link: str, extracted: dict, details: str):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO company_information
                (pool_id_link, name_check, website, founded_year, revenue, ownership, employees, details, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
        """, (
            str(pool_id_link),
            extracted.get("name_check", False),
            extracted.get("website", ""),
            extracted.get("founded_year", ""),
            extracted.get("revenue", ""),
            extracted.get("ownership", ""),
            extracted.get("employees", ""),
            details,
            datetime.now(),
        ))
    conn.commit()


def run(csv_bytes: bytes) -> bytes:
    """
    Process the uploaded CSV bytes.
    Returns output CSV bytes in pool_id_link, field, value format.
    """
    df = pd.read_csv(io.BytesIO(csv_bytes))

    required = {"id", "company_name", "company_address", "details"}
    missing  = required - set(df.columns.str.lower())
    if missing:
        raise ValueError(f"Input CSV missing columns: {missing}")

    df.columns = df.columns.str.lower()

    conn = _get_conn()
    _ensure_table(conn)

    output_rows = []

    for _, row in df.iterrows():
        pool_id     = str(row["id"])
        name        = str(row.get("company_name", ""))
        address     = str(row.get("company_address", ""))
        details     = str(row.get("details", ""))

        print(f"[company_extractor] Processing id={pool_id} — {name}")

        user_prompt = build_user_prompt(name, address, details)
        raw         = get_deepseek_response(SYSTEM_PROMPT, user_prompt)
        extracted   = parse_llm_response(raw)

        if not isinstance(extracted, dict):
            extracted = {}

        _upsert_company(conn, pool_id, extracted, details)

        if extracted.get("name_check") is True:
            for field in _FIELDS:
                value = extracted.get(field, "")
                if value:
                    output_rows.append({"pool_id_link": pool_id, "field": field, "value": value})

    conn.close()

    out_df = pd.DataFrame(output_rows, columns=["pool_id_link", "field", "value"])
    buf = io.BytesIO()
    out_df.to_csv(buf, index=False)
    return buf.getvalue()
