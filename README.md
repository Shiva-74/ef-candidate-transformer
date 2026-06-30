# Multi-Source Candidate Data Transformer

A pipeline that ingests candidate information from **multiple heterogeneous sources**, deduplicates and merges it into a single canonical profile, and emits clean, schema-valid JSON — with full provenance and configurable output projection.

---
## Problem Statement  
Eightfold ingests candidate data from many places at once. Downstream products need one clean, canonical profile per candidate: a fixed set of fields, normalised formats, deduplicated across sources, and a record of where each value came from and how confident we are in it.

---

## Setup & Installation

### Prerequisites
- Python 3.10 or higher
- `pip`

### Install

```bash
# 1. Clone the repo
git clone https://github.com/Shiva-74/ef-candidate-transformer.git
cd ef-candidate-transformer

# 2. Create and activate a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt
```


**`requirements.txt`:**
```
pydantic>=2.0
pandas
phonenumbers
dateparser
PyMuPDF
requests
streamlit
pytest
```


> **Note:** `PyMuPDF` installs as `fitz`. If you hit a build error on Windows, install the pre-built wheel:
> `pip install pymupdf`


## How to Run

---

### Streamlit UI(Easier Access)

A minimal web UI is provided for interactive exploration:

```bash
streamlit run app.py
```

Then open [http://localhost:8501](http://localhost:8501) in your browser.

The UI lets you:
- Upload a CSV, PDF resume, or enter a GitHub URL
- Paste or upload a custom config JSON
- Run the pipeline and view the canonical profile + projected output side-by-side
- See the provenance table and confidence scores

---
### CLI
 
```bash
python main.py [--csv PATH] [--resume PATH] [--github-url URL]
               [--config PATH] [--output PATH] [--full] [--quiet]
```
 
At least one of `--csv`, `--resume`, or `--github-url` is required.
 
**Examples:**
 
```bash
# CSV only, default schema
python main.py --csv sample_inputs/sample.csv
 
# CSV + custom config (renamed fields, E.164 phones, canonical skills)
python main.py --csv sample_inputs/sample.csv --config configs/custom_config.json
 
# All three sources combined
python main.py \
  --csv sample_inputs/sample.csv \
  --resume sample_inputs/resume.pdf \
  --github-url https://github.com/octocat \
  --config configs/custom_config.json \
  --output output/profile.json \
  --full
```
 
| Flag | Default | Description |
|------|---------|-------------|
| `--csv PATH` | — | Recruiter CSV file |
| `--resume PATH` | — | PDF resume |
| `--github-url URL` | — | GitHub profile URL or username |
| `--config PATH` | `configs/default_config.json` | Projection config JSON |
| `--output PATH` | `output/profile.json` | Output JSON path |
| `--full` | off | Also write full canonical record to `output/candidate_full.json` |
| `--quiet` | off | Suppress INFO logs |

 
## Sample Output
 
Running the default CSV example produces a CLI summary like:
 
```
=======================================================
  CANDIDATE PROFILE SUMMARY
=======================================================
  ID         : c001abc
  Name       : Priya Nair
  Emails     : priya@example.com
  Phones     : +919876543210
  Location   : Bangalore, Karnataka, IN
  Headline   : ML Engineer at Acme Corp
  Skills     : 6 found
  Experience : 2 entry/entries
  Education  : 1 entry/entries
  Confidence : 85%
=======================================================
  Sources    : 12 provenance entries
=======================================================
```

and writes the projected JSON to `output/profile.json` (full canonical record to `output/candidate_full.json` with `--full`).

#### Error Handling at CLI Level

If validation fails (e.g. a required field is missing and `on_missing: "error"`), the pipeline raises `ValueError` which the CLI catches and exits cleanly:

```
Error: Output validation failed:
  • Required field 'primary_email' is missing from output.
```

Exit code `1` is returned — safe for shell scripting.


---

## Running Tests

```bash
# Run all 61 tests
python -m pytest tests/ -v

# Run only the validate unit tests
python -m pytest tests/test_validate.py -v

# Run only the project unit tests
python -m pytest tests/test_project.py -v

# Run only the pipeline integration tests (the bug-fix tests)
python -m pytest tests/test_pipeline_validate_propagation.py -v

# Run with short traceback on failure
python -m pytest tests/ --tb=short
```

Expected output: **61 passed**.

### What the Tests Cover

| Test File | Count | What it verifies |
|-----------|-------|-----------------|
| `test_validate.py` | 21 | `validate.check()` — required fields, type checks, all three `on_missing` modes, multi-error reporting, edge cases |
| `test_project.py` | 34 | `project.project()` — scalar/nested/array-index/list-map path resolution, on_missing policies, E.164+canonical normalizers, `include_confidence`, Pydantic→dict serialization |
| `test_pipeline_validate_propagation.py` | 6 | **The critical bug fix** — confirms `ValueError` from `validate.check()` now propagates out of `run_pipeline()` to the caller; valid output still returns normally |

---

A sample run on sample_inputs/sample.csv is included in this repo: output/profile.json (default config) and output/profile_custom.json (custom config — renamed fields, E.164 phones, canonical skills). These show the actual output produced by the pipeline on the provided sample inputs.

---

## Design Decisions

### 1. Claim-based intermediate representation
Every adapter emits `RawFieldValue(field, value, source, method, confidence)` rather than a half-filled `Candidate`. This keeps adapters thin and lets the merge layer be the single place that resolves conflicts. It also makes it easy to add a new source without touching any other module.

### 2. Confidence is derived, not asserted
Confidence is not a magic number. It follows a clear formula:
- 1 source agreeing → 0.60
- 2 sources agreeing → 0.85
- 3+ sources agreeing → 0.95
- Structured source (CSV) → 1.0 (direct field)
- Regex from PDF → 0.75–0.85
- GitHub API → 0.60–0.95 depending on field

This makes confidence explainable and auditable via the provenance table.

### 3. Clean separation between canonical record and projection
The `Candidate` model is never mutated after merge. The projection layer reads from it and produces an output dict — these two concerns never mix. This means the same canonical record can serve any number of different output configs without re-running the adapters or merge.

### 4. Validate-before-return is a hard gate
`validate.check()` raises `ValueError` on hard failures (required field missing, type mismatch on required field). `pipeline.py` intentionally does **not** catch this — it propagates to the CLI's `except ValueError → sys.exit(1)`. This ensures the spec's "validate before returning" bullet is actually enforced, not silently papered over.

### 5. Graceful degradation on bad sources
A missing file, a corrupt PDF, or a GitHub 404 logs a warning and continues — it does not crash the run. The pipeline only aborts if **all** sources yield zero claims.

### 6. Provenance deduplication
If the same `(field, source)` pair appears multiple times (e.g. two emails from the same CSV), only one provenance row is kept (the higher confidence one). This keeps the provenance table clean and readable.

---



