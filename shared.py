"""
shared.py — Helpers shared across routers.

Exports:
  DATA_DIR          Path to output directory
  _ts()             Timestamp string
  _file_response()  FastAPI FileResponse helper
  _respond()        Return results as inline JSONResponse or CSV FileResponse
"""

import os
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi.responses import FileResponse, JSONResponse

DATA_DIR = Path("data")
os.makedirs(DATA_DIR, exist_ok=True)


def _ts() -> str:
    return datetime.now().strftime("%Y_%m_%d_%H_%M_%S")


def _file_response(path: str, media_type: str, filename: str) -> FileResponse:
    return FileResponse(path=path, media_type=media_type, filename=filename)


def _respond(results: list, output_format: str, stem: str):
    """Return results as inline JSONResponse or CSV FileResponse."""
    ts = _ts()
    output_format = output_format.lower()

    if output_format == "json":
        return JSONResponse(content={"scraped_at": ts, "total": len(results), "results": results})

    fpath = str(DATA_DIR / f"{stem}_{ts}.csv")
    pd.DataFrame(results).to_csv(fpath, index=False)
    return _file_response(fpath, "text/csv", f"{stem}_{ts}.csv")
