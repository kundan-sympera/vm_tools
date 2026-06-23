"""
services/company_extractor.py — Extract structured company data from a CSV using DeepSeek.

Input CSV columns : pool_id, pool_id_link, validated_name, validated_address, details, status
Output CSV columns: pool_id_link, field, value  (one row per field, name_check=True only)

DB table          : company_information (one row per company)
"""

import io
from datetime import datetime

import pandas as pd

from prompts.company_extraction import SYSTEM_PROMPT, build_user_prompt
from utils.db import get_conn, ensure_company_table, get_extracted_company
from utils.llm import get_deepseek_response, parse_llm_response

_FIELDS = ["website", "founded_year", "revenue", "ownership", "employees"]


def _upsert_company(conn, pool_id: str, pool_id_link: str, extracted: dict, details: str):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM company_information WHERE pool_id_link = %s ORDER BY created_at DESC LIMIT 1",
            (pool_id_link,),
        )
        row = cur.fetchone()
        if row:
            cur.execute("""
                UPDATE company_information
                SET pool_id=%(pool_id)s, name_check=%(name_check)s, website=%(website)s,
                    founded_year=%(founded_year)s, revenue=%(revenue)s, ownership=%(ownership)s,
                    employees=%(employees)s, details=%(details)s, created_at=%(created_at)s
                WHERE id=%(id)s
            """, {
                "id":           row[0],
                "pool_id":      str(pool_id),
                "name_check":   extracted.get("name_check", False),
                "website":      extracted.get("website", ""),
                "founded_year": extracted.get("founded_year", ""),
                "revenue":      extracted.get("revenue", ""),
                "ownership":    extracted.get("ownership", ""),
                "employees":    extracted.get("employees", ""),
                "details":      details,
                "created_at":   datetime.now(),
            })
        else:
            cur.execute("""
                INSERT INTO company_information
                    (pool_id, pool_id_link, name_check, website, founded_year, revenue, ownership, employees, details, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                str(pool_id),
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
    df.columns = df.columns.str.lower()

    required = {"pool_id", "pool_id_link", "validated_name", "validated_address", "details"}
    missing  = required - set(df.columns)
    if missing:
        raise ValueError(f"Input CSV missing columns: {missing}")

    conn = get_conn()
    ensure_company_table(conn)

    output_rows = []

    for _, row in df.iterrows():
        pool_id      = str(row["pool_id"])
        pool_id_link = str(row["pool_id_link"])
        name         = str(row.get("validated_name", ""))
        address      = str(row.get("validated_address", ""))
        details      = str(row.get("details", ""))

        print(f"[company_extractor] Processing pool_id={pool_id} — {name}")

        extracted = get_extracted_company(conn, pool_id_link)
        if extracted:
            print(f"[company_extractor] cache hit for {pool_id_link}")
        else:
            user_prompt = build_user_prompt(name, address, details)
            raw         = get_deepseek_response(SYSTEM_PROMPT, user_prompt)
            extracted   = parse_llm_response(raw)
            if not isinstance(extracted, dict):
                extracted = {}
            _upsert_company(conn, pool_id, pool_id_link, extracted, details)

        if extracted.get("name_check") is True:
            for field in _FIELDS:
                value = extracted.get(field, "")
                if value:
                    output_rows.append({"pool_id_link": pool_id_link, "field": field, "value": value})

    conn.close()

    out_df = pd.DataFrame(output_rows, columns=["pool_id_link", "field", "value"])
    buf = io.BytesIO()
    out_df.to_csv(buf, index=False)
    return buf.getvalue()
