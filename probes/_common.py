"""
Shared Selenium helpers for the scrapers in this folder.

Everything in `scraper/` is self-contained - this module is the ONLY
place driver / page-fetch logic should live. Source scrapers
(`lawinfo_scraper.py`, `bcg_scraper.py`, ...) should import from here
and nothing else outside the folder.
"""

from __future__ import annotations

import json
import re
import time
from typing import Iterable, List, Optional
import pyautogui

def open_console() -> None:
    pyautogui.press("f12")


def close_console() -> None:
    pyautogui.press("f12")

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

try:
    from webdriver_manager.chrome import ChromeDriverManager
    _USE_WEBDRIVER_MANAGER = True
except ImportError:
    _USE_WEBDRIVER_MANAGER = False


DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def build_driver(headless: bool = True) -> webdriver.Chrome:
    """Create a Chrome WebDriver with sane anti-detection defaults."""
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--window-size=1920,1080")
    options.add_argument(f"user-agent={DEFAULT_USER_AGENT}")

    if _USE_WEBDRIVER_MANAGER:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {
            "source": (
                "Object.defineProperty(navigator, 'webdriver', "
                "{get: () => undefined})"
            )
        },
    )
    return driver


def get_soup(
    driver: webdriver.Chrome,
    url: str,
    wait_seconds: int = 5,
    wait_selector: str = "h1, h2, a",
    timeout: int = 15,
    callback=None,
) -> Optional[BeautifulSoup]:
    """Navigate to `url`, wait for `wait_selector`, return the parsed
    BeautifulSoup. Returns None on timeout / driver error and logs via
    `callback` (or print) without raising.
    """
    log = callback if callable(callback) else print
    try:
        driver.get(url)
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
        )
        if wait_seconds > 0:
            time.sleep(wait_seconds)
        return BeautifulSoup(driver.page_source, "html.parser")
    except TimeoutException:
        log(f"  [warn] timeout loading {url}")
        return None
    except Exception as e:
        log(f"  [warn] error loading {url}: {e}")
        return None


def build_page_url(base_url: str, page: int) -> str:
    """Append `?page=N` (or `&page=N` if `?` already present). Page 1
    returns the base URL unchanged.
    """
    if page <= 1:
        return base_url
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}page={page}"


def detect_total_pages(
    soup: BeautifulSoup,
    cap: int = 50,
) -> int:
    """Find the largest `?page=N` (or `&page=N`) number referenced by any
    anchor href on the page. Returns 1 when no pagination is visible.
    Capped at `cap` to defend against pathological pages.
    """
    max_page = 1
    page_re = re.compile(r"[?&]page=(\d+)")
    for a in soup.find_all("a", href=True):
        match = page_re.search(a["href"])
        if not match:
            continue
        try:
            n = int(match.group(1))
        except ValueError:
            continue
        if n > max_page:
            max_page = n
    return min(max_page, cap)


def extract_jsonld(soup: BeautifulSoup) -> List[dict]:
    """Parse every ``<script type="application/ld+json">`` block on the page.

    Returns a flat list of dicts. Top-level arrays are flattened; invalid JSON
    blocks are silently skipped. Useful for ZoomInfo / BCG-style pages that
    embed structured data (Organization, ItemList, FAQPage, ...).
    """
    out: List[dict] = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text() or ""
        raw = raw.strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    out.append(item)
        elif isinstance(data, dict):
            out.append(data)
    return out


def collect_jsonld_by_type(
    blocks: Iterable[dict], type_name: str
) -> List[dict]:
    """Return JSON-LD blocks whose ``@type`` matches ``type_name``."""
    matches: List[dict] = []
    for b in blocks:
        t = b.get("@type")
        if isinstance(t, str) and t.lower() == type_name.lower():
            matches.append(b)
        elif isinstance(t, list) and any(
            isinstance(x, str) and x.lower() == type_name.lower() for x in t
        ):
            matches.append(b)
    return matches


def slugify(value: str) -> str:
    """Normalize a value into a URL- and filename-safe slug.

    Lower-cases, collapses any run of non-`[a-z0-9-]` characters into a
    single hyphen, and trims leading/trailing hyphens. Hyphens that the
    user already typed (e.g. `family-law`, `south-dakota`, `rapid-city`)
    are preserved so the slug works directly in LawInfo URLs.

    Examples:
        slugify("Family Law")    -> "family-law"
        slugify("family-law")    -> "family-law"
        slugify(" South Dakota") -> "south-dakota"
        slugify("south-dakota")  -> "south-dakota"
    """
    value = (value or "").strip().lower()
    value = re.sub(r"[^a-z0-9-]+", "-", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-") or "unknown"
