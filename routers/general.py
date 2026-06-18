"""
routers/general.py — UI + general URL scraper

Routes:
  GET  /        → serve templates/index.html
  POST /scrape  → open each URL in browser, extract all text
"""

import time
import webbrowser
from pathlib import Path

import pyautogui
import pyperclip
from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, JSONResponse

from probes._common import open_console
from shared import _Cache, _respond, _ts

router = APIRouter()

TEMPLATE_PATH = Path("templates/index.html")

_JS_COPY_ALL = r"""
const allText = document.body.innerText;
const textArea = document.createElement("textarea");
textArea.value = allText;
textArea.style.position = "fixed";
textArea.style.left = "-999999px";
textArea.style.top  = "-999999px";
document.body.appendChild(textArea);
textArea.focus(); textArea.select();
try { document.execCommand("copy"); } catch(e) {}
document.body.removeChild(textArea);
"""


def _scrape_url(url: str, wait: int = 5) -> dict:
    """Open a URL in the browser and copy all visible text via DevTools."""
    ts = _ts()
    try:
        webbrowser.open(url)
        time.sleep(wait)
        pyautogui.press("esc")
        time.sleep(0.5)
        pyperclip.copy(_JS_COPY_ALL)
        open_console()
        time.sleep(0.5)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.5)
        pyautogui.press("enter")
        time.sleep(2)
        text = pyperclip.paste().strip()
        pyautogui.hotkey("ctrl", "w")
        time.sleep(1)
        return {
            "url": url, "text": text,
            "status": "success" if len(text) > 100 else "partial",
            "length": len(text), "timestamp": ts,
        }
    except Exception as e:
        return {"url": url, "text": f"ERROR: {e}", "status": "error", "length": 0, "timestamp": ts}


@router.get("/", response_class=HTMLResponse)
async def home():
    return HTMLResponse(content=TEMPLATE_PATH.read_text(encoding="utf-8"))


@router.post("/scrape")
async def scrape_urls(
    urls:          str = Form(...),
    output_format: str = Form(default="csv"),
):
    url_list = [u.strip() for u in urls.splitlines() if u.strip()]
    if not url_list:
        return JSONResponse(status_code=400, content={"error": "No URLs provided"})

    results = []
    for i, url in enumerate(url_list, 1):
        cached = _Cache.get(url)
        if cached is not None:
            print(f"[general cache hit] {url}")
            results.extend(cached)
            continue
        print(f"[general {i}/{len(url_list)}] {url}")
        result = _scrape_url(url)
        _Cache.set(url, [result])
        results.append(result)
        time.sleep(3)

    return _respond(results, output_format, "scraped")
