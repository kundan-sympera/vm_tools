"""
ZocDoc Profile Scraper.

Takes one or more ZocDoc doctor profile URLs and extracts office locations
(practice name + address) via DevTools JS injection.

USAGE
-----
    # Single profile:
    python zocdoc_profile_scraper.py --url "https://www.zocdoc.com/doctor/alex-harrison-do-433823"

    # Batch from file (one URL per line):
    python zocdoc_profile_scraper.py --urls-file profiles.txt

    # XLSX only:
    python zocdoc_profile_scraper.py --url "..." --format xlsx

OUTPUT
------
    scraper/output/zocdoc_profiles_<timestamp>.{csv,xlsx}

    Columns: profile_url, practice_name, address
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional
from urllib.parse import urlparse

import pandas as pd
import pyautogui
import pyperclip


OUTPUT_DIR = Path(__file__).resolve().parent / "output"
SOURCE_NAME = "zocdoc"

# ---------------------------------------------------------------------------
# JavaScript snippets
# ---------------------------------------------------------------------------

# Step 1 — copy all visible page text to clipboard (for block/captcha detection)
JS_PAGE_TEXT = r"""
(function() {
  var ta = document.createElement('textarea');
  ta.value = document.body.innerText;
  ta.style.cssText = 'position:fixed;left:-999999px;top:-999999px';
  document.body.appendChild(ta);
  ta.focus(); ta.select();
  try { document.execCommand('copy'); } catch(e) {}
  document.body.removeChild(ta);
})();
"""

# Step 2 — extract office locations from a doctor profile page
JS_EXTRACT_LOCATIONS = r"""
(function() {
    var clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
    var locations = [];
    var seen = new Set();

    console.log('zocdoc-profile: extracting office locations...');

    // Main selector for structured address cards
    const addressCards = document.querySelectorAll('div[itemprop="address"]');

    console.log('zocdoc-profile: found ' + addressCards.length + ' address cards');

    addressCards.forEach((card, index) => {
        let practice_name = '';
        let address_parts = [];

        const nameEl = card.querySelector('span[itemprop="name"]');
        if (nameEl) practice_name = clean(nameEl.innerText);

        const streetEl = card.querySelector('span[itemprop="streetAddress"]');
        if (streetEl) address_parts.push(clean(streetEl.innerText));

        const localityEl = card.querySelector('span[itemprop="addressLocality"]');
        const regionEl = card.querySelector('span[itemprop="addressRegion"]');
        const postalEl = card.querySelector('span[itemprop="postalCode"]');

        if (localityEl) address_parts.push(clean(localityEl.innerText));
        if (regionEl) address_parts.push(clean(regionEl.innerText));
        if (postalEl) address_parts.push(clean(postalEl.innerText));

        let address = address_parts.filter(Boolean).join(', ');

        // Fallback if address is missing
        if (!address) {
            const fullText = clean(card.innerText);
            const zipMatch = fullText.match(/(\d{5}(?:-\d{4})?)/);
            if (zipMatch) address = fullText;
        }

        if (address) {
            let key = (practice_name + '|' + address).toLowerCase().replace(/\s+/g, '');
            if (!seen.has(key)) {
                seen.add(key);
                locations.push({
                    company_name: practice_name || 'Main Practice',
                    company_address: clean(address)
                });
                console.log('zocdoc-profile #' + locations.length + ': ' + (practice_name || 'Main Practice') + ' | ' + address);
            }
        }
    });

    // Fallback for pages with a single location (no structured cards)
    if (locations.length === 0) {
        console.log('zocdoc-profile: trying single location fallback...');
        const locationSection = Array.from(document.querySelectorAll('h2, h3')).find(h =>
            clean(h.innerText).toLowerCase().includes('office location')
        );

        if (locationSection) {
            let container = locationSection.parentElement;
            while (container && container.innerText.length < 500) container = container.parentElement;

            const text = clean(container ? container.innerText : document.body.innerText);
            const addressMatch = text.match(/([A-Za-z0-9\s,]+?\d{5}(?:-\d{4})?)/);
            if (addressMatch) {
                locations.push({
                    company_name: 'Main Practice',
                    company_address: addressMatch[1]
                });
            }
        }
    }

    var ta = document.createElement('textarea');
    ta.value = JSON.stringify({ locations: locations, profile_url: location.href, count: locations.length });
    ta.style.cssText = 'position:fixed;left:-9999px;top:0';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    try {
        document.execCommand('copy');
        console.log('zocdoc-profile: copied ' + locations.length + ' location(s) to clipboard');
    } catch(e) {
        console.log('zocdoc-profile: copy failed');
    }
    document.body.removeChild(ta);
})();
"""

# ---------------------------------------------------------------------------
# Block detection
# ---------------------------------------------------------------------------

_BLOCK_PHRASES = [
    "press & hold to confirm",
    "confirm you are a human",
    "you are being rate limited",
    "has banned you temporarily",
    "access denied",
    "please verify you are a human",
]


def _is_blocked(text: str) -> bool:
    return any(p in text.lower() for p in _BLOCK_PHRASES)


# ---------------------------------------------------------------------------
# DevTools helpers
# ---------------------------------------------------------------------------

def _open_devtools(log: Callable) -> None:
    log("[devtools] opening (F12)...")
    pyautogui.press("f12")
    time.sleep(random.uniform(1.5, 2.5))


def _close_devtools(log: Callable) -> None:
    log("[devtools] closing (F12)...")
    pyautogui.press("f12")
    time.sleep(0.5)


def _run_js(js: str, log: Callable) -> str:
    pyperclip.copy(js)
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "shift", "v")
    pyautogui.press("enter")
    time.sleep(random.uniform(1.5, 3.0))
    result = pyperclip.paste()
    log(f"[devtools] clipboard {len(result)} chars")
    return result


# ---------------------------------------------------------------------------
# Core scrape for one profile URL
# ---------------------------------------------------------------------------

def scrape_profile(
    url: str,
    page_load_wait: int,
    log: Callable,
) -> List[dict]:
    log(f"[browser] opening {url}")
    webbrowser.open(url)
    wait = page_load_wait + random.uniform(0, 3)
    log(f"[browser] waiting {wait:.1f}s...")
    time.sleep(wait)

    _open_devtools(log)

    # Block/captcha check
    page_text = _run_js(JS_PAGE_TEXT, log)
    if _is_blocked(page_text):
        log("[warn] block/captcha detected — waiting 30s then retrying once")
        _close_devtools(log)
        time.sleep(30)
        webbrowser.open(url)
        time.sleep(page_load_wait + 5)
        _open_devtools(log)
        page_text = _run_js(JS_PAGE_TEXT, log)
        if _is_blocked(page_text):
            log("[error] still blocked — skipping this URL")
            _close_devtools(log)
            return []

    raw = _run_js(JS_EXTRACT_LOCATIONS, log)
    _close_devtools(log)

    log("[browser] closing tab (Ctrl+W)...")
    pyautogui.hotkey("ctrl", "w")
    time.sleep(0.5)

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        log(f"[error] JSON parse failed — raw: {raw[:200]!r}")
        return []

    locations = data.get("locations") or []
    log(f"[profile] {len(locations)} office location(s) found")

    # Drop fallback placeholders, keep only the first real location
    locations = [l for l in locations if l.get("company_name", "").strip() != "Main Practice"]
    log(f"[profile] {len(locations)} after removing 'Main Practice' entries")
    if len(locations) > 1:
        log(f"[profile] keeping first location: {locations[0].get('company_name')} | {locations[0].get('company_address')}")
    locations = locations[:1]

    for loc in locations:
        loc["profile_url"] = url
        loc["Source"] = SOURCE_NAME

    return locations


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_output(
    rows: List[dict],
    base_name: str,
    fmt: str,
    log: Callable,
) -> List[Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if not rows:
        log("[output] no rows to write")
        return []

    df = pd.DataFrame(rows, columns=["profile_url", "company_name", "company_address", "Source"])
    df = df.drop_duplicates(subset=["company_name", "company_address"]).reset_index(drop=True)

    fmt = fmt.lower().strip()
    written: List[Path] = []

    if fmt in ("csv", "both"):
        path = OUTPUT_DIR / f"{base_name}.csv"
        df.to_csv(path, index=False)
        written.append(path)
        log(f"[output] CSV  -> {path}")

    if fmt in ("xlsx", "excel", "both"):
        path = OUTPUT_DIR / f"{base_name}.xlsx"
        df.to_excel(path, index=False)
        written.append(path)
        log(f"[output] XLSX -> {path}")

    if not written:
        log(f"[output] unknown --format: {fmt!r}")

    return written


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run(
    url: Optional[str] = None,
    urls_file: Optional[str] = None,
    page_load_wait: int = 8,
    fmt: str = "both",
    callback: Optional[Callable] = None,
) -> bool:
    log = callback if callable(callback) else print
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")

    urls: List[str] = []
    if url:
        urls.append(url.strip())
    if urls_file:
        p = Path(urls_file)
        if not p.exists():
            log(f"[error] --urls-file not found: {p}")
            return False
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)

    if not urls:
        log("[error] no URLs provided — use --url or --urls-file")
        return False

    log("=" * 60)
    log("  ZocDoc Profile Scraper (DevTools/JS probe)")
    log(f"  URLs       = {len(urls)}")
    log(f"  page_wait  = {page_load_wait}s  (+0-3s jitter)")
    log(f"  format     = {fmt}")
    log(f"  started_at = {datetime.now().isoformat(timespec='seconds')}")
    log("=" * 60)

    all_rows: List[dict] = []
    try:
        for idx, u in enumerate(urls, 1):
            log(f"\n[{idx}/{len(urls)}] {u}")
            rows = scrape_profile(url=u, page_load_wait=page_load_wait, log=log)
            log(f"[{idx}/{len(urls)}] {len(rows)} location(s) collected")
            all_rows.extend(rows)

            if idx < len(urls):
                pause = random.randint(5, 15)
                log(f"[inter-url pause] {pause}s...")
                time.sleep(pause)

    except KeyboardInterrupt:
        log("[run] interrupted")

    log(f"\n[run] total locations across all profiles = {len(all_rows)}")

    if all_rows:
        write_output(all_rows, f"zocdoc_profiles_{timestamp}", fmt, log)

    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Scrape office locations from ZocDoc doctor profile pages.",
    )
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument("--url", help="Single ZocDoc doctor profile URL.")
    group.add_argument(
        "--urls-file",
        help="Text file of ZocDoc profile URLs, one per line.",
    )
    p.add_argument(
        "--format", default="both",
        choices=["csv", "xlsx", "excel", "both"],
    )
    p.add_argument(
        "--page-load-wait", type=int, default=8,
        help="Seconds to wait after opening a page. Default: 8.",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_argparser().parse_args(argv)
    ok = run(
        url=getattr(args, "url", None),
        urls_file=getattr(args, "urls_file", None),
        page_load_wait=args.page_load_wait,
        fmt=args.format,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
