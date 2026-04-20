"""
fed_scraper.py — Download FOMC documents by constructing URLs directly.

No Selenium required. Strategy:
  1. Collect all FOMC meeting dates from plain-HTML Fed calendar pages
  2. For each date, construct document URLs from known patterns and download
  3. HTTP 200 → save; HTTP 404 → document doesn't exist for that meeting

Confirmed URL patterns (from live site inspection):
  Statement  HTML : /newsevents/pressreleases/monetary{YYYYMMDD}a.htm
  Minutes    PDF  : /monetarypolicy/files/fomcminutes{YYYYMMDD}.pdf
  Minutes    HTML : /monetarypolicy/fomcminutes{YYYYMMDD}.htm  (pre-2005 fallback)
  Press Conf HTML : /monetarypolicy/fomcpresconf{YYYYMMDD}.htm

Coverage:
  Statements   : 2000-02-02 → present
  Minutes      : 2000-02-02 → present  (HTML only before 2005, PDF+HTML after)
  Press Conf   : 2011-04-27 → present  (Chair press conferences, not conference calls)

Usage:
    python fed_scraper.py
    python fed_scraper.py --start-year 2000 --end-year 2026
    python fed_scraper.py --types statements minutes
"""

import argparse
import re
import time
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from utils import (
    BASE_URL,
    HEADERS,
    load_checkpoint,
    make_doc_id,
    save_checkpoint,
    save_raw,
    setup_logging,
)

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT      = Path(__file__).resolve().parent
RAW_ROOT  = ROOT / "data" / "raw"
CKPT_PATH = ROOT / "data" / ".checkpoints" / "scraper.json"
LOG_PATH  = ROOT / "data" / ".checkpoints" / "scraper.log"

# ── URL templates ─────────────────────────────────────────────────────────────
# Listed in priority order — first 200 response wins

URL_TEMPLATES = {
    "statements": [
        "/newsevents/pressreleases/monetary{date}a.htm",          # post-~2011
        "/newsevents/press/monetary/{date}a.htm",                  # ~2006–2011
        "/boarddocs/press/general/{yyyy}/{date}/default.htm",      # ~2000–2005
    ],
    "minutes": [
        "/monetarypolicy/files/fomcminutes{date}.pdf",             # post-2004
        "/monetarypolicy/fomcminutes{date}.htm",                   # ~2005–2006
        "/fomc/minutes/{date}.htm",                                # ~2000–2005
    ],
    "press_conf": [
        "/monetarypolicy/fomcpresconf{date}.htm",
    ],
}

# Press conferences (Chair public Q&A) began April 26-27, 2011
PC_START_DATE = "20110427"


# ── Historical meeting dates (2000–2011) ─────────────────────────────────────
# Hardcoded because the Fed's historical year pages return 404.
# These are all scheduled and emergency FOMC meetings 2000–2011.

HISTORICAL_DATES_2000_2011 = [
    # 2000
    "20000202", "20000321", "20000516", "20000628",
    "20000822", "20001003", "20001115", "20001219",
    # 2001
    "20010103", "20010131", "20010320", "20010418",
    "20010515", "20010627", "20010821", "20010917",
    "20011002", "20011106", "20011211",
    # 2002
    "20020130", "20020319", "20020507", "20020626",
    "20020813", "20020924", "20021106", "20021210",
    # 2003
    "20030129", "20030318", "20030506", "20030625",
    "20030812", "20030916", "20031028", "20031209",
    # 2004
    "20040128", "20040316", "20040504", "20040630",
    "20040810", "20040921", "20041110", "20041214",
    # 2005
    "20050202", "20050322", "20050503", "20050630",
    "20050809", "20050920", "20051101", "20051213",
    # 2006
    "20060131", "20060328", "20060510", "20060629",
    "20060808", "20060920", "20061025", "20061212",
    # 2007
    "20070131", "20070321", "20070509", "20070628",
    "20070807", "20070918", "20071031", "20071211",
    # 2008
    "20080122", "20080130", "20080318", "20080430",
    "20080625", "20080805", "20080916", "20081008",
    "20081029", "20081216",
    # 2009
    "20090128", "20090318", "20090429", "20090624",
    "20090812", "20090923", "20091104", "20091216",
    # 2010
    "20100127", "20100316", "20100428", "20100623",
    "20100810", "20100921", "20101103", "20101214",
    # 2011
    "20110126", "20110315", "20110427", "20110622",
    "20110809", "20110921", "20111102", "20111213",
]


# ── Calendar scraping ─────────────────────────────────────────────────────────

