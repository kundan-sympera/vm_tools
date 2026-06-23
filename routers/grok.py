"""
routers/grok.py — Grok company enrichment probe

Routes:
  POST /probe/grok  → CSV upload or JSON array, returns enriched CSV/JSON

Input (one of):
  csv_file       — multipart CSV with columns: pool_id, pool_id_link, validated_name, validated_address
  companies_json — JSON array of objects with the same columns (n8n-friendly alternative)
"""

import io
import json
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from probes import grok as grok_probe
from shared import _respond

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
