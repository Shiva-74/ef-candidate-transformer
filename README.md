# Multi-Source Candidate Data Transformer
### Eightfold Engineering Intern Assignment (Jul–Dec 2026)

A pipeline that ingests candidate information from **multiple heterogeneous sources**, deduplicates and merges it into a single canonical profile, and emits clean, schema-valid JSON — with full provenance and configurable output projection.

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Architecture Overview](#architecture-overview)
3. [Pipeline Steps](#pipeline-steps)
4. [Canonical Output Schema](#canonical-output-schema)
5. [Configurable Output (Projection Layer)](#configurable-output-projection-layer)
6. [Source Types Supported](#source-types-supported)
7. [Merge & Conflict-Resolution Policy](#merge--conflict-resolution-policy)
8. [Edge Cases Handled](#edge-cases-handled)
9. [Project Structure](#project-structure)
10. [Setup & Installation](#setup--installation)
11. [How to Run](#how-to-run)
    - [CLI](#cli)
    - [Streamlit UI](#streamlit-ui)
12. [Running Tests](#running-tests)
13. [Design Decisions](#design-decisions)
14. [Assumptions & Descoped Items](#assumptions--descoped-items)

---

## Problem Statement

Eightfold ingests candidate data from many places at once. Downstream products need one clean, canonical profile per candidate: a fixed set of fields, normalised formats, deduplicated across sources, and a record of where each value came from and how confident we are in it.

**Wrong-but-confident is worse than honestly-empty** — a bad value silently pollutes hiring decisions. This transformer turns messy multi-source inputs into one trustworthy profile.

---

## Architecture Overview

```
┌─────────────┐  ┌─────────────┐  ┌──────────────┐
│ Recruiter   │  │ PDF Resume  │  │  GitHub API  │
│ CSV Export  │  │  (pdf/docx) │  │  (REST)      │
└──────┬──────┘  └──────┬──────┘  └──────┬───────┘
       │                │                │
       ▼                ▼                ▼
┌─────────────────────────────────────────────────┐
│              ADAPTERS  (adapters/)              │
│  Each adapter emits typed RawFieldValue claims  │
│  with: field, value, source, method, confidence │
└───────────────────────┬─────────────────────────┘
                        │  List[RawFieldValue]
                        ▼
┌─────────────────────────────────────────────────┐
│             MERGE  (merge.py)                   │
│  Group → deduplicate → conflict-resolve →       │
│  build canonical Candidate + provenance         │
└───────────────────────┬─────────────────────────┘
                        │  Candidate (Pydantic)
                        ▼
┌─────────────────────────────────────────────────┐
│             PROJECT  (project.py)               │
│  Config-driven projection: field selection,     │
│  renaming, normalisation, missing-value policy  │
└───────────────────────┬─────────────────────────┘
                        │  dict (output shape)
                        ▼
┌─────────────────────────────────────────────────┐
│             VALIDATE  (validate.py)             │
│  Type checks + required-field checks against    │
│  the config spec — raises ValueError on failure │
└───────────────────────┬─────────────────────────┘
                        │
                        ▼
                  JSON Output / UI
```

---

## Pipeline Steps

| Step | Module | Responsibility |
|------|--------|----------------|
| **1. Extract** | `adapters/` | Parse each source into typed `RawFieldValue` claims |
| **2. Merge** | `merge.py` | Group claims by candidate identity, resolve conflicts, build `Candidate` |
| **3. Project** | `project.py` | Apply runtime config — select fields, rename, normalise, handle missing values |
| **4. Validate** | `validate.py` | Assert required fields present, check types — hard failures raise `ValueError` |
| **Output** | `pipeline.py` | Return `(Candidate, output_dict)` to CLI or UI |

---

## Canonical Output Schema

The internal `Candidate` model (defined in `candidate_schema.py`) is the source of truth. All adapters write into it; the projection layer reads from it.

| Field | Type | Notes |
|-------|------|-------|
| `candidate_id` | `string` | MD5 of first 3 claims or UUID if no ID in source |
| `full_name` | `string \| null` | |
| `emails` | `string[]` | Deduplicated, lowercased |
| `phones` | `string[]` | E.164 format (`+91XXXXXXXXXX`) |
| `location` | `{ city, region, country }` | `country` is ISO 3166-alpha-2 where known |
| `links` | `{ linkedin, github, portfolio, other[] }` | |
| `headline` | `string \| null` | Bio / job title summary |
| `years_experience` | `number \| null` | |
| `skills` | `[{ name, confidence, sources[] }]` | Canonical skill names (see normaliser) |
| `experience` | `[{ company, title, start, end, summary }]` | Dates as YYYY-MM |
| `education` | `[{ institution, degree, field, end_year }]` | |
| `provenance` | `[{ field, source, method, confidence }]` | One row per (field, source) pair |
| `overall_confidence` | `number` | Mean of all field-level confidences |

---

## Configurable Output (Projection Layer)

The pipeline accepts a **runtime JSON config** that reshapes the output without any code changes. The config can:

- **Select a subset of fields** to include in output
- **Rename / remap** a field from a canonical path (`"from"` key)
- **Set per-field normalisation** (E.164 for phones, canonical for skills, date for dates)
- **Toggle per-field and overall confidence** on or off
- **Choose what to do when a value is missing**: `"null"` (emit `null`), `"omit"` (skip the key), or `"error"` (abort with `ValueError`)

### Config Schema

```json
{
  "fields": [
    {
      "path":      "output_key_name",
      "from":      "canonical.path.or.emails[0]",
      "type":      "string | number | boolean | string[] | number[] | object",
      "required":  true,
      "normalize": "E164 | canonical | date"
    }
  ],
  "include_confidence": true,
  "on_missing": "null | omit | error"
}
```

### Path Syntax

| Pattern | Example | Result |
|---------|---------|--------|
| Top-level field | `"full_name"` | `candidate.full_name` |
| Nested field | `"location.country"` | `candidate.location.country` |
| Array index | `"emails[0]"` | First email address |
| List-map | `"skills[].name"` | `[s.name for s in candidate.skills]` |

### Provided Configs

| File | Description |
|------|-------------|
| `configs/default_config.json` | Full canonical schema, all fields, `on_missing: null` |
| `configs/custom_config.json` | Compact view — renamed fields (`primary_email`, `phone`), E.164 + canonical normalisation, only key fields |

### Example: `configs/custom_config.json`

```json
{
  "fields": [
    { "path": "full_name",     "type": "string",    "required": true  },
    { "path": "primary_email", "from": "emails[0]", "type": "string",    "required": true  },
    { "path": "phone",         "from": "phones[0]", "type": "string",    "normalize": "E164"      },
    { "path": "skills",        "from": "skills[].name", "type": "string[]", "normalize": "canonical" },
    { "path": "headline",      "type": "string"  },
    { "path": "location",      "type": "object"  },
    { "path": "experience",    "type": "string[]" },
    { "path": "education",     "type": "string[]" }
  ],
  "include_confidence": true,
  "on_missing": "null"
}
```

---

## Source Types Supported

### Structured Sources

#### Recruiter CSV (`adapters/recruiter_csv.py`)
- Reads a CSV where each row is one candidate
- Column name mapping is flexible (aliases: `name`/`full_name`, `email`/`emails`, `mobile`/`phone`, etc.)
- Handles Excel scientific-notation phone numbers (e.g. `9.17484E+11` → `+919174840000`)
- Multi-value fields split on `;`, `,`, `/`, `|`
- Confidence: **1.0** (direct structured field)

### Unstructured Sources

#### PDF Resume (`adapters/resume_pdf.py`)
- Extracts plain text via **PyMuPDF** (`fitz`)
- Regex extraction for: emails, phone numbers (international + 10-digit Indian), LinkedIn/GitHub URLs
- Section-aware parsing for Skills, Experience, Education, Achievements, Projects
- Date-range extraction for experience entries (`Jan 2020 – Present`)
- Confidence: **0.75–0.85** (regex from unstructured text)

#### GitHub Profile (`adapters/github_profile.py`)
- Calls the public **GitHub REST API** (`api.github.com/users/{username}`)
- Accepts either a full URL (`https://github.com/torvalds`) or bare username (`torvalds`)
- Extracts: confirmed GitHub URL (0.95), bio/headline (0.65), programming language skills from non-fork repos (0.60–0.80, weighted by repo share)
- Intentionally **omits** location (free-text, unreliable) and email (rarely public)
- Retry on rate-limit (429) with `Retry-After` header

---

## Merge & Conflict-Resolution Policy

### Identity Grouping
Claims from multiple sources are grouped into one candidate when any of:
- Same email address (normalised, case-insensitive)
- Same phone number (E.164 normalised)
- Same name (fuzzy match ≥ 0.80 via `SequenceMatcher`)

### Scalar Fields (`full_name`, `headline`, etc.)
1. Normalise all values to lowercase
2. Group by normalised value — find the most-agreed-on value
3. Within that group, pick the highest-confidence claim
4. Confidence = `f(count)`: 1 source → 0.60, 2 sources → 0.85, 3+ sources → 0.95

### List Fields (`emails`, `phones`, `skills`)
- Deduplicated by normalised key (phone → E.164, skill → canonical name)
- Highest-confidence value wins per key
- Skills from multiple sources boost confidence via the same `f(count)` formula

### Provenance
Every resolved field records `(field, source, method, confidence)`. Duplicate `(field, source)` pairs keep the highest confidence only. This gives full explainability: you can see exactly which source provided each value and how confident we are.

### Multi-candidate CSV
When a CSV has multiple rows (multiple candidates) alongside a PDF resume, the pipeline picks the candidate group whose claims include `resume_pdf` as a source (i.e. the person the resume belongs to). Ties broken by highest `overall_confidence`.

---

## Edge Cases Handled

| Edge Case | Handling |
|-----------|----------|
| Source file missing / unreadable | Logged as warning, pipeline continues with remaining sources |
| All sources return no data | `ValueError` raised — at least one source must yield claims |
| Excel scientific-notation phones (`9.17E+11`) | Converted to integer string before E.164 parsing |
| Phone in PDF that looks like a date fragment | Strict regex (10–15 consecutive digits OR `+` prefix) avoids false matches |
| Conflicting names across sources | Most-agreed-on value wins; confidence scales with agreement count |
| Required field missing with `on_missing: error` | `ValueError` raised by `project.py`, propagated through `pipeline.py` to CLI (`sys.exit(1)`) |
| Required field missing with `on_missing: null` | Field present in output as `null` |
| Required field missing with `on_missing: omit` | Field absent from output — validate does not re-flag it |
| Type mismatch on required field | `ValueError` from `validate.check()` |
| Type mismatch on optional field | Warning logged only, pipeline continues |
| GitHub API rate limit (429) | Waits `Retry-After` seconds and retries up to 2 times |
| GitHub returns 404 | Logged as warning, returns empty claims |
| Unknown column in CSV | Silently skipped (unmapped column) |
| Empty string / empty list treated as missing | `project.py` treats `""` and `[]` the same as `None` |

---

## Project Structure

```
ef_candiadte_tf/
│
├── adapters/
│   ├── recruiter_csv.py      # Structured CSV → RawFieldValue claims
│   ├── resume_pdf.py         # PDF resume text → RawFieldValue claims
│   └── github_profile.py     # GitHub REST API → RawFieldValue claims
│
├── configs/
│   ├── default_config.json   # Full canonical schema output config
│   └── custom_config.json    # Compact renamed-field config
│
├── sample_inputs/
│   └── sample.csv            # Two-row recruiter CSV for quick testing
│
├── output/                   # Populated at runtime
│   └── profile.json
│
├── tests/
│   ├── test_validate.py                        # 21 unit tests for validate.check()
│   ├── test_project.py                         # 34 unit tests for project.project()
│   └── test_pipeline_validate_propagation.py   # 6 integration tests for the bug fix
│
├── candidate_schema.py   # Pydantic models: Candidate, Skill, Experience, etc.
├── normalize.py          # Phone (E.164), date (YYYY-MM), skill (canonical name)
├── merge.py              # Claim grouping, conflict resolution, Candidate builder
├── project.py            # Config-driven projection: path resolution, normalizers
├── validate.py           # Post-projection validation: required fields, type checks
├── pipeline.py           # Orchestrator: extract → merge → project → validate
├── main.py               # CLI entry point (argparse)
├── app.py                # Streamlit UI
└── requirements.txt
```

---

## Setup & Installation

### Prerequisites
- Python 3.10 or higher
- `pip`

### Install

```bash
# 1. Clone the repo
git clone <your-repo-url>
cd ef_candiadte_tf

# 2. Create and activate a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
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

### 3. Install dependencies
```
pip install -r requirements.txt
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

```
python main.py [--csv PATH] [--resume PATH] [--github-url URL]
               [--config PATH] [--output PATH] [--full] [--quiet]
```

At least **one** of `--csv`, `--resume`, or `--github-url` is required.

#### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--csv PATH` | — | Path to recruiter CSV file |
| `--resume PATH` | — | Path to PDF resume |
| `--github-url URL` | — | GitHub profile URL or bare username |
| `--config PATH` | `configs/default_config.json` | Projection config JSON |
| `--output PATH` | `output/profile.json` | Where to write the projected JSON |
| `--full` | off | Also write full canonical record to `output/candidate_full.json` |
| `--quiet` | off | Suppress INFO logs (only warnings/errors shown) |

#### Examples

**CSV only — default schema:**
```bash
python main.py --csv sample_inputs/sample.csv
```

**CSV + custom config (renamed fields, E.164 phones, canonical skills):**
```bash
python main.py --csv sample_inputs/sample.csv --config configs/custom_config.json
```

**PDF resume only:**
```bash
python main.py --resume path/to/resume.pdf
```

**All three sources combined:**
```bash
python main.py \
  --csv sample_inputs/sample.csv \
  --resume path/to/resume.pdf \
  --github-url https://github.com/octocat \
  --config configs/custom_config.json \
  --output output/profile.json \
  --full
```

**GitHub profile only:**
```bash
python main.py --github-url torvalds
```

**Quiet mode (no INFO logs):**
```bash
python main.py --csv sample_inputs/sample.csv --quiet
```

#### CLI Output

The CLI prints a summary table to stdout and writes the projected JSON to `--output`:

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

## Assumptions & Descoped Items

| Item | Decision |
|------|----------|
| **LinkedIn scraping** | Descoped — LinkedIn's ToS prohibits automated scraping; no public API is available without a partnership. The `links.linkedin` field is populated from CSV or PDF if present. |
| **DOCX resumes** | Descoped for time. PyMuPDF handles PDF; DOCX would need `python-docx`. The adapter interface is the same, so it's a straightforward extension. |
| **Recruiter notes (.txt)** | Descoped. The resume adapter handles free-text extraction; `.txt` notes would follow the same pattern with a simpler adapter. |
| **Name as merge key** | Used at fuzzy threshold 0.80 to handle minor variations (e.g. "Priya Nair" vs "Priya S. Nair"). Threshold chosen to avoid false merges. |
| **Location parsing** | GitHub returns free-text location (e.g. "Earth", "Bengaluru, India") — too unreliable to split into city/region/country, so intentionally omitted from the GitHub adapter. |
| **Scale** | The pipeline is stateless and processes one candidate at a time. For thousands of candidates, wrap `run_pipeline` in a process pool or queue; no internal state blocks parallelism. |
| **ATS JSON blob** | Not implemented as a dedicated adapter. JSON blobs with arbitrary field names can be mapped via the config's `"from"` key if they first go through a thin normalisation shim. |