def get_meeting_dates(start_year: int, end_year: int, logger) -> list[str]:
    """
    Collect FOMC meeting dates (YYYYMMDD).

    Sources:
      - Hardcoded list for 2000–2011 (historical pages return 404)
      - fomccalendars.htm for 2012–present
    """
    dates: set[str] = set()

    DATE_RE = re.compile(
        r'(?:monetary|fomcminutes|fomcpresconf)(\d{8})', re.IGNORECASE
    )

    # 1. Hardcoded 2000–2011 dates
    if start_year <= 2011:
        for d in HISTORICAL_DATES_2000_2011:
            if start_year <= int(d[:4]) <= min(end_year, 2011):
                dates.add(d)
        logger.info(f"Loaded {len(dates)} hardcoded dates (2000–2011).")

    # 2. Current calendar page (covers 2012–present)
    if end_year >= 2012:
        logger.info("Fetching current FOMC calendar …")
        try:
            resp = requests.get(
                f"{BASE_URL}/monetarypolicy/fomccalendars.htm",
                headers=HEADERS, timeout=30
            )
            resp.raise_for_status()
            found = set()
            for m in DATE_RE.finditer(resp.text):
                d = m.group(1)
                if 2012 <= int(d[:4]) <= end_year:
                    found.add(d)
            new = found - dates
            dates.update(found)
            logger.info(f"  {len(new)} new dates from calendar page.")
        except Exception as e:
            logger.warning(f"  Calendar page failed: {e}")

    sorted_dates = sorted(dates)
    logger.info(f"Total unique meeting dates: {len(sorted_dates)}")
    if sorted_dates:
        logger.info(f"  Range: {sorted_dates[0]} → {sorted_dates[-1]}")
    return sorted_dates


# ── Download ──────────────────────────────────────────────────────────────────

def try_download(date: str, doc_type: str) -> tuple[str, str, str]:
    """
    Try each URL template for the given date and doc_type.
    Returns (status, fmt, url):
      status : 'ok' | 'not_found' | 'error: ...'
      fmt    : 'pdf' | 'html' | 'none'
      url    : URL that succeeded (or last tried)
    """
    for tmpl in URL_TEMPLATES[doc_type]:
        path = tmpl.format(date=date, yyyy=date[:4])
        url  = BASE_URL + path
        fmt  = "pdf" if path.endswith(".pdf") else "html"
        ext  = ".pdf" if fmt == "pdf" else ".html"

        try:
            resp = requests.get(url, headers=HEADERS, timeout=30,
                                stream=(fmt == "pdf"))
            if resp.status_code == 404:
                continue

            resp.raise_for_status()

            # Save to disk
            doc_id = make_doc_id(doc_type, date)
            dest   = RAW_ROOT / doc_type / f"{doc_id}{ext}"
            dest.parent.mkdir(parents=True, exist_ok=True)
            save_raw(resp.content if fmt == "pdf" else resp.text, dest)

            time.sleep(1.2)   # polite delay between requests
            return "ok", fmt, url

        except Exception as e:
            return f"error: {e}", fmt, url

    return "not_found", "none", ""


# ── Main ──────────────────────────────────────────────────────────────────────

def scrape(
    target_types: list[str],
    start_year: int = 2000,
    end_year: int   = 2026,
) -> None:
    logger     = setup_logging("fed_scraper", str(LOG_PATH))
    checkpoint = load_checkpoint(CKPT_PATH)

    logger.info(f"Target types  : {target_types}")
    logger.info(f"Date range    : {start_year}–{end_year}")
    logger.info(f"In checkpoint : {len(checkpoint)} documents")

    # Step 1 — collect all meeting dates
    dates = get_meeting_dates(start_year, end_year, logger)

    # Step 2 — download each doc type for each date
    downloaded = skipped = failed = not_found = 0

    for date in dates:
        for doc_type in target_types:

            # Press conferences didn't exist before April 2011
            if doc_type == "press_conf" and date < PC_START_DATE:
                continue

            doc_id = make_doc_id(doc_type, date)

            # Skip already-downloaded
            if checkpoint.get(doc_id, {}).get("status") == "ok":
                skipped += 1
                continue

            status, fmt, url = try_download(date, doc_type)

            if status == "not_found":
                # Normal — not every meeting has every doc type
                not_found += 1
                continue

            checkpoint[doc_id] = {
                "date": date, "type": doc_type,
                "fmt": fmt, "url": url, "status": status,
            }
            save_checkpoint(checkpoint, CKPT_PATH)

            if status == "ok":
                downloaded += 1
                logger.info(f"  ✓ {doc_id} ({fmt})")
            else:
                failed += 1
                logger.error(f"  ✗ {doc_id} — {status}")

    logger.info(
        f"\nDone. "
        f"Downloaded: {downloaded} | "
        f"Skipped: {skipped} | "
        f"Not found: {not_found} | "
        f"Failed: {failed}"
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Scrape FOMC Statements, Minutes, Press Conferences"
    )
    parser.add_argument(
        "--types", nargs="+",
        choices=["statements", "minutes", "press_conf"],
        default=["statements", "minutes", "press_conf"],
    )
    parser.add_argument("--start-year", type=int, default=2000)
    parser.add_argument("--end-year",   type=int, default=2026)
    args = parser.parse_args()

    scrape(
        target_types=args.types,
        start_year=args.start_year,
        end_year=args.end_year,
    )
