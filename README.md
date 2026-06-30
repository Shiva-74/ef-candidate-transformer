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
