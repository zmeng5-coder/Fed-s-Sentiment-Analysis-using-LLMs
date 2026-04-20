"""
build_metadata.py — Build metadata CSV from processed TXT documents.

Input  : data/processed/{statements,minutes,press_conf}/
         data/.checkpoints/scraper.json  (for download_date, source URL)
Output : data/metadata.csv

Columns:
    doc_id          : unique identifier, e.g. stmt_20230201
    doc_type        : statements | minutes | press_conf
    doc_date        : YYYY-MM-DD  (document release date = meeting end date)
    meeting_date    : YYYY-MM-DD  (same as doc_date for our purposes)
    download_date   : YYYY-MM-DD  (date file was downloaded)
    year            : int
    source          : URL the file was downloaded from
    file_name       : filename on disk, e.g. stmt_20230201.html
    file_ext        : html | pdf
    speaker         : Chair name (for press_conf); NA for others
    chair_regime    : Fed Chair name covering this meeting date
    local_path      : relative path to processed TXT file

Usage:
    python build_metadata.py
    python build_metadata.py --output data/metadata_v2.csv
"""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

from utils import setup_logging

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT      = Path(__file__).resolve().parent
PROC_ROOT = ROOT / "data" / "processed"
RAW_ROOT  = ROOT / "data" / "raw"
CKPT_PATH = ROOT / "data" / ".checkpoints" / "scraper.json"
LOG_PATH  = ROOT / "data" / ".checkpoints" / "build_metadata.log"

DOC_TYPES = ["statements", "minutes", "press_conf"]

# ── Fed Chair regimes ─────────────────────────────────────────────────────────
# (start_date, end_date, name)  — end_date is last day in office

CHAIR_REGIMES = [
    ("20000201", "20060131", "Greenspan"),
    ("20060201", "20140131", "Bernanke"),
    ("20140201", "20180203", "Yellen"),
    ("20180205", "20991231", "Powell"),   # covers through end of dataset
]

def get_chair(date_str: str) -> str:
    for start, end, name in CHAIR_REGIMES:
        if start <= date_str <= end:
            return name
    return "Unknown"


# ── Speaker lookup (Press Conference chairs) ──────────────────────────────────

def get_speaker(doc_type: str, date_str: str) -> str:
    """For press conferences, return the Chair's name. NA for other doc types."""
    if doc_type != "press_conf":
        return "NA"
    return get_chair(date_str)


# ── Helpers ───────────────────────────────────────────────────────────────────

def format_date(date_str: str) -> str:
    """Convert YYYYMMDD → YYYY-MM-DD."""
    return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"


def get_file_ext(doc_id: str, doc_type: str, raw_dir: Path) -> str:
    """Find the actual file extension from raw directory."""
    for ext in [".pdf", ".html", ".htm"]:
        if (raw_dir / doc_type / f"{doc_id}{ext}").exists():
            return ext.lstrip(".")
    return "unknown"


def get_file_name(doc_id: str, doc_type: str, raw_dir: Path) -> str:
    """Find the actual filename from raw directory."""
    for ext in [".pdf", ".html", ".htm"]:
        fname = f"{doc_id}{ext}"
        if (raw_dir / doc_type / fname).exists():
            return fname
    return f"{doc_id}.unknown"


# ── Main ──────────────────────────────────────────────────────────────────────

def build_metadata(output_path: Path) -> pd.DataFrame:
    logger = setup_logging("build_metadata", str(LOG_PATH))

    # Load checkpoint for download_date and source URL
    checkpoint = {}
    if CKPT_PATH.exists():
        with open(CKPT_PATH) as f:
            checkpoint = json.load(f)
        logger.info(f"Loaded {len(checkpoint)} checkpoint entries.")

    today = datetime.today().strftime("%Y-%m-%d")

    rows = []
    for doc_type in DOC_TYPES:
        proc_dir = PROC_ROOT / doc_type
        txt_files = sorted(proc_dir.glob("*.txt")) if proc_dir.exists() else []
        logger.info(f"[{doc_type}] {len(txt_files)} processed TXT files.")

        for txt_path in txt_files:
            doc_id   = txt_path.stem
            date_str = doc_id.split("_")[1]    # YYYYMMDD
            ckpt_entry = checkpoint.get(doc_id, {})

            # download_date from checkpoint timestamp or fallback to today
            dl_date = ckpt_entry.get("download_date", today)

            row = {
                "doc_id":        doc_id,
                "doc_type":      doc_type,
                "doc_date":      format_date(date_str),
                "meeting_date":  format_date(date_str),
                "download_date": dl_date,
                "year":          int(date_str[:4]),
                "source":        ckpt_entry.get("url", ""),
                "file_name":     get_file_name(doc_id, doc_type, RAW_ROOT),
                "file_ext":      get_file_ext(doc_id, doc_type, RAW_ROOT),
                "speaker":       get_speaker(doc_type, date_str),
                "chair_regime":  get_chair(date_str),
                "local_path":    str(txt_path.relative_to(ROOT)),
            }
            rows.append(row)

    df = pd.DataFrame(rows)

    if df.empty:
        logger.warning("No processed documents found.")
        df.to_csv(output_path, index=False)
        return df

    # Sort by date then doc_type
    df.sort_values(["doc_date", "doc_type"], inplace=True)
    df.reset_index(drop=True, inplace=True)

    # Save
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info(f"\nMetadata saved → {output_path}")
    logger.info(f"Total documents: {len(df)}")

    # Summary
    summary = df.groupby("doc_type").agg(
        count=("doc_id", "count"),
        year_min=("year", "min"),
        year_max=("year", "max"),
    )
    logger.info(f"\n{summary.to_string()}")

    return df


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build metadata CSV")
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parent / "data" / "metadata.csv",
    )
    args = parser.parse_args()
    build_metadata(args.output)
