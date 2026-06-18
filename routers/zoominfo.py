"""
routers/zoominfo.py — ZoomInfo company search probe

Routes:
  POST /probe/zoominfo
"""

import json
import os
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from probes import zoominfo
from shared import _Cache, _file_response, _ts, DATA_DIR

router = APIRouter()


@router.post("/probe/zoominfo")
async def probe_zoominfo(
    # builder mode
    cities:        Optional[str] = Form(default=None, description="One city per line: state, city"),
    industries:    Optional[str] = Form(default=None, description="Comma-separated industry slugs"),
    # raw mode
    raw_urls:      Optional[str] = Form(default=None, description="Raw URL templates, one per line"),
    # shared
    max_pages:     int           = Form(default=5),
    min_companies: int           = Form(default=9),
    output_format: str           = Form(default="csv"),
):
    ts = _ts()
    output_file = str(DATA_DIR / f"zoominfo_{ts}.csv")

    if raw_urls and raw_urls.strip():
        url_list = [u.strip() for u in raw_urls.splitlines() if u.strip()]
    else:
        city_list = zoominfo.parse_city_input(cities or "")
        ind_list  = [i.strip() for i in (industries or "").split(",") if i.strip()]
        if not ind_list:
            ind_list = zoominfo.INDUSTRIES
        url_list = zoominfo.build_urls(city_list, ind_list)

    if not url_list:
        return JSONResponse(status_code=400, content={"error": "No URLs resolved"})

    print(f"[zoominfo] {len(url_list)} URL templates, max_pages={max_pages}")

    all_rows: list = []
    for u in url_list:
        cached = _Cache.get(u)
        if cached is not None:
            print(f"[zoominfo cache hit] {u}")
            all_rows.extend(cached)
            continue
        tmp = str(DATA_DIR / f"zi_tmp_{_ts()}.csv")
        count = zoominfo.scrape(urls=[u], output_file=tmp, max_pages=max_pages, min_companies=min_companies)
        if count > 0 and os.path.exists(tmp):
            rows = pd.read_csv(tmp).to_dict(orient="records")
            _Cache.set(u, rows)
            all_rows.extend(rows)
            os.remove(tmp)

    if not all_rows:
        return JSONResponse(status_code=200, content={"message": "No rows scraped"})

    pd.DataFrame(all_rows).to_csv(output_file, index=False)

    if output_format.lower() == "json":
        ts2 = _ts()
        jpath = str(DATA_DIR / f"zoominfo_{ts2}.json")
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(
                {"scraped_at": ts, "total": len(all_rows), "results": all_rows},
                f, indent=2, ensure_ascii=False,
            )
        return _file_response(jpath, "application/json", f"zoominfo_{ts2}.json")

    return _file_response(output_file, "text/csv", f"zoominfo_{ts}.csv")
