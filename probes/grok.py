"""
probes/grok.py — Grok probe
Opens Grok once, sets a system prompt, then iterates a list of companies
and returns scraped details for each.

Public API
----------
scrape(companies: list[dict], system_prompt: str | None) -> list[dict]

Each input dict must have:  pool_id, pool_id_link, validated_name, validated_address
Each output dict has:       pool_id, pool_id_link, validated_name, validated_address, details, status
"""

import time
import webbrowser

import pyautogui
import pyperclip

import screen_positions  # must expose GROK_COPY_1080p (with .x / .y)
from utils.db import get_conn, get_details, save_details

# ─────────────────────────────────────────────
#  Constants
# ─────────────────────────────────────────────

DEFAULT_SYSTEM_PROMPT = """
Please help me to answer the following questions for the company provided as input:
The company’s main location, if you are not sure answer NA.
Is the company’s physical headquarters/office address located within the following counties? (Ignore service areas/areas served): Yes / No"
Priority Locations: Nassau/Queens  NY , Nassau/Suffolk County Long Island, Westchester County, Bergen County, NJ
Public Official Links: (for this first verify that the links work and is active)
•	Website:
•	LinkedIn:
•	Other relevant links:

Founded Year:
Employee count: (tightened range which is as accurate as possible for the company)
does the company have alternative names, DBA , previous names? [We need this for the UCC]
Company ownership: Subsidiary, private, family-owned business, Private-Equity Backed
Is it a public company?
Is the company a subsidiary or a division of another company
Is the company a subsidiary of a foreign company
Is this company working with the government and wins federal contracts?
Is the company active?
Revenue:
Use multiple methods to estimate revenue and provide a summary, first do research online and try to fine links like zoominfo or others which have revenue, else try to get an estimation based on data you are able to fine, and in 3rd step use the employee based model provided below to estimate revenue a third way, combine all 3 to get a more accurate data.

The company revenue estimation, the range is fine. 
Also use the following ranges for revenue <1M$, 1-3M$, 3-5M$, 5-20M$,20-30M$, ,30-50M$, 50-100M$, 100-130M$, >130M$, clear distinction between 5-30M$, 30-50M is required, same goes for 100-130M$ and >130M$,
Try to provide proof If there are conflicts, present two estimations
Employes based model: (see that the avg rpe is based on NY/NJ if the company belongs to another city and state use the values accordingly based on that city for Avg RPE)
Industry	$1M – $3M Revenue (Headcount)	$3M – $6M Revenue (Headcount)	Avg. RPE (NY/NJ)
Legal Services (Boutique)	3 – 10 employees	10 – 22 employees	~$275k – $325k
Management Consulting	4 – 11 employees	11 – 22 employees	~$265k
IT / Systems Consulting	5 – 13 employees	13 – 26 employees	~$230k
Engineering Services	4 – 12 employees	12 – 24 employees	~$250k
Architectural Services	5 – 14 employees	14 – 28 employees	~$215k
Accounting / CPA Firms	6 – 16 employees	16 – 32 employees	~$185k
Marketing / Ad Agencies	6 – 18 employees	18 – 35 employees	~$170k
HR / Recruiting (Perm)	4 – 10 employees	10 – 20 employees	~$300k
Staffing Firms (Contract)	8 – 24 employees	24 – 48 employees	~$125k
Other Professional Services	5 – 14 employees	14 – 28 employees	~$215k
Manufacturing	3 – 9 employees	9 – 18 employees	~$330k
E-commerce	2 – 6 employees	6 – 12 employees	~$500k
Wholesale	2 – 5 employees	5 – 10 employees	~$600k
Trade Services	7 – 20 employees	20 – 40 employees	~$150k
Healthcare & Life Sciences	3 – 8 employees	8 – 16 employees	~$375k

Industry type:
Please provide the industry type for the company and if it is a focus company, for example :  Manufacturing, Consumer products, Industrial services, Specialty distribution, oil and gas exploration and production, third-party logistics.
Our focus is:
Professional Services
Manufacturing
E-Commerce
Wholesale
Trade Services
Healthcare & Life Sciences

 Or suggest another type if nothing matches.

do you identify any growth signals and why? 
any ranking or awards, examples:
included in superlawyers profiles.superlawyers.com
Included in Award Confirmation (Spartan Tool): Pro of the Month: Richard Sachs - Spartan Tool	
Or 
Avvo Client’s Choice Award for 2025. T

High rating 
for example
High rating in google (more then 4.5)
For example: High Rating (Google): Holds a 5.0-star rating , 160 reviews with consistent praise for handling "medically complex" and "anxious" children.
Other rating examples:
https://www.houzz.com/professionals/architects-and-building-designers/g-g-architects-pfvwus-pf~1291986037


Official HomeAdvisor Profile: Drain Away Sewer Service Inc. - HomeAdvisor
Angi (formerly Angie's List) Profile: Drain Away Sewer Service Inc. - Angi
If any one of the doctors  is included in a top list for example : "top dentist" lists

Union Affiliation 
for example :: The company is a signatory with the New York City District Council of Carpenters, indicating a high-capacity workforce capable of handling large-scale commercial union jobs. Source: CCA Metro

Community Leadership:
For example :  The firm is an active donor to local academic funds and a long-standing member of the Meadowlands Chamber. Source: Meadowlands Chamber Directory

 For every growth signal, award, or rating mentioned, provide a direct URL link to the source (e.g., the Angi profile, the SuperLawyers listing, or the official press release).
 Verification Rule: Do not include a signal if you cannot provide a functioning link to verify it. If a link is not available, list the signal as "Unverified" or omit it.

Always format links in Markdown as [descriptive link text](full URL) for clickable hyperlinks. Do not use inline citations like [web:xx] or plain URLs without text.
"""

