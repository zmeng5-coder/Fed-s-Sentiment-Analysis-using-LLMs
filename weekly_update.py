"""
weekly_update.py — Incremental update: check for new FOMC documents.

Run this weekly (or after each FOMC meeting) to pull only NEW documents
without re-scraping the full history.

Strategy:
  - Only scrape the first N pages of the materials table (most recent docs)
  - The checkpoint in scraper.json means already-downloaded docs are skipped
  - New docs (not in checkpoint) are downloaded automatically

Typical FOMC schedule:
  - 8 meetings/year → roughly 8 Statements + 8 Minutes + 8 Press Confs
  - Minutes released ~3 weeks after meeting
  - Pages 1–2 of the materials table cover ~6 months of meetings

Usage:
    # Run manually after an FOMC meeting
    python weekly_update.py

    # Or schedule via cron:
    # 0 18 * * 3   cd /path/to/fed_pipeline && python 01_data_collection/scrapers/weekly_update.py
    # (runs every Wednesday at 6pm — FOMC minutes typically release on Wednesdays)
"""

import subprocess
import sys
from pathlib import Path

from utils import setup_logging

ROOT     = Path(__file__).resolve().parent
LOG_PATH = ROOT / "data" / ".checkpoints" / "weekly_update.log"


def run_update():
    logger = setup_logging("weekly_update", str(LOG_PATH))
    logger.info("=" * 60)
    logger.info("Starting weekly FOMC materials update …")
    logger.info("Checking first 3 pages (covers ~6 months of meetings)")

    # Step 1: Scrape latest pages only
    scraper = Path(__file__).parent / "fed_scraper.py"
    result = subprocess.run(
        [sys.executable, str(scraper),
         "--types", "statements", "minutes", "press_conf",
         "--start-year", "2000"],
        capture_output=False,
    )

    if result.returncode != 0:
        logger.error("Scraper failed — check logs above.")
        return

    # Step 2: Convert any new raw files to TXT
    logger.info("\nConverting new raw files to TXT …")
    converter = ROOT / "convert_to_txt.py"
    subprocess.run([sys.executable, str(converter)], capture_output=False)

    # Step 3: Rebuild metadata CSV
    logger.info("\nRebuilding metadata CSV …")
    meta_builder = ROOT / "build_metadata.py"
    subprocess.run([sys.executable, str(meta_builder)], capture_output=False)

    logger.info("\nWeekly update complete.")
    logger.info("Next step: run annotation_pipeline.py on any new doc_ids.")


if __name__ == "__main__":
    run_update()
