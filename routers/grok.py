"""
routers/grok.py — Grok company enrichment probe

Routes:
  POST /probe/grok  → upload CSV (id, validated_name, validated_address), returns enriched CSV
"""

import io
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from probes import grok as grok_probe
from shared import _respond

router = APIRouter()


@router.post("/probe/grok")
async def probe_grok(
    csv_file:      UploadFile    = File(...),
    system_prompt: Optional[str] = Form(default=None),
    output_format: str           = Form(default="csv"),
):
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
    if not companies:
        return JSONResponse(status_code=400, content={"error": "CSV has no data rows"})

    print(f"[grok] {len(companies)} companies loaded from CSV")

    results = grok_probe.scrape(
        companies=companies,
        system_prompt=system_prompt or None,
    )

    return _respond(results, output_format, "grok")
