"""
routers/zocdoc.py — ZocDoc listing + profile scrapers

Routes:
  POST /probe/zocdoc          → provider listings (name, specialty, address, …)
  POST /probe/zocdoc-profiles → office locations from doctor profile pages
"""

import json
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Form
from fastapi.responses import JSONResponse

from probes import zocdoc_profile_scraper, zocdoc_scraper
from shared import _Cache, _file_response, _ts, DATA_DIR

router = APIRouter(tags=["ZocDoc"])


@router.post(
    "/probe/zocdoc",
    summary="Scrape ZocDoc provider listings",
    response_description="CSV or JSON — name, specialty, address, profile_url, accepting_new_patients",
)
async def probe_zocdoc(
    url:                 Optional[str] = Form(default=None,  description="Single ZocDoc listing URL"),
    urls:                Optional[str] = Form(default=None,  description="Multiple listing URLs, one per line"),
    page_load_wait:      int           = Form(default=8,     description="Seconds to wait after each page load"),
    delay_between_pages: float         = Form(default=4.0,   description="Base seconds between pages (jitter added automatically)"),
    max_pages:           int           = Form(default=0,     description="Per-URL page cap; 0 = use total-results count"),
    output_format:       str           = Form(default="csv", description="csv or json"),
):
    """
    Scrape one or more ZocDoc city/specialty listing pages.

    Paginates automatically (appends /2, /3, …) until all providers are
    collected or `max_pages` is reached. Results are deduplicated by
    name+address and profile_url before download.

    **Columns:** name, specialty, address, profile_url, accepting_new_patients, Source URL, Source
    """
    url_list: list = []
    if url and url.strip():
        url_list.append(url.strip())
    if urls and urls.strip():
        url_list.extend([u.strip() for u in urls.splitlines() if u.strip()])

    if not url_list:
        return JSONResponse(status_code=400, content={"error": "No URLs provided"})

    ts = _ts()
    all_rows: list = []

    for idx, u in enumerate(url_list, 1):
        cached = _Cache.get(u)
        if cached is not None:
            print(f"[zocdoc cache hit] {u}")
            all_rows.extend(cached)
            continue
        print(f"[zocdoc {idx}/{len(url_list)}] {u}")
        rows = zocdoc_scraper.scrape_url(
            url=u,
            page_load_wait=page_load_wait,
            delay_between_pages=delay_between_pages,
            max_pages=max_pages,
            log=print,
        )
        _Cache.set(u, rows)
        all_rows.extend(rows)

    if not all_rows:
        return JSONResponse(status_code=200, content={"message": "No providers scraped"})

    df = pd.DataFrame(all_rows)
    df = df.drop_duplicates(subset=["name", "address"]).reset_index(drop=True)
    df = df.drop_duplicates(subset=["profile_url"]).reset_index(drop=True)

    output_file = str(DATA_DIR / f"zocdoc_{ts}.csv")
    df.to_csv(output_file, index=False)

    if output_format.lower() == "json":
        jpath = str(DATA_DIR / f"zocdoc_{ts}.json")
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(
                {"scraped_at": ts, "total": len(df), "results": df.to_dict(orient="records")},
                f, indent=2, ensure_ascii=False,
            )
        return _file_response(jpath, "application/json", f"zocdoc_{ts}.json")

    return _file_response(output_file, "text/csv", f"zocdoc_{ts}.csv")


@router.post(
    "/probe/zocdoc-profiles",
    summary="Scrape ZocDoc doctor profiles for office locations",
    response_description="CSV or JSON — profile_url, company_name, company_address, Source",
)
async def probe_zocdoc_profiles(
    url:            Optional[str] = Form(default=None,  description="Single ZocDoc doctor profile URL"),
    urls:           Optional[str] = Form(default=None,  description="Multiple profile URLs, one per line"),
    page_load_wait: int           = Form(default=8,     description="Seconds to wait after each page load"),
    output_format:  str           = Form(default="csv", description="csv or json"),
):
    """
    Extract office locations from ZocDoc doctor profile pages.

    Uses DevTools JS injection to parse `[itemprop="address"]` structured-data
    cards. Falls back to single-location text extraction when no cards are found.
    Only the first (primary) office per profile is kept.

    **Columns:** profile_url, company_name, company_address, Source
    """
    url_list: list = []
    if url and url.strip():
        url_list.append(url.strip())
    if urls and urls.strip():
        url_list.extend([u.strip() for u in urls.splitlines() if u.strip()])

    if not url_list:
        return JSONResponse(status_code=400, content={"error": "No URLs provided"})

    ts = _ts()
    all_rows: list = []

    for idx, u in enumerate(url_list, 1):
        cached = _Cache.get(u)
        if cached is not None:
            print(f"[zocdoc-profiles cache hit] {u}")
            all_rows.extend(cached)
            continue
        print(f"[zocdoc-profiles {idx}/{len(url_list)}] {u}")
        rows = zocdoc_profile_scraper.scrape_profile(
            url=u,
            page_load_wait=page_load_wait,
            log=print,
        )
        _Cache.set(u, rows)
        all_rows.extend(rows)

    if not all_rows:
        return JSONResponse(status_code=200, content={"message": "No office locations scraped"})

    df = pd.DataFrame(all_rows, columns=["profile_url", "company_name", "company_address", "Source"])
    df = df.drop_duplicates(subset=["company_name", "company_address"]).reset_index(drop=True)

    output_file = str(DATA_DIR / f"zocdoc_profiles_{ts}.csv")
    df.to_csv(output_file, index=False)

    if output_format.lower() == "json":
        jpath = str(DATA_DIR / f"zocdoc_profiles_{ts}.json")
        with open(jpath, "w", encoding="utf-8") as f:
            json.dump(
                {"scraped_at": ts, "total": len(df), "results": df.to_dict(orient="records")},
                f, indent=2, ensure_ascii=False,
            )
        return _file_response(jpath, "application/json", f"zocdoc_profiles_{ts}.json")

    return _file_response(output_file, "text/csv", f"zocdoc_profiles_{ts}.csv")
