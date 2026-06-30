from __future__ import annotations
import json
import logging
from typing import Optional, Tuple

from adapters import recruiter_csv, resume_pdf, github_profile
from merge import resolve
from project import project as project_output
from candidate_schema import Candidate
from validate import check

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = "configs/default_config.json"


def load_config(config_path: Optional[str] = None) -> dict:
    """Load a JSON config file. Falls back to default_config.json."""
    path = config_path or _DEFAULT_CONFIG_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning(f"pipeline: config '{path}' not found, using empty config")
        return {"fields": [], "include_confidence": True, "on_missing": "null"}
    except json.JSONDecodeError as e:
        logger.warning(f"pipeline: invalid JSON in '{path}': {e}, using empty config")
        return {"fields": [], "include_confidence": True, "on_missing": "null"}


def run_pipeline(
    csv_path: Optional[str] = None,
    resume_path: Optional[str] = None,
    github_url: Optional[str] = None,
    config_path: Optional[str] = None,
    config_dict: Optional[dict] = None,
) -> Tuple[Candidate, dict]:
    """
    Orchestrate the full pipeline:
      adapters → claims → merge → candidate → project → validate → output

    Args:
        csv_path:    Path to recruiter CSV file (structured source)
        resume_path: Path to PDF resume (unstructured source)
        github_url:  GitHub profile URL or username (stretch source)
        config_path: Path to a JSON projection config file
        config_dict: Config dict passed directly (used by Streamlit UI)

    Returns:
        (candidate, output) — canonical Candidate + projected output dict
    """
    if not any([csv_path, resume_path, github_url]):
        raise ValueError(
            "At least one input source is required: --csv, --resume, or --github-url"
        )

    # ── Step 1: Extract claims from all provided sources ─────────────────────
    claims = []

    if csv_path:
        logger.info(f"pipeline: extracting from CSV '{csv_path}'")
        try:
            csv_claims = recruiter_csv.extract(csv_path)
            claims += csv_claims
            logger.info(f"pipeline: CSV yielded {len(csv_claims)} claims")
        except Exception as e:
            logger.warning(f"pipeline: CSV adapter failed — {e}, continuing")

    if resume_path:
        logger.info(f"pipeline: extracting from resume '{resume_path}'")
        try:
            pdf_claims = resume_pdf.extract(resume_path)
            claims += pdf_claims
            logger.info(f"pipeline: resume yielded {len(pdf_claims)} claims")
        except Exception as e:
            logger.warning(f"pipeline: resume adapter failed — {e}, continuing")

    if github_url:
        logger.info(f"pipeline: extracting from GitHub '{github_url}'")
        try:
            gh_claims = github_profile.extract(github_url)
            claims += gh_claims
            logger.info(f"pipeline: GitHub yielded {len(gh_claims)} claims")
        except Exception as e:
            logger.warning(f"pipeline: GitHub adapter failed — {e}, continuing")

    if not claims:
        raise ValueError(
            "All input sources returned no data. "
            "Check that files exist and are not empty/corrupt."
        )

    # ── Step 2: Merge claims into one canonical Candidate ────────────────────
    logger.info(f"pipeline: merging {len(claims)} total claims")
    candidate = resolve(claims)

    # ── Step 3: Load config ───────────────────────────────────────────────────
    config = config_dict if config_dict is not None else load_config(config_path)

    # ── Step 4: Project to output shape ──────────────────────────────────────
    logger.info("pipeline: projecting to output schema")
    output = project_output(candidate, config)

    # ── Step 5: Validate output ───────────────────────────────────────────────
    # NOTE: check() raises ValueError on hard failures (required field missing,
    # type mismatch on a required field, or on_missing=error violations).
    # We intentionally do NOT catch that here so the exception propagates to
    # the caller (CLI's except-ValueError → sys.exit(1), or the UI layer).
    logger.info("pipeline: validating output")
    check(output, config)

    return candidate, output