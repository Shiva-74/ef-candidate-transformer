# Multi-Source Candidate Data Transformer

A pipeline that ingests candidate data from multiple sources (recruiter CSV, PDF resume, GitHub profile), deduplicates and merges it into a single canonical profile, and emits clean, schema-valid JSON with provenance and confidence tracking. Output shape is configurable at runtime via a JSON config — no code changes needed.

## Setup

```bash
pip install -r requirements.txt
```

Python 3.10+.

## How to Run

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

### Streamlit UI

```bash
streamlit run app.py
```

Open http://localhost:8501 — upload sources, paste a config, and view canonical + projected output side-by-side.

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

## Tests

```bash
python -m pytest tests/ -v
```

Expected: **61 passed**.

## Project Structure

```
adapters/       # per-source extractors (CSV, PDF, GitHub)
merge.py        # dedup + conflict resolution -> canonical Candidate
project.py      # runtime config-driven output projection
validate.py     # required-field / type checks, raises ValueError on hard failure
pipeline.py     # orchestrates the above, returns (Candidate, output_dict)
configs/        # default_config.json, custom_config.json
sample_inputs/  # sample CSV / resume for quick testing
tests/          # 61 tests across validate, project, and pipeline
```

## Notes

See the one-page design document (PDF) for architecture rationale, the confidence-scoring model, conflict-resolution policy, and descoped items (DOCX resumes, LinkedIn scraping, etc.).
