"""
probes/zoominfo.py
ZoomInfo scraper logic — importable by scraper.py or run standalone.
"""

import os
import re
import random
import subprocess
import time
import webbrowser
from datetime import datetime
from io import StringIO
from typing import List, Optional

import pandas as pd
import pyautogui
import pyperclip

from probes._common import open_console, close_console

# ─────────────────────────────────────────────
#  JS snippets
# ─────────────────────────────────────────────

HTML_ALL_TEXT_CODE = r"""
const allText = document.body.innerText;
const textArea = document.createElement("textarea");
textArea.value = allText;
textArea.style.position = "fixed";
textArea.style.left = "-999999px";
textArea.style.top = "-999999px";
document.body.appendChild(textArea);
textArea.focus();
textArea.select();
try { document.execCommand("copy"); } catch(e) {}
document.body.removeChild(textArea);
"""

CSV_EXTRACT_CODE = r"""
(() => {
  const clean = (s) => (s || "").replace(/\s+/g, " ").trim();
  const esc = (s) => `"${clean(s).replace(/"/g, '""')}"`;
  const rows = [...document.querySelectorAll(".results-table-row")]
    .filter(row => !row.classList.contains("header-row"));
  const headers = ["page_url","company_name","industry","location","revenue","employees"];
  const data = rows.map(row => {
    const parts = row.innerText.split(/\n|\t/).map(clean).filter(Boolean);
    return {
      page_url: location.href,
      company_name: parts[0] || "",
      industry: parts[1] || "",
      location: parts[2] || "",
      revenue: parts[3] || "",
      employees: parts[4] || ""
    };
  }).filter(r => r.company_name);
  const csv = [headers.join(","), ...data.map(row => headers.map(h => esc(row[h])).join(","))].join("\n");
  const textarea = document.createElement("textarea");
  textarea.value = csv;
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
})();
"""

# ─────────────────────────────────────────────
#  URL builder
# ─────────────────────────────────────────────

INDUSTRIES = [
    "manufacturing-chemicals",
    "manufacturing",
    "construction-management",
    "construction",
    "transportation-rail-and-bus",
    "transportation",
    "transportation-freight",
    "manufacturing-appliances",
    "manufacturing-electronics",
]

BASE_URL = "https://www.zoominfo.com/companies-search/location-usa--{state}--{city}-industry-{industry}?pageNum={{page}}"


def build_urls(cities: List[dict], industries: List[str]) -> List[str]:
    """
    cities: list of {"state": "indiana", "city": "gary"}
    industries: list of industry slugs
    Returns list of URL templates with {page} placeholder.
    """
    urls = []
    for c in cities:
        for ind in industries:
            url = BASE_URL.format(
                state=c["state"].lower().replace(" ", "-"),
                city=c["city"].lower().replace(" ", "-"),
                industry=ind,
            )
            urls.append(url)
    return urls


def parse_city_input(raw: str) -> List[dict]:
    """
    Accepts lines like:
        indiana, gary
        wisconsin, kenosha
    Returns list of {"state": ..., "city": ...}
    """
    cities = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) >= 2:
            cities.append({"state": parts[0], "city": parts[1]})
    return cities


# ─────────────────────────────────────────────
#  Block / captcha detection
# ─────────────────────────────────────────────

def human_verification_detected(text: str) -> bool:
    text = str(text).lower()
    return any(w in text for w in ["press & hold to confirm", "confirm you are a human"])


def rate_limit_detected(text: str) -> bool:
    text = str(text).lower()
    return any(w in text for w in [
        "you are being rate limited",
        "has banned you temporarily from accessing this website",
    ])


# ─────────────────────────────────────────────
#  Wi-Fi reconnect
# ─────────────────────────────────────────────

def get_current_wifi_name() -> Optional[str]:
    result = subprocess.run("netsh wlan show interfaces", shell=True, capture_output=True, text=True)
    match = re.search(r"^\s*SSID\s*:\s*(.+)$", result.stdout, re.MULTILINE)
    return match.group(1).strip() if match else None


def wifi_reconnect():
    wifi = get_current_wifi_name()
    print(f"[WIFI] Reconnecting to: {wifi}")
    subprocess.run("netsh wlan disconnect", shell=True, check=False)
    time.sleep(5)
    subprocess.run(f'netsh wlan connect name="{wifi}"', shell=True, check=False)


# ─────────────────────────────────────────────
#  Browser helpers
# ─────────────────────────────────────────────

def handle_human_verification():
    print("[STATUS] Human verification detected")
    open_console()
    pyautogui.moveTo(1919, 1180, duration=0.5)
    pyautogui.mouseDown(button="left")
    time.sleep(random.randint(12, 15))
    pyautogui.mouseUp(button="left")
    time.sleep(5)
    close_console()


def handle_rate_limit():
    print("[STATUS] Rate limit detected")
    wifi_reconnect()
    pyautogui.hotkey("ctrl", "r")
    time.sleep(random.randint(3, 6))
    open_console()
    close_console()


def copy_page_text() -> str:
    open_console()
    time.sleep(random.randint(1, 3))
    pyperclip.copy(HTML_ALL_TEXT_CODE)
    pyautogui.hotkey("ctrl", "shift", "v")
    pyautogui.press("enter")
    time.sleep(random.randint(1, 3))
    return pyperclip.paste()


def extract_csv() -> str:
    pyperclip.copy(CSV_EXTRACT_CODE)
    pyautogui.hotkey("ctrl", "shift", "v")
    pyautogui.press("enter")
    time.sleep(random.randint(1, 3))
    return pyperclip.paste()


# ─────────────────────────────────────────────
#  Core scrape logic
# ─────────────────────────────────────────────

def scrape(
    urls: List[str],
    output_file: str,
    max_pages: int = 5,
    min_companies: int = 9,
    log=print,
) -> int:
    """
    Scrapes all url templates (each containing {page}) up to max_pages.
    Appends rows incrementally to output_file (CSV).
    Returns total rows written.
    """
    output_columns = None
    total_rows = 0
    pages_fetched = 0

    os.makedirs(os.path.dirname(output_file) or ".", exist_ok=True)

    for t, url_template in enumerate(urls, 1):
        log(f"[{t}/{len(urls)}] {url_template}")

        for page in range(1, max_pages + 1):
            url = url_template.format(page=page)
            pages_fetched += 1

            webbrowser.open(url)
            time.sleep(random.randint(5, 9))

            page_text = copy_page_text()

            if human_verification_detected(page_text):
                handle_human_verification()
            if rate_limit_detected(page_text):
                handle_rate_limit()

            csv_text = extract_csv()
            pyautogui.hotkey("ctrl", "w")

            # parse
            rows_this_page = None
            try:
                df = pd.read_csv(StringIO(csv_text.strip()))
                if "company_name" in df.columns:
                    file_exists = os.path.exists(output_file)
                    if output_columns is None:
                        output_columns = list(df.columns)
                    else:
                        df = df.reindex(columns=output_columns)
                    df.to_csv(output_file, mode="a", header=not file_exists, index=False)
                    rows_this_page = len(df)
                    total_rows += rows_this_page
                    log(f"  page {page}: {rows_this_page} rows (total {total_rows})")
            except Exception as e:
                log(f"  page {page}: parse error — {e}")

            # batch pause every 9 pages
            if pages_fetched % 9 == 0:
                wait = random.randint(60, 120)
                log(f"  batch pause {wait}s …")
                time.sleep(wait)

            if rows_this_page is None or rows_this_page < min_companies:
                break

    log(f"[DONE] Total rows: {total_rows} → {output_file}")
    return total_rows