# Fed NLP Pipeline: FOMC Communication & Market Impact

An end-to-end pipeline for collecting, processing, and annotating Federal Reserve (FOMC) documents (2000–present) to extract structured macroeconomic and policy signals using large language models.

## Research Overview

This project analyzes how FOMC communications drive asset price reactions by extracting interpretable factors from Fed documents across three dimensions:

- **Information Layer** — macroeconomic sentiment on Inflation, Labor, Growth, and Financial Stability
- **Policy Layer** — hawkish/dovish stance and forward guidance signals
- **Disagreement Layer** — internal policy disagreement within the Committee

The core methodology shifts from traditional dictionary-based sentiment analysis (LM, BG, ABG dictionaries) to LLM-based factor extraction, motivated by the context-dependence of Fed language that fixed word lists cannot capture.

## Pipeline Architecture

```
federalreserve.gov
       ↓
01_data_collection/          Raw HTML & PDF documents
       ↓
02_data_processing/          Plain text + metadata CSV
       ↓
03_annotation/               LLM-extracted factors (12 columns)
       ↓
04_validation/               Divergence analysis & human review
       ↓
05_empirical_analysis/       Regression: factors → market returns
```

## Document Coverage

| Type | Source | Format | Period |
|------|--------|--------|--------|
| FOMC Statements | federalreserve.gov | HTML | 2000–present |
| FOMC Minutes | federalreserve.gov | PDF | 2000–present |
| Press Conferences | federalreserve.gov | HTML | 2011–present |

## Annotation Schema

Each document is scored using three prompts run in parallel across two LLMs (Llama 3.3 70B + DeepSeek-V3):

### Prompt 1 — Macro Sentiment (all document types)

Extracts structured signals for four economic topics. Each topic is evaluated independently:

| Topic | Fields | Range |
|-------|--------|-------|
| Inflation | Mention, Importance, Current_Condition, Outlook | Mention: 0/1 · Importance: Major/Minor · Scores: −2 to +2 |
| Labor Market | Mention, Importance, Current_Condition, Outlook | same |
| Growth | Mention, Importance, Current_Condition, Outlook | same |
| Financial Stability | Mention, Importance, Current_Condition, Outlook | same |

Sign conventions follow the Fed's dual mandate framing (e.g., inflation above target or increasing → positive; tight labor market → positive). Scores reflect the dominant narrative when conflicting signals appear.

### Prompt 2 — Policy Layer (Statements and Press Conferences only)

| Field | Range | Description |
|-------|-------|-------------|
| Hawkish_Dovish_Stance | −2 to +2 | Current policy stance (−2 = strongly dovish, +2 = strongly hawkish) |
| Forward_Guidance | −2 to +2 | Expected direction of future policy change |

Minutes are excluded from this prompt because they embed the Statement verbatim — extracting policy stance from Minutes would double-count signals already captured in Statements.

### Prompt 3 — Policy Disagreement (Minutes and Press Conferences only)

| Field | Range | Description |
|-------|-------|-------------|
| Policy_Disagreement | 0 / 1 / 2 | 0 = none · 1 = implicit · 2 = explicit disagreement on policy path |

Scores follow a strict hierarchy: explicit disagreement anywhere in the document overrides implicit signals.

Dual-model annotation enables divergence analysis to flag high-uncertainty documents for targeted human review, rather than exhaustive re-scoring.

## Repository Structure

```
scripts/
├── pipeline_runner.ipynb        # ← Start here: runs full pipeline
│
├── fed_scraper.py               # Scrapes all three doc types via Selenium
├── weekly_update.py             # Incremental update after each FOMC meeting
├── utils.py                     # Shared utilities (logging, checkpoints, HTTP)
│
├── convert_to_txt.py            # PDF/HTML → plain TXT (pdfplumber + BS4)
├── build_metadata.py            # Builds metadata.csv from processed TXT
│
├── annotation_pipeline.py       # LLM annotation (Together AI)
│
└── data/
    ├── metadata.csv             # Document index (doc_id, date, type, etc.)
    ├── annotation_dataset.csv   # Input to annotation pipeline (61 docs)
    └── open_annotation_dataset.csv  # Annotated output (12 factor columns)
```

> `data/raw/` and `data/processed/` are excluded from version control (see `.gitignore`).

## Quickstart

**Requirements**: Python 3.10+, Anaconda, Google Chrome

```bash
pip install -r requirements.txt
```

Open `pipeline_runner.ipynb` and run cells in order:

| Section | Action |
|---------|--------|
| 0. Setup | Set working directory, verify Chrome + Selenium |
| 1. Scrape | Download raw documents (first run: ~1 hr) |
| 2. Convert | PDF/HTML → TXT |
| 3. Metadata | Build metadata.csv |
| 4. Update | Weekly incremental update (new docs only) |

## Key Design Decisions

**Why Selenium?**
The Fed materials page (`federalreserve.gov/monetarypolicy/materials/`) is an Angular application with JavaScript pagination. Standard `requests`-based scraping cannot iterate pages — Selenium is required.

**Why dual-model annotation?**
Running two models (Llama 3.3 70B and DeepSeek-V3) on each document allows divergence analysis to identify genuinely ambiguous documents. Human review is targeted at high-disagreement cases rather than exhaustive re-scoring.

**Why separate policy and information layers for Minutes?**
FOMC Minutes embed the Statement verbatim in the "Committee Policy Action" section. To avoid double-counting, HD Stance and Forward Guidance are extracted from standalone Statements only; Minutes contribute only to the Information Layer (macro theme scores).

**Pre/post-crisis Minutes format:**
The January 27–28, 2009 meeting marks a structural shift in Minutes formatting. Pre-crisis Minutes lack standardized section headers; post-crisis Minutes have consistent section structure. The pipeline detects this automatically via `minutes_format` in metadata.

## My Contribution

This project is collaborative. My responsibilities:

- FOMC Statements and Minutes: web scraping, ETL pipeline, text processing
- Press Conference transcripts: scraping and processing
- Annotation pipeline architecture: prompt design, Together AI integration, checkpoint system, output normalization
- Divergence analysis: model disagreement quantification and human review prioritization

Teammates cover: SEPs, Speeches, and empirical regression analysis.

## Dependencies

```
requests / beautifulsoup4 / lxml   — HTTP and HTML parsing
selenium / webdriver-manager       — JavaScript pagination
pdfplumber                         — PDF text extraction
pandas                             — Data processing
```

See `requirements.txt` for pinned versions.

## Status

- [x] Data collection pipeline (Statements, Minutes, Press Conferences)
- [x] ETL: PDF/HTML → TXT → metadata CSV
- [x] LLM annotation pipeline (Llama 3.3 70B + DeepSeek-V3)
- [x] Divergence analysis and human review framework
- [ ] Empirical analysis: regression of factors on market returns