# Seconds to wait after opening Grok before typing
BROWSER_OPEN_WAIT = 10

# Seconds to wait for Grok to respond to the system prompt
SYSTEM_PROMPT_WAIT = 30

# Seconds to wait for Grok to respond to each company query
COMPANY_QUERY_WAIT = 45

# Seconds to wait after clicking the copy button
COPY_WAIT = 2

# Seconds to wait after click
CLICK_WAIT = 0.5

# Seconds between companies (let UI settle)
BETWEEN_COMPANY_WAIT = 2

# Number of companies to scrape before resetting the Grok session
BATCH_SIZE = 5

# Seconds to wait after closing the tab before reopening Grok
SESSION_RESET_WAIT = 30

GROK_URL = "https://grok.com/"


# ─────────────────────────────────────────────
#  Internal helpers
# ─────────────────────────────────────────────

def _type(text: str, interval: float = 0.05) -> None:
	"""Type text safely — pyautogui.typewrite only handles ASCII,
	so we fall back to clipboard paste for anything else."""
	try:
		text.encode("ascii")
		pyautogui.typewrite(text, interval=interval)
	except UnicodeEncodeError:
		pyperclip.copy(text)
		pyautogui.hotkey("ctrl", "v")


def _move_to_input() -> None:
	""" after successfulyl copying move to input"""
	pyautogui.moveTo(
		screen_positions.GROK_INPUT_1080p.x,
		screen_positions.GROK_INPUT_1080p.y,
	)
	pyautogui.click()
	time.sleep(CLICK_WAIT)

def _move_to_base_input() -> None:
	""" after successfulyl copying move to input"""
	pyautogui.moveTo(
		screen_positions.GROK_BASE_INPUT_1080p.x,
		screen_positions.GROK_BASE_INPUT_1080p.y,
	)
	pyautogui.click()
	time.sleep(CLICK_WAIT)


def _copy_response() -> str:
	"""Click the Grok copy button and return clipboard contents."""
	
	pyperclip.copy("check")
	
	pyautogui.moveTo(
		screen_positions.GROK_COPY_3R_1080p.x,
		screen_positions.GROK_COPY_3R_1080p.y,
	)
	
	pyautogui.click()
	time.sleep(COPY_WAIT)
	
	if pyperclip.paste() == "check":
	
		pyautogui.moveTo(
			screen_positions.GROK_COPY_2R_1080p.x,
			screen_positions.GROK_COPY_2R_1080p.y,
		)
		
		pyautogui.click()
		time.sleep(COPY_WAIT)
	
	return pyperclip.paste().strip()


def _open_grok_with_system_prompt(system_prompt: str) -> None:
	"""Open Grok in the browser and submit the system/context prompt."""
	webbrowser.open(GROK_URL)
	time.sleep(BROWSER_OPEN_WAIT)

	# Dismiss any splash / cookie banners
	pyautogui.press("esc")
	time.sleep(0.5)
	
	_move_to_base_input()

	_type(system_prompt)
	time.sleep(0.3)
	pyautogui.press("enter")
	time.sleep(SYSTEM_PROMPT_WAIT)


