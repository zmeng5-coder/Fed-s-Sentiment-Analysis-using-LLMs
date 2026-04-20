"""
utils.py — Shared utilities for Fed document scrapers.
Handles logging, rate-limited requests, checkpointing, and file I/O.
"""

import json
import logging
import time
from pathlib import Path

import requests

# ── Constants ────────────────────────────────────────────────────────────────

BASE_URL = "https://www.federalreserve.gov"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# doc_type → short prefix for doc_id
DOC_TYPE_PREFIX = {
    "statements":  "stmt",
    "minutes":     "min",
    "press_conf":  "pc",
}


# ── Logging ───────────────────────────────────────────────────────────────────

def setup_logging(name: str, log_file: str = None) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s — %(message)s")

    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)

        if log_file:
            Path(log_file).parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(log_file)
            fh.setFormatter(fmt)
            logger.addHandler(fh)

    return logger


# ── HTTP ──────────────────────────────────────────────────────────────────────

def rate_limited_get(url: str, delay: float = 1.5, **kwargs) -> requests.Response:
    """GET with polite delay and timeout. Raises on HTTP errors."""
    time.sleep(delay)
    resp = requests.get(url, headers=HEADERS, timeout=30, **kwargs)
    resp.raise_for_status()
    return resp


# ── Checkpointing ─────────────────────────────────────────────────────────────

def save_checkpoint(data: dict, path: Path) -> None:
    """Persist a dict to JSON (used to track already-scraped doc_ids)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_checkpoint(path: Path) -> dict:
    """Load checkpoint dict; returns empty dict if file doesn't exist."""
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return {}


# ── File I/O ──────────────────────────────────────────────────────────────────

def save_raw(content: bytes | str, dest: Path) -> None:
    """Save raw bytes (PDF) or str (HTML) to disk."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        dest.write_bytes(content)
    else:
        dest.write_text(content, encoding="utf-8")


# ── doc_id helpers ────────────────────────────────────────────────────────────

def make_doc_id(doc_type: str, date_str: str) -> str:
    """
    Build a unique doc_id.
    Args:
        doc_type : 'statements' | 'minutes' | 'press_conf'
        date_str : 'YYYYMMDD'
    Returns:
        e.g. 'stmt_20230201'
    """
    prefix = DOC_TYPE_PREFIX[doc_type]
    return f"{prefix}_{date_str}"


def date_from_doc_id(doc_id: str) -> str:
    """Extract 'YYYYMMDD' from a doc_id like 'stmt_20230201'."""
    return doc_id.split("_")[1]
