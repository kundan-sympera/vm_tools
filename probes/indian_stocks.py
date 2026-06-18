"""
probes/indian_stocks.py
StockEdge sector scraper logic — importable by scraper.py or run standalone.
"""

import time
import webbrowser
from datetime import datetime
from typing import List

import pandas as pd
import pyautogui
import pyperclip

from probes._common import open_console, close_console

# ─────────────────────────────────────────────
#  JS snippets
# ─────────────────────────────────────────────

GAINERS_CODE = r"""
const lines = document.body.innerText.split('\n').map(x => x.trim()).filter(Boolean);
const tableStarts = [];
for (let i = 0; i < lines.length; i++) {
  if (lines[i]==='Stock Name'&&lines[i+1]==='LTP'&&lines[i+2]==='Chg'&&lines[i+3]==='Chg %'&&lines[i+4]==='Last Update')
    tableStarts.push(i);
}
const start = tableStarts[0];
const end = tableStarts[1] || lines.length;
const rows = lines.slice(start + 5, end);
const names = [];
for (let i = 0; i < rows.length - 4; i++) {
  const name=rows[i],ltp=rows[i+1],chg=rows[i+2],chgPct=rows[i+3],lastUpdate=rows[i+4];
  if (/^[A-Za-z0-9&().,''\-\s]+$/.test(name)&&/^[\d,]+(\.\d+)?$/.test(ltp)&&/^[+-]?[\d,]+(\.\d+)?$/.test(chg)&&/^\d+(\.\d+)?%$/.test(chgPct)&&/^\d{2}:\d{2}:\d{2}\s*(am|pm)$/i.test(lastUpdate))
    { names.push(name); i+=4; }
}
copy([...new Set(names)].join('\n'));
"""

LOSERS_CODE = r"""
const lines = document.body.innerText.split('\n').map(x => x.trim()).filter(Boolean);
const tableStarts = [];
for (let i = 0; i < lines.length; i++) {
  if (lines[i]==='Stock Name'&&lines[i+1]==='LTP'&&lines[i+2]==='Chg'&&lines[i+3]==='Chg %'&&lines[i+4]==='Last Update')
    tableStarts.push(i);
}
const start = tableStarts[1];
const end = lines.findIndex((x, i) => i > start && x === 'Date Wise');
const rows = lines.slice(start + 5, end > start ? end : lines.length);
const names = [];
for (let i = 0; i < rows.length - 4; i++) {
  const name=rows[i],ltp=rows[i+1],chg=rows[i+2],chgPct=rows[i+3],lastUpdate=rows[i+4];
  if (/^[A-Za-z0-9&().,''\-\s]+$/.test(name)&&/^[\d,]+(\.\d+)?$/.test(ltp)&&/^[+-]?[\d,]+(\.\d+)?$/.test(chg)&&/^\d+(\.\d+)?%$/.test(chgPct)&&/^\d{2}:\d{2}:\d{2}\s*(am|pm)$/i.test(lastUpdate))
    { names.push(name); i+=4; }
}
copy([...new Set(names)].join('\n'));
"""

# ─────────────────────────────────────────────
#  Catalogue  (kept in sync with constants.py)
# ─────────────────────────────────────────────

from constants import sectors as ALL_SECTORS, section as ALL_SECTIONS, time_period as ALL_PERIODS, build_sector_url


# ─────────────────────────────────────────────
#  Core scrape logic
# ─────────────────────────────────────────────

def scrape(
    sectors: List[str],
    sections: List[str],
    periods: List[str],
    output_file: str,
    log=print,
) -> int:
    """
    Scrapes the chosen sectors × sections × periods matrix.
    Saves results to output_file (CSV).
    Returns total rows written.
    """
    rows = []

    total = len(sectors) * len(sections) * len(periods)
    done = 0

    for sector in sectors:
        for section in sections:
            for period in periods:
                done += 1
                url = build_sector_url(sector, section, period)
                log(f"[{done}/{total}] {sector} / {section} / {period}")

                webbrowser.open(url)
                time.sleep(4)

                pyautogui.moveTo(x=2274, y=2040, duration=0.5)
                for _ in range(5):
                    pyautogui.scroll(-1000)
                    time.sleep(0.5)

                open_console()
                time.sleep(1)

                code = GAINERS_CODE if section == "sector-gainers" else LOSERS_CODE
                pyperclip.copy(code)
                pyautogui.hotkey("ctrl", "shift", "v")
                time.sleep(0.5)
                pyautogui.press("enter")
                time.sleep(1)

                stocks = [s.strip() for s in pyperclip.paste().split("\n") if s.strip()]
                log(f"  → {len(stocks)} stocks")

                for stock in stocks:
                    rows.append({
                        "sector": sector,
                        "section": section,
                        "period": period,
                        "stock_name": stock,
                    })

                pyautogui.hotkey("ctrl", "w")

    df = pd.DataFrame(rows, columns=["sector", "section", "period", "stock_name"])
    df.to_csv(output_file, index=False)
    log(f"[DONE] {len(df)} rows → {output_file}")
    return len(df)