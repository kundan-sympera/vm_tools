"""
routers/stocks.py — Indian Stocks (StockEdge) probe

Routes:
  POST /probe/stocks
"""

import json
import os
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from probes import indian_stocks
from shared import _Cache, _file_response, _stocks_key, _ts, DATA_DIR

router = APIRouter()


@router.post("/probe/stocks")
async def probe_stocks(
    sectors:       Optional[str] = Form(default=None, description="Comma-separated sector slugs"),
    sections:      Optional[str] = Form(default=None, description="Comma-separated section names"),
    periods:       Optional[str] = Form(default=None, description="Comma-separated time periods"),
    output_format: str           = Form(default="csv"),
):
    def _parse(raw: Optional[str], default: list) -> list:
        if not raw or not raw.strip():
            return default
        return [v.strip() for v in raw.split(",") if v.strip()]

    sel_sectors  = _parse(sectors,  indian_stocks.ALL_SECTORS)
    sel_sections = _parse(sections, indian_stocks.ALL_SECTIONS)
    sel_periods  = _parse(periods,  indian_stocks.ALL_PERIODS)

    ts = _ts()
    output_file = str(DATA_DIR / f"stocks_{ts}.csv")

    print(f"[stocks] {len(sel_sectors)} sectors × {len(sel_sections)} sections × {len(sel_periods)} periods")

    cache_key = _stocks_key(sel_sectors, sel_sections, sel_periods)
    cached = _Cache.get(cache_key)
    if cached is not None:
        print(f"[stocks cache hit] {len(cached)} rows")
        if not cached:
            return JSONResponse(status_code=200, content={"message": "No rows scraped"})
        pd.DataFrame(cached).to_csv(output_file, index=False)
    else:
        total = indian_stocks.scrape(
            sectors=sel_sectors,
            sections=sel_sections,
            periods=sel_periods,
            output_file=output_file,
        )
        if total == 0 or not os.path.exists(output_file):
            return JSONResponse(status_code=200, content={"message": "No rows scraped"})
        _Cache.set(cache_key, pd.read_csv(output_file).to_dict(orient="records"))

    if output_format.lower() == "json":
        df = pd.read_csv(output_file)
        jpath = output_file.replace(".csv", ".json")
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(
                {"scraped_at": ts, "total": len(df), "results": df.to_dict(orient="records")},
                f, indent=2, ensure_ascii=False,
            )
        return _file_response(jpath, "application/json", f"stocks_{ts}.json")

    return _file_response(output_file, "text/csv", f"stocks_{ts}.csv")
