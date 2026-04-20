"""
convert_to_txt.py — Convert raw Fed documents (PDF / HTML) to plain text.

Input  : data/raw/{statements,minutes,press_conf}/
Output : data/processed/{statements,minutes,press_conf}/

Key behaviors:
  - PDF  → pdfplumber (page-by-page extraction, joined with newlines)
  - HTML → BeautifulSoup (strips tags, preserves paragraph breaks)
  - Skips files already converted (checkpoint-based resume)
  - Minutes-specific: flags post-crisis vs pre-crisis format for downstream use
    (transition date: 2009-01-28, i.e. doc_id min_20090128)

Usage:
    python convert_to_txt.py                    # all doc types
    python convert_to_txt.py --doc-type minutes # specific type
    python convert_to_txt.py --force            # re-convert everything
"""

import argparse
import re
from pathlib import Path

import pdfplumber
from bs4 import BeautifulSoup

from utils import load_checkpoint, save_checkpoint, setup_logging

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent
RAW_ROOT   = ROOT / "data" / "raw"
PROC_ROOT  = ROOT / "data" / "processed"
CKPT_PATH  = ROOT / "data" / ".checkpoints" / "convert_to_txt.json"
LOG_PATH   = ROOT / "data" / ".checkpoints" / "convert_to_txt.log"

DOC_TYPES  = ["statements", "minutes", "press_conf"]

# Minutes format transition (meeting date of Jan 27–28, 2009)
MIN_TRANSITION_DATE = "20090128"


# ── Conversion helpers ────────────────────────────────────────────────────────

def pdf_to_text(path: Path) -> str:
    """Extract text from PDF using pdfplumber. Returns concatenated pages."""
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
    return "\n\n".join(pages)


def html_to_text(path: Path) -> str:
    """
    Extract readable text from an HTML file.
    Preserves paragraph-level line breaks; strips all tags.
    """
    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")

    # Remove nav, script, style, header, footer noise
    for tag in soup.find_all(["script", "style", "nav", "header", "footer",
                               "aside", "noscript"]):
        tag.decompose()

    # Insert newlines around block elements before getting text
    for tag in soup.find_all(["p", "div", "br", "h1", "h2", "h3", "h4", "li"]):
        tag.insert_before("\n")
        tag.insert_after("\n")

    text = soup.get_text(separator=" ")

    # Collapse excessive whitespace while preserving paragraph breaks
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ── Minutes format detection ──────────────────────────────────────────────────

def detect_minutes_format(doc_id: str) -> str:
    """
    Return 'post_crisis' or 'pre_crisis' based on meeting date.
    Transition: January 27-28 2009 meeting (min_20090128).
    """
    date_str = doc_id.split("_")[1]
    return "post_crisis" if date_str >= MIN_TRANSITION_DATE else "pre_crisis"


# ── Core conversion ───────────────────────────────────────────────────────────

def convert_file(src: Path, dest: Path, logger) -> str:
    """
    Convert a single raw file to TXT. Returns 'ok', 'skip', or 'error:...'
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    suffix = src.suffix.lower()

    if suffix == ".pdf":
        text = pdf_to_text(src)
    elif suffix in (".html", ".htm"):
        text = html_to_text(src)
    else:
        logger.warning(f"  Unknown format {suffix} for {src.name} — skipping.")
        return "skip"

    if not text.strip():
        logger.warning(f"  Empty text extracted from {src.name}")
        return "error: empty extraction"

    dest.write_text(text, encoding="utf-8")
    return "ok"


# ── Main ──────────────────────────────────────────────────────────────────────

def convert_all(doc_types: list[str], force: bool = False) -> None:
    logger = setup_logging("convert_to_txt", LOG_PATH)
    checkpoint = load_checkpoint(CKPT_PATH)

    converted = skipped = failed = 0

    for doc_type in doc_types:
        raw_dir  = RAW_ROOT  / doc_type
        proc_dir = PROC_ROOT / doc_type

        raw_files = sorted(raw_dir.glob("*"))
        logger.info(f"\n[{doc_type}] {len(raw_files)} raw files found.")

        for src in raw_files:
            doc_id = src.stem          # e.g. "stmt_20230201"
            key    = f"{doc_type}/{doc_id}"

            if not force and checkpoint.get(key) == "ok":
                skipped += 1
                continue

            dest = proc_dir / f"{doc_id}.txt"

            # Attach format metadata for minutes
            extra_info = ""
            if doc_type == "minutes":
                fmt = detect_minutes_format(doc_id)
                extra_info = f" [{fmt}]"

            try:
                status = convert_file(src, dest, logger)
                checkpoint[key] = status
                save_checkpoint(checkpoint, CKPT_PATH)

                if status == "ok":
                    converted += 1
                    logger.info(f"  ✓ {doc_id}{extra_info}")
                else:
                    skipped += 1

            except Exception as e:
                failed += 1
                checkpoint[key] = f"error: {e}"
                save_checkpoint(checkpoint, CKPT_PATH)
                logger.error(f"  ✗ {doc_id} — {e}")

    logger.info(
        f"\nConversion complete. "
        f"Converted: {converted} | Skipped: {skipped} | Failed: {failed}"
    )


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert raw Fed docs to TXT")
    parser.add_argument(
        "--doc-type",
        choices=DOC_TYPES + ["all"],
        default="all",
        help="Which document type(s) to convert (default: all)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-convert all files, ignoring checkpoint",
    )
    args = parser.parse_args()

    types = DOC_TYPES if args.doc_type == "all" else [args.doc_type]
    convert_all(types, force=args.force)
