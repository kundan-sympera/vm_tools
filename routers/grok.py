"""
routers/grok.py — Grok company enrichment probe

Routes:
  POST /probe/grok             → CSV upload or JSON array, returns enriched CSV/JSON
  GET  /probe/grok/data        → list cached grok results (optional search on pool_id or validated_name)
  GET  /probe/grok/data/{id}   → single full row (includes markdown details)

Input (one of):
  csv_file       — multipart CSV with columns: pool_id, pool_id_link, validated_name, validated_address
  companies_json — JSON array of objects with the same columns (n8n-friendly alternative)
"""

import io
import json
from typing import Optional

import pandas as pd
import psycopg2.extras
from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse

from probes import grok as grok_probe
from shared import _respond
from utils.db import get_conn

router = APIRouter()


@router.post("/probe/grok")
async def probe_grok(
    csv_file:       Optional[UploadFile] = File(default=None),
    companies_json: Optional[str]        = Form(default=None, description='JSON array: [{"pool_id":…,"pool_id_link":…,"validated_name":…,"validated_address":…}]'),
    system_prompt:  Optional[str]        = Form(default=None),
    output_format:  str                  = Form(default="csv"),
):
    if companies_json and companies_json.strip():
        try:
            companies = json.loads(companies_json)
            if not isinstance(companies, list):
                raise ValueError("Expected a JSON array")
        except Exception as exc:
            return JSONResponse(status_code=400, content={"error": f"Invalid companies_json: {exc}"})
        required_cols = {"pool_id", "pool_id_link", "validated_name", "validated_address"}
        if companies:
            missing = required_cols - set(companies[0].keys())
            if missing:
                return JSONResponse(status_code=400, content={"error": f"companies_json missing keys: {', '.join(sorted(missing))}"})
    elif csv_file is not None:
        try:
            contents = await csv_file.read()
            df = pd.read_csv(io.BytesIO(contents))
        except Exception as exc:
            return JSONResponse(status_code=400, content={"error": f"Could not read CSV: {exc}"})
        required_cols = {"pool_id", "pool_id_link", "validated_name", "validated_address"}
        missing = required_cols - set(df.columns)
        if missing:
            return JSONResponse(status_code=400, content={"error": f"CSV missing columns: {', '.join(sorted(missing))}"})
        companies = df[["pool_id", "pool_id_link", "validated_name", "validated_address"]].to_dict(orient="records")
    else:
        return JSONResponse(status_code=400, content={"error": "Provide either csv_file or companies_json"})

    if not companies:
        return JSONResponse(status_code=400, content={"error": "No companies provided"})

    print(f"[grok] {len(companies)} companies")

    results = grok_probe.scrape(
        companies=companies,
        system_prompt=system_prompt or None,
    )

    return _respond(results, output_format, "grok")


@router.get("/probe/grok/data")
def list_grok_data(search: str = Query("", description="Filter by pool_id or validated_name (case-insensitive)")):
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if search.strip():
                cur.execute(
                    """
                    SELECT id, pool_id, pool_id_link, validated_name, created_at
                    FROM company_information
                    WHERE details IS NOT NULL AND length(trim(details)) > 0
                      AND (pool_id::text ILIKE %s OR validated_name ILIKE %s)
                    ORDER BY created_at DESC
                    LIMIT 500
                    """,
                    (f"%{search.strip()}%", f"%{search.strip()}%"),
                )
            else:
                cur.execute(
                    """
                    SELECT id, pool_id, pool_id_link, validated_name, created_at
                    FROM company_information
                    WHERE details IS NOT NULL AND length(trim(details)) > 0
                    ORDER BY created_at DESC
                    LIMIT 500
                    """
                )
            rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except psycopg2.Error as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})


@router.get("/probe/grok/data/{row_id}")
def get_grok_data(row_id: int):
    try:
        conn = get_conn()
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, pool_id, pool_id_link, validated_name, details, created_at
                FROM company_information
                WHERE id = %s
                """,
                (row_id,),
            )
            row = cur.fetchone()
        conn.close()
        if row is None:
            return JSONResponse(status_code=404, content={"error": "Row not found"})
        return dict(row)
    except psycopg2.Error as exc:
        return JSONResponse(status_code=500, content={"error": str(exc)})
