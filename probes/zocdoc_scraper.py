"""
ZocDoc Scraper (DevTools / JS probe approach).

Takes a ZocDoc city/specialty listing URL such as:
    https://www.zocdoc.com/dentists/bessemer-al-244777pm

Opens the real browser (same technique as _zoominfo_probe.py), injects
JavaScript via the DevTools console to extract:
  - Total result count shown on the page
  - Doctor name, specialty, address, profile URL, accepting-new-patients status

Paginates by appending /2, /3, ... to the base URL. The total result count
from page 1 is used to compute how many pages exist. Stops early when a page
returns 0 providers.

Results are written incrementally (one file per source URL) to scraper/output/.

USAGE
-----
    # Single URL:
    python zocdoc_scraper.py --url "https://www.zocdoc.com/dentists/arrowhead-ranch-glendale-az-220726pm"

    # Batch from file (output of zocdoc_url_extractor.py):
    python zocdoc_scraper.py --urls-file zocdoc_examples/surgeons_urls.txt

    # Cap pages, xlsx only:
    python zocdoc_scraper.py --url "..." --max-pages 3 --format xlsx

OUTPUT
------
    scraper/output/zocdoc_<slug>_<timestamp>.{csv,xlsx}
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

# Step 2 — get total provider count, copies a plain integer string to clipboard
JS_GET_TOTAL = r"""
(function() {
    var clean = (s) => (s || '').replace(/\s+/g, ' ').trim();

    let total = 0;
    const selectors = [
        'h1',                                   // Main heading often contains it
        '[class*="SearchResultCount"]',
        '[class*="result-count"]',
        '[class*="ResultCount"]',
        '[class*="resultsCount"]',
        '[data-qa*="count"]',
        '[class*="count"]',                     // Broader fallback
        'header h1',                            // More specific
        '.search-header h1',                    // Zocdoc-specific patterns
        'h1[data-testid]'                       // Common React test IDs
    ];

    // Priority: Look for "X verified" pattern first
    for (let sel of selectors) {
        const els = document.querySelectorAll(sel);
        for (let el of els) {
            const text = clean(el.innerText || el.textContent);
            
            // Strong match for verified dentists pattern (handles "315 verified Dentists...")
            let match = text.match(/(\d[\d,]*)\s+verified/i);
            if (match) {
                total = parseInt(match[1].replace(/,/g, ''), 10);
                console.log('✅ zocdoc-total: Verified match found', total, 'from:', text);
                break;
            }
            
            // Fallback: any large number that looks like a count (avoid "100+")
            match = text.match(/(\d{3,}[\d,]*)/);  // Prefer 3+ digit numbers
            if (match) {
                const candidate = parseInt(match[1].replace(/,/g, ''), 10);
                if (candidate > 100 && candidate !== 100) {  // Skip the "100+" teaser
                    total = candidate;
                }
            }
        }
        if (total > 0) break;
    }

    // Whole-page fallback (very reliable for Zocdoc)
    if (total === 0 || total < 200) {
        const bodyText = clean(document.body.innerText);
        const verifiedMatch = bodyText.match(/(\d[\d,]*)\s+verified\s+(dentists|doctors|providers)/i);
        if (verifiedMatch) {
            total = parseInt(verifiedMatch[1].replace(/,/g, ''), 10);
            console.log('✅ zocdoc-total: Body fallback verified match', total);
        } else {
            // Ultra fallback - look anywhere for the location + verified pattern
            const locationMatch = bodyText.match(/(\d[\d,]*)\s+verified\s+Dentists?\s+in\s+Arrowhead/i);
            if (locationMatch) {
                total = parseInt(locationMatch[1].replace(/,/g, ''), 10);
                console.log('✅ zocdoc-total: Location-specific match', total);
            }
        }
    }

    // Copy to clipboard
    if (total > 0) {
        const ta = document.createElement('textarea');
        ta.value = total.toString();
        ta.style.cssText = 'position:fixed;left:-9999px;top:0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        try {
            document.execCommand('copy');
            console.log('✅ zocdoc-total: Copied successfully →', total);
        } catch(e) {
            console.log('❌ zocdoc-total: Copy failed');
        }
        document.body.removeChild(ta);
    } else {
        console.log('❌ zocdoc-total: No count found');
    }
})();
"""

# Step 3 — extract provider cards, copy JSON to clipboard
JS_EXTRACT = r"""
(function() {
  var clean = function(s) { return (s || '').replace(/\s+/g, ' ').trim(); };

  // --- provider cards ---
  var cardSelectors = [
    '[data-provider-id]',
    '[data-qa="provider-card"]',
    '[class*="ProviderCard"]',
    '[class*="provider-card"]',
    '[class*="UCard"]',
    'article',
  ];
  var cards = [];
  for (var j = 0; j < cardSelectors.length; j++) {
    cards = Array.from(document.querySelectorAll(cardSelectors[j]));
    if (cards.length > 0) break;
  }

  var providers = cards.map(function(card) {
    var nameSelectors = ['[data-qa="provider-name"]', 'h2', 'h3', '[class*="Name"]', '[class*="name"]'];
    var name = '';
    for (var n = 0; n < nameSelectors.length; n++) {
      var el = card.querySelector(nameSelectors[n]);
      if (el && clean(el.innerText)) { name = clean(el.innerText); break; }
    }
    if (!name) return null;

    var addrSelectors = ['[data-qa="address"]', 'address', '[class*="address"]', '[class*="Address"]', '[class*="location"]', '[class*="Location"]'];
    var address = '';
    for (var a = 0; a < addrSelectors.length; a++) {
      var el = card.querySelector(addrSelectors[a]);
      if (el && clean(el.innerText)) { address = clean(el.innerText); break; }
    }

    var specSelectors = ['[data-qa="provider-specialty"]', '[class*="specialty"]', '[class*="Specialty"]'];
    var specialty = '';
    for (var s = 0; s < specSelectors.length; s++) {
      var el = card.querySelector(specSelectors[s]);
      if (el && clean(el.innerText)) { specialty = clean(el.innerText); break; }
    }

    var link = card.querySelector('a[href]');
    var profile_url = '';
    if (link) {
      var href = link.getAttribute('href');
      profile_url = href.startsWith('/') ? 'https://www.zocdoc.com' + href : href;
    }

    var cardText = card.innerText.toLowerCase();
    var accepting = cardText.includes('not accepting new patients') ? 'No'
                  : cardText.includes('accepting new patients') ? 'Yes' : '';

    return { name: name, specialty: specialty, address: address, profile_url: profile_url, accepting_new_patients: accepting };
  }).filter(Boolean);

  var out = JSON.stringify({ providers: providers, page_url: location.href });

  var ta = document.createElement('textarea');
  ta.value = out;
  ta.style.cssText = 'position:fixed;left:-9999px;top:0';
  document.body.appendChild(ta);
  ta.focus(); ta.select();
  try { document.execCommand('copy'); } catch(e) {}
  document.body.removeChild(ta);

  console.log('zocdoc-probe: ' + providers.length + ' providers on page');
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
    t = text.lower()
    return any(p in t for p in _BLOCK_PHRASES)


# ---------------------------------------------------------------------------
# DevTools helpers (same pattern as _zoominfo_probe.py)
# ---------------------------------------------------------------------------

def _open_devtools(log: Callable) -> None:
    log("[devtools] opening (F12)...")
    pyautogui.press("f12")
    time.sleep(random.uniform(1.5, 2.5))


def _close_devtools(log: Callable) -> None:
    log("[devtools] closing (F12)...")
    pyautogui.press("f12")
    time.sleep(0.5)


def _close_tab(log: Callable) -> None:
    log("[browser] closing tab (Ctrl+W)...")
    pyautogui.hotkey("ctrl", "w")
    time.sleep(0.5)


def _run_js(js: str, log: Callable) -> str:
    """Paste js into the DevTools console and return whatever ends up on the clipboard."""
    pyperclip.copy(js)
    time.sleep(0.3)
    pyautogui.hotkey("ctrl", "shift", "v")
    pyautogui.press("enter")
    time.sleep(random.uniform(1.5, 3.0))
    result = pyperclip.paste()
    log(f"[devtools] clipboard {len(result)} chars")
    return result


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _slug_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    slug = re.sub(r"[^a-zA-Z0-9_\-]", "", path.replace("/", "_"))
    return slug or "zocdoc"


def _page_url(base_url: str, page: int) -> str:
    """page 1 → base_url   |   page 2 → base_url/2   |   page 3 → base_url/3"""
    base = base_url.rstrip("/")
    base = re.sub(r"/\d+$", "", base)  # strip any existing trailing page number
    return base if page <= 1 else f"{base}/{page}"


# ---------------------------------------------------------------------------
# Core scrape loop for one URL
# ---------------------------------------------------------------------------

def scrape_url(
    url: str,
    page_load_wait: int,
    delay_between_pages: float,
    max_pages: int,
    log: Callable,
) -> List[dict]:
    all_providers: List[dict] = []
    total_results: Optional[int] = None

    page = 1
    while True:
        page_url = _page_url(url, page)
        log(f"[page {page}] {page_url}")

        webbrowser.open(page_url)
        wait = page_load_wait + random.uniform(0, 3)
        log(f"[page {page}] waiting {wait:.1f}s...")
        time.sleep(wait)

        _open_devtools(log)

        # Check for blocks/captcha
        page_text = _run_js(JS_PAGE_TEXT, log)
        if _is_blocked(page_text):
            log("[warn] block/captcha detected — waiting 30s then retrying once")
            _close_devtools(log)
            _close_tab(log)
            time.sleep(30)
            webbrowser.open(page_url)
            time.sleep(page_load_wait + 5)
            _open_devtools(log)
            page_text = _run_js(JS_PAGE_TEXT, log)
            if _is_blocked(page_text):
                log("[error] still blocked — skipping this URL")
                _close_devtools(log)
                _close_tab(log)
                break

        # Get total provider count once from page 1
        if page == 1:
            raw_total = _run_js(JS_GET_TOTAL, log)
            try:
                total_results = int(raw_total.strip())
                log(f"[page 1] total providers reported: {total_results}")
            except (ValueError, TypeError):
                log(f"[page 1] could not parse total from: {raw_total!r}")

        # Extract providers
        raw = _run_js(JS_EXTRACT, log)
        _close_devtools(log)
        _close_tab(log)

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            log(f"[page {page}] JSON parse failed — stopping")
            break

        page_providers = data.get("providers") or []
        collected = len(all_providers) + len(page_providers)
        log(f"[page {page}] {len(page_providers)} providers | collected {collected}/{total_results or '?'}")

        if not page_providers:
            log(f"[page {page}] no providers found — stopping pagination")
            break

        for prov in page_providers:
            prov["Source URL"] = page_url
            prov["Source"] = SOURCE_NAME

        all_providers.extend(page_providers)

        # Stop conditions
        if max_pages > 0 and page >= max_pages:
            log(f"[page {page}] --max-pages limit reached")
            break
        if total_results is not None and len(all_providers) >= total_results:
            log(f"[page {page}] collected {len(all_providers)}/{total_results} — done")
            break

        page += 1
        pause = delay_between_pages + random.uniform(0, 2)
        log(f"sleeping {pause:.1f}s...")
        time.sleep(pause)

        if page % 5 == 0:
            batch = random.randint(30, 60)
            log(f"[batch pause] {batch}s...")
            time.sleep(batch)

    return all_providers


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

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(subset=["name", "address"]).reset_index(drop=True)
    df = df.drop_duplicates(subset=["profile_url"]).reset_index(drop=True)

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
    delay_between_pages: float = 4.0,
    max_pages: int = 0,
    fmt: str = "both",
    callback: Optional[Callable] = None,
) -> bool:
    log = callback if callable(callback) else print
    timestamp = datetime.now().strftime("%Y_%m_%d_%H_%M_%S")

    urls: list[str] = []
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
    log("  ZocDoc Scraper (DevTools/JS probe)")
    log(f"  URLs          = {len(urls)}")
    log(f"  page_wait     = {page_load_wait}s  (+0-3s jitter)")
    log(f"  delay         = {delay_between_pages}s  (+0-2s jitter)")
    log(f"  max_pages     = {'unlimited' if max_pages <= 0 else max_pages}")
    log(f"  format        = {fmt}")
    log(f"  started_at    = {datetime.now().isoformat(timespec='seconds')}")
    log("=" * 60)

    all_rows: list[dict] = []
    try:
        for idx, u in enumerate(urls, 1):
            log(f"\n[{idx}/{len(urls)}] {u}")
            try:
                rows = scrape_url(
                    url=u,
                    page_load_wait=page_load_wait,
                    delay_between_pages=delay_between_pages,
                    max_pages=max_pages,
                    log=log,
                )
                log(f"[{idx}/{len(urls)}] {len(rows)} providers collected")
                all_rows.extend(rows)
            except Exception as exc:
                log(f"[{idx}/{len(urls)}] ERROR scraping {u} — {exc} — skipping")

            if idx < len(urls):
                pause = random.randint(5, 15)
                log(f"[inter-url pause] {pause}s...")
                time.sleep(pause)

    except KeyboardInterrupt:
        log("[run] interrupted")

    log(f"\n[run] total providers collected = {len(all_rows)}")

    if not all_rows:
        return True

    # Dedup across all collected providers
    df = pd.DataFrame(all_rows)
    df = df.drop_duplicates(subset=["name", "address"]).reset_index(drop=True)
    df = df.drop_duplicates(subset=["profile_url"]).reset_index(drop=True)
    log(f"[run] {len(df)} unique providers after dedup")

    # Enrich each unique profile_url with office location via profile scraper
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from zocdoc_profile_scraper import scrape_profile as _scrape_profile

    profile_urls = [u for u in df["profile_url"].dropna().tolist() if u]
    log(f"[run] enriching {len(profile_urls)} profiles via profile scraper...")

    profile_data: list[dict] = []
    for i, purl in enumerate(profile_urls, 1):
        log(f"\n[profile {i}/{len(profile_urls)}] {purl}")
        locs = _scrape_profile(url=purl, page_load_wait=page_load_wait, log=log)
        if locs:
            profile_data.append({
                "profile_url": purl,
                "company_name": locs[0].get("company_name", ""),
                "company_address": locs[0].get("company_address", ""),
            })
        if i < len(profile_urls):
            pause = random.randint(5, 15)
            log(f"[inter-profile pause] {pause}s...")
            time.sleep(pause)

    if profile_data:
        profile_df = pd.DataFrame(profile_data)
        df = df.merge(profile_df, on="profile_url", how="left")
        log(f"[run] merged {len(profile_data)} profile enrichment(s)")

    write_output(df.to_dict("records"), f"zocdoc_enriched_{timestamp}", fmt, log)
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Scrape ZocDoc provider listings via DevTools JS injection.",
    )
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--url",
        help="Single ZocDoc listing URL.",
    )
    group.add_argument(
        "--urls-file",
        help="Text file of ZocDoc URLs, one per line "
             "(output of zocdoc_url_extractor.py).",
    )
    p.add_argument(
        "--format", default="both",
        choices=["csv", "xlsx", "excel", "both"],
    )
    p.add_argument(
        "--page-load-wait", type=int, default=8,
        help="Base seconds to wait after opening a page. Default: 8.",
    )
    p.add_argument(
        "--delay", type=float, default=4.0,
        help="Base seconds between pages. Default: 4.0.",
    )
    p.add_argument(
        "--max-pages", type=int, default=0,
        help="Per-URL page cap (0 = use total-results count). Default: 0.",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_argparser().parse_args(argv)
    ok = run(
        url=getattr(args, "url", None),
        urls_file=getattr(args, "urls_file", None),
        page_load_wait=args.page_load_wait,
        delay_between_pages=args.delay,
        max_pages=args.max_pages,
        fmt=args.format,
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
