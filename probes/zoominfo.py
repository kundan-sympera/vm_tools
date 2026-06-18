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

try:
    import winreg
    _WINDOWS = True
except ImportError:
    _WINDOWS = False

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
#  Connection detection
# ─────────────────────────────────────────────

def get_wifi_adapter_name() -> Optional[str]:
    """Returns WiFi adapter name on Windows (via netsh), None on Linux."""
    result = subprocess.run("netsh wlan show interfaces", shell=True, capture_output=True, text=True)
    match = re.search(r"^\s*Name\s*:\s*(.+)$", result.stdout, re.MULTILINE)
    return match.group(1).strip() if match else None


def get_current_wifi_name() -> Optional[str]:
    result = subprocess.run("netsh wlan show interfaces", shell=True, capture_output=True, text=True)
    match = re.search(r"^\s*SSID\s*:\s*(.+)$", result.stdout, re.MULTILINE)
    return match.group(1).strip() if match else None


def get_lan_adapter_name() -> Optional[str]:
    """Returns the default network interface on Linux (via ip route)."""
    result = subprocess.run("ip route show default", shell=True, capture_output=True, text=True)
    match = re.search(r"dev\s+(\S+)", result.stdout)
    return match.group(1) if match else None


# ─────────────────────────────────────────────
#  MAC randomization
# ─────────────────────────────────────────────

def _random_mac() -> str:
    """Random locally-administered unicast MAC with colons (e.g. 02:A1:B2:C3:D4:E5)."""
    mac = [random.randint(0x00, 0xFF) for _ in range(6)]
    mac[0] = (mac[0] & 0xFE) | 0x02
    return ":".join(f"{b:02X}" for b in mac)


def _randomize_mac_windows(adapter_name: str, mac: str) -> bool:
    net_base  = r"SYSTEM\CurrentControlSet\Control\Class\{4D36E972-E325-11CE-BFC1-08002BE10318}"
    conn_base = r"SYSTEM\CurrentControlSet\Control\Network\{4D36E972-E325-11CE-BFC1-08002BE10318}"
    mac_plain = mac.replace(":", "")
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, net_base) as base:
            for i in range(winreg.QueryInfoKey(base)[0]):
                sub = winreg.EnumKey(base, i)
                path = f"{net_base}\\{sub}"
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path, 0,
                                        winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
                        try:
                            guid = winreg.QueryValueEx(k, "NetCfgInstanceId")[0]
                        except FileNotFoundError:
                            continue
                        try:
                            conn_path = f"{conn_base}\\{guid}\\Connection"
                            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, conn_path) as ck:
                                name = winreg.QueryValueEx(ck, "Name")[0]
                            if name.lower() != adapter_name.lower():
                                continue
                        except (FileNotFoundError, OSError):
                            continue
                        winreg.SetValueEx(k, "NetworkAddress", 0, winreg.REG_SZ, mac_plain)
                        return True
                except (PermissionError, OSError):
                    continue
    except Exception as exc:
        print(f"[MAC] Registry error: {exc}")
    return False


def _randomize_mac_linux(adapter_name: str, mac: str) -> bool:
    subprocess.run(f"sudo ip link set dev {adapter_name} down", shell=True, check=False)
    r = subprocess.run(f"sudo ip link set dev {adapter_name} address {mac}", shell=True, check=False)
    subprocess.run(f"sudo ip link set dev {adapter_name} up", shell=True, check=False)
    return r.returncode == 0


def randomize_mac(adapter_name: str, windows: bool) -> bool:
    mac = _random_mac()
    if windows:
        ok = _randomize_mac_windows(adapter_name, mac)
    else:
        ok = _randomize_mac_linux(adapter_name, mac)
    if ok:
        print(f"[MAC] Randomized to {mac}")
    else:
        print(f"[MAC] Could not set MAC for '{adapter_name}'")
    return ok


# ─────────────────────────────────────────────
#  Reconnect helpers
# ─────────────────────────────────────────────

def wifi_reconnect(adapter_name: str) -> None:
    ssid = get_current_wifi_name()
    print(f"[WIFI] Reconnecting '{adapter_name}' to: {ssid}")
    subprocess.run(f'netsh interface set interface name="{adapter_name}" admin=DISABLED',
                   shell=True, check=False)
    time.sleep(3)
    subprocess.run(f'netsh interface set interface name="{adapter_name}" admin=ENABLED',
                   shell=True, check=False)
    time.sleep(3)
    if ssid:
        subprocess.run(f'netsh wlan connect name="{ssid}"', shell=True, check=False)


def lan_reconnect(adapter_name: str) -> None:
    print(f"[LAN] Reconnecting '{adapter_name}'")
    time.sleep(2)
    # interface is already up after MAC randomization — just renew DHCP lease
    for client, cmd in [
        ("nmcli",    f"nmcli dev reapply {adapter_name}"),
        ("dhcpcd",   f"sudo dhcpcd {adapter_name}"),
        ("udhcpc",   f"sudo udhcpc -i {adapter_name}"),
        ("dhclient", f"sudo dhclient {adapter_name}"),
    ]:
        if subprocess.run(f"which {client}", shell=True, capture_output=True).returncode == 0:
            print(f"[LAN] Using {client} for DHCP")
            subprocess.run(cmd, shell=True, check=False)
            break
    else:
        print("[LAN] No DHCP client found — interface is up, OS may handle renewal automatically")


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
    wifi_adapter = get_wifi_adapter_name()  # returns None on Linux
    on_windows   = wifi_adapter is not None

    if on_windows:
        randomize_mac(wifi_adapter, windows=True)
        wifi_reconnect(wifi_adapter)
    else:
        lan_adapter = get_lan_adapter_name()
        if lan_adapter:
            randomize_mac(lan_adapter, windows=False)
            lan_reconnect(lan_adapter)
        else:
            print("[NETWORK] No active adapter detected — skipping reconnect")

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
        try:
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
        except Exception as exc:
            log(f"[{t}/{len(urls)}] ERROR — {exc} — skipping URL template")

    log(f"[DONE] Total rows: {total_rows} → {output_file}")
    return total_rows