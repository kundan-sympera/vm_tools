"""
routers/pipeline.py — Chained probe pipelines

Routes:
  POST /pipeline/grok-to-extract  → Grok enrichment → Company extraction → final CSV
"""

import io
from typing import Optional

import pandas as pd
from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response

from probes import grok as grok_probe
from services import company_extractor

router = APIRouter(tags=["Pipelines"], prefix="/pipeline")


@router.post("/grok-to-extract")
async def grok_to_extract(
    csv_file:      UploadFile    = File(...),
    system_prompt: Optional[str] = Form(default=None),
):
    # ── Step 1: read input CSV ────────────────────────────────
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

    # ── Step 2: Grok enrichment ───────────────────────────────
    print(f"[pipeline] Step 1/2 — Grok enrichment for {len(companies)} companies")
    grok_results = grok_probe.scrape(
        companies=companies,
        system_prompt=system_prompt or None,
    )

    # ── Step 3: Company extraction ────────────────────────────
    print(f"[pipeline] Step 2/2 — Company extraction")
    grok_csv_bytes = pd.DataFrame(grok_results).to_csv(index=False).encode("utf-8")
    output_csv = company_extractor.run(grok_csv_bytes)

    return Response(
        content=output_csv,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=pipeline_output.csv"},
    )
