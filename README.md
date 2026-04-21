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
03_annotation/               LLM-extracted factors
       ↓
04_validation/               Divergence analysis & human review
       ↓
05_empirical_analysis/       Regression: factors → market returns
```

## Document Coverage

| Type | Source | Format | Period |
|------|--------|--------|--------|
| FOMC Statements | federalreserve.gov | HTML | 2000–present |
| FOMC Minutes | federalreserve.gov | PDF/HTML | 2000–present |
| Press Conferences | federalreserve.gov | HTML | 2011–present |

## Annotation Schema

Each document is scored using three prompts run across two LLMs in parallel (**Llama 3.3 70B** and **DeepSeek-V3** via Together AI). Results are stored as JSON columns in `open_annotation_dataset.csv`.

### Prompt 1 — Macro Sentiment (`macro_sentiment.txt`)
Applied to: all document types

Extracts structured signals for four economic topics. Each topic is evaluated independently:

| Topic | Fields | Score Range |
|-------|--------|-------------|
| Inflation | Mention, Importance, Current_Condition, Outlook | Mention: 0/1 · Importance: Major/Minor · Scores: −2 to +2 |
| Labor Market | Mention, Importance, Current_Condition, Outlook | same |
| Growth | Mention, Importance, Current_Condition, Outlook | same |
| Financial Stability | Mention, Importance, Current_Condition, Outlook | same |

Key conventions: inflation above target or increasing → positive; tight labor market → positive. Scores reflect the dominant narrative when conflicting signals appear. Outlook for inflation uses a directional scale (increasing/decreasing); other topics use an improvement scale.

### Prompt 2 — Policy Layer (`policy_layer.txt`)
Applied to: Statements and Press Conferences only

| Field | Range | Description |
|-------|-------|-------------|
| Hawkish_Dovish_Stance | −2 to +2 | Current policy stance (−2 = strongly dovish, +2 = strongly hawkish) |
| Forward_Guidance | −2 to +2 | Expected direction of future policy change |

Minutes are excluded because the Statement is embedded verbatim within them — extracting policy stance from Minutes would double-count signals already captured from standalone Statements.

### Prompt 3 — Policy Disagreement (`policy_disagreement.txt`)
Applied to: Minutes and Press Conferences only

| Field | Range | Description |
|-------|-------|-------------|
| Policy_Disagreement | 0 / 1 / 2 | 0 = none · 1 = implicit · 2 = explicit disagreement on policy path |

Scores follow a strict hierarchy: any instance of explicit disagreement anywhere in the document overrides implicit signals. Routine data dependence and general uncertainty do not count as disagreement.

### Output columns in `open_annotation_dataset.csv`

```
llama_Inflation, llama_Labor, llama_Growth, llama_Financial_Stability,
llama_Policy_Layer, llama_Policy_Disagreement,
ds_Inflation, ds_Labor, ds_Growth, ds_Financial_Stability,
ds_Policy_Layer, ds_Policy_Disagreement
```

Dual-model annotation enables divergence analysis to flag high-uncertainty documents for targeted human review rather than exhaustive re-scoring.

## Repository Structure

```
Fed-s-Sentiment-Analysis-using-LLMs/
│
├── pipeline_runner.ipynb        # ← Start here: runs full data pipeline
├── requirements.txt
├── .gitignore
│
├── 01_data_collection/
│   ├── fed_scraper.py           # Scrapes Statements, Minutes, Press Confs
│   ├── weekly_update.py         # Incremental update after each FOMC meeting
│   └── utils.py                 # Shared utilities (logging, checkpoints, HTTP)
│
├── 02_data_processing/
│   ├── convert_to_txt.py        # PDF/HTML → plain TXT (pdfplumber + BS4)
│   └── build_metadata.py        # Builds metadata.csv from processed TXT
│
├── 03_annotation/
│   ├── annotation_pipeline.ipynb    # LLM annotation (Llama + DeepSeek via Together AI)
│   ├── model_comparison.ipynb       # Model comparison test (DeepSeek vs Qwen)
│   └── prompts/
│       ├── macro_sentiment.txt
│       ├── policy_layer.txt
│       └── policy_disagreement.txt
│
└── data/
    ├── metadata.csv                 # 431 documents: doc_id, date, type, chair_regime
    ├── annotation_dataset.csv       # Human-annotated ground truth
    └── open_annotation_dataset.csv  # LLM annotation output (12 JSON columns)
```

> `data/raw/` and `data/processed/` are excluded from version control (see `.gitignore`).

## Quickstart

**Requirements**: Python 3.10+, Anaconda

```bash
pip install -r requirements.txt
```

Open `pipeline_runner.ipynb` and run cells in order:

| Section | Action |
|---------|--------|
| 0. Setup | Set working directory, verify environment |
| 1. Scrape | Download raw documents (~1 hr first run) |
| 2. Convert | PDF/HTML → TXT |
| 3. Metadata | Build metadata.csv |
| 4. Update | Weekly incremental update (new docs only) |

To run the annotation pipeline, open `03_annotation/annotation_pipeline.ipynb` and set your Together AI API key.

## Key Design Decisions

**Direct URL construction over pagination scraping**
The Fed materials page is an Angular app with JavaScript pagination. Rather than fighting browser automation, the scraper collects meeting dates from plain-HTML calendar pages and constructs document URLs directly — simpler, faster, and more reliable.

**Why dual-model annotation?**
Running Llama 3.3 70B and DeepSeek-V3 in parallel on each document enables divergence analysis to identify genuinely ambiguous documents. Human review is targeted at high-disagreement cases rather than exhaustive re-scoring.

**Why separate policy and information layers for Minutes?**
FOMC Minutes embed the Statement verbatim in the "Committee Policy Action" section. Extracting HD Stance and Forward Guidance from Minutes would double-count signals already captured from standalone Statements. Minutes contribute only to the Information Layer.

**Inflation outlook sign convention**
Unlike other topics where outlook reflects improvement/worsening, inflation outlook uses a directional scale (increasing/decreasing). This matches the Fed's mandate framing: rising inflation is scored positive regardless of whether it is desirable.

## My Contribution

This project is collaborative. My responsibilities:

- FOMC Statements, Minutes, Press Conferences: web scraping, ETL pipeline, text processing
- Annotation pipeline: prompt design, Together AI integration, dual-model execution, checkpoint system, output normalization
- Divergence analysis: model disagreement quantification and human review prioritization

Teammates cover: SEPs, Speeches, and empirical regression analysis.

## Dependencies

```
requests / beautifulsoup4 / lxml   — HTTP and HTML parsing
pdfplumber                         — PDF text extraction
pandas                             — Data processing
```

See `requirements.txt` for pinned versions.

## Status

- [x] Data collection pipeline (Statements, Minutes, Press Conferences, 2000–present)
- [x] ETL: PDF/HTML → TXT → metadata CSV (431 documents)
- [x] LLM annotation pipeline (Llama 3.3 70B + DeepSeek-V3)
- [x] Divergence analysis and human review framework
- [ ] Empirical analysis: regression of factors on market returns
