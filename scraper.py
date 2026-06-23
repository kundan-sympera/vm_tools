"""
scraper.py — VM Scraper entry point

Routes:
  routers/general.py   → GET /,  POST /scrape
  routers/zoominfo.py  → POST /probe/zoominfo
  routers/stocks.py    → POST /probe/stocks
  routers/zocdoc.py    → POST /probe/zocdoc, POST /probe/zocdoc-profiles
  routers/grok.py      → POST /probe/grok
  routers/company.py   → POST /service/company-extract
  routers/explore.py   → GET  /explore/companies
  routers/cache.py     → GET/DELETE /cache
"""

from dotenv import load_dotenv
load_dotenv()

import os
import webbrowser

VERSION = "1.0.0"

import pyautogui
import uvicorn
from fastapi import FastAPI

from routers import cache, company, explore, general, grok, stocks, zoominfo, zocdoc

pyautogui.PAUSE    = 0.8
pyautogui.FAILSAFE = False
webbrowser.open("example.com")

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
        "| `POST /probe/grok` | Grok company enrichment |\n"
        "| `POST /service/company-extract` | DeepSeek structured extraction |\n"
    ),
)

app.include_router(general.router)
app.include_router(zoominfo.router)
app.include_router(stocks.router)
app.include_router(zocdoc.router)
app.include_router(cache.router)
app.include_router(company.router)
app.include_router(explore.router)
app.include_router(grok.router)


@app.get("/health")
def health():
    return {"status": "running", "message": "VM Scraper is ready", "version": VERSION}


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    print("VM Scraper starting …")
    print(f"→  http://0.0.0.0:{port}")
    print(f"→  http://0.0.0.0:{port}/docs")
    uvicorn.run(app, host="0.0.0.0", port=port)
