"""
scraper.py — VM Scraper entry point

Routes are split across routers/:
  routers/general.py   → GET /,  POST /scrape
  routers/zoominfo.py  → POST /probe/zoominfo
  routers/stocks.py    → POST /probe/stocks
  routers/zocdoc.py    → POST /probe/zocdoc, POST /probe/zocdoc-profiles

Shared state (DATA_DIR, _Cache, helpers) lives in shared.py.
"""

import webbrowser

VERSION = "1.0.0"

import pyautogui
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()

from routers import cache, general, stocks, zoominfo, zocdoc

# ── Browser warm-up ──────────────────────────
pyautogui.PAUSE    = 0.8
pyautogui.FAILSAFE = False
webbrowser.open("example.com")

# ── App ──────────────────────────────────────
app = FastAPI(
    title="VM Scraper",
    description=(
        "Automated browser scraper.\n\n"
        "| Endpoint | Purpose |\n"
        "|---|---|\n"
        "| `POST /scrape` | General URL text extractor |\n"
        "| `POST /probe/zoominfo` | ZoomInfo company search |\n"
        "| `POST /probe/stocks` | Indian Stocks (StockEdge) |\n"
        "| `POST /probe/zocdoc` | ZocDoc provider listings |\n"
        "| `POST /probe/zocdoc-profiles` | ZocDoc doctor office locations |\n"
    ),
)

app.include_router(general.router)
app.include_router(zoominfo.router)
app.include_router(stocks.router)
app.include_router(zocdoc.router)
app.include_router(cache.router)


@app.get("/health")
def health():
    return {"status": "running", "message": "VM Scraper is ready", "version": VERSION}


if __name__ == "__main__":
    print("VM Scraper starting …")
    print("→  http://0.0.0.0:8000")
    print("→  http://0.0.0.0:8000/docs")
    uvicorn.run(app, host="0.0.0.0", port=8000)