def _query_company(company_name: str, company_address: str) -> str:
	"""Type a company query and return Grok's response text."""
	query = f"{company_name} {company_address}"
	
	_move_to_input()
	
	_type(query)
	time.sleep(0.3)
	pyautogui.press("enter")
	time.sleep(COMPANY_QUERY_WAIT)
	return _copy_response()


# ─────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────

def scrape(
	companies: list[dict],
	system_prompt: str | None = None,
) -> list[dict]:
	"""
	Open Grok once, send the system prompt, then query each company.

	Parameters
	----------
	companies : list of dicts with keys  pool_id, pool_id_link, validated_name, validated_address
	system_prompt : override the default prompt (optional)

	Returns
	-------
	list of dicts:  pool_id, pool_id_link, validated_name, validated_address, details, status
	"""
	if not companies:
		return []

	prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
	results_by_idx: dict[int, dict] = {}

	# ── DB connection (best-effort; scraper still works without it) ──
	conn = None
	try:
		conn = get_conn()
	except Exception as exc:
		print(f"[grok] DB unavailable, cache disabled: {exc}")

	# ── Phase 1: resolve cache hits ──
	to_scrape: list[tuple[int, dict]] = []
	for idx, row in enumerate(companies):
		pool_id_link = str(row.get("pool_id_link", ""))
		cached = None
		if conn and pool_id_link:
			try:
				cached = get_details(conn, pool_id_link)
			except Exception as exc:
				print(f"[grok] DB read failed for {pool_id_link}: {exc}")

		if cached:
			print(f"[grok] cache hit  — {row.get('validated_name', '')} ({pool_id_link})")
			results_by_idx[idx] = {
				"pool_id":           row.get("pool_id", idx + 1),
				"pool_id_link":      pool_id_link,
				"validated_name":    str(row.get("validated_name", "")).strip(),
				"validated_address": str(row.get("validated_address", "")).strip(),
				"details":           cached,
				"status":            "cached",
			}
		else:
			to_scrape.append((idx, row))

	n_cached = len(results_by_idx)
	n_scrape = len(to_scrape)
	print(f"[grok] {n_cached} cached, {n_scrape} to scrape.")

	# ── Phase 2: batch-scrape the rest ──
	for batch_start in range(0, n_scrape, BATCH_SIZE):
		batch = to_scrape[batch_start : batch_start + BATCH_SIZE]
		batch_num = batch_start // BATCH_SIZE + 1
		batch_end = batch_start + len(batch)

		print(f"[grok] Opening Grok — batch {batch_num} ({batch_start + 1}–{batch_end}/{n_scrape}) …")
		_open_grok_with_system_prompt(prompt)

		for j, (orig_idx, row) in enumerate(batch, 1):
			pool_id           = row.get("pool_id", orig_idx + 1)
			pool_id_link      = str(row.get("pool_id_link", ""))
			validated_name    = str(row.get("validated_name", "")).strip()
			validated_address = str(row.get("validated_address", "")).strip()

			print(f"[grok {batch_start + j}/{n_scrape}] {validated_name} | {validated_address}")

			try:
				details = _query_company(validated_name, validated_address)
				status  = "success" if len(details) > 50 else "partial"
			except Exception as exc:
				details = f"ERROR: {exc}"
				status  = "error"

			if conn and pool_id_link and status != "error":
				try:
					save_details(conn, pool_id, pool_id_link, details)
				except Exception as exc:
					print(f"[grok] DB save failed for {pool_id_link}: {exc}")

			results_by_idx[orig_idx] = {
				"pool_id":           pool_id,
				"pool_id_link":      pool_id_link,
				"validated_name":    validated_name,
				"validated_address": validated_address,
				"details":           details,
				"status":            status,
			}

			if j < len(batch):
				time.sleep(BETWEEN_COMPANY_WAIT)

		pyautogui.hotkey("ctrl", "w")
		print(f"[grok] Batch {batch_num} done — tab closed.")

		if batch_end < n_scrape:
			print(f"[grok] Waiting {SESSION_RESET_WAIT}s before next batch …")
			time.sleep(SESSION_RESET_WAIT)

	if conn:
		try:
			conn.close()
		except Exception:
			pass

	total = len(companies)
	print(f"[grok] Done — {total} companies ({n_cached} cached, {n_scrape} scraped).")
	return [results_by_idx[i] for i in range(total)]
