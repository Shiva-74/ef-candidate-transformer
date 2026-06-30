from __future__ import annotations
import logging
import uuid
import re
from typing import List

import pandas as pd

from candidate_schema import RawFieldValue

logger = logging.getLogger(__name__)

_COLUMN_MAP = {
    "name": "full_name",
    "full_name": "full_name",
    "fullname": "full_name",

    "email": "emails",
    "emails": "emails",
    "email_address": "emails",
    "emailaddress": "emails",

    "phone": "phones",
    "phones": "phones",
    "phone_number": "phones",
    "mobile": "phones",
    "mobile_number": "phones",

    "current_company": "experience.company",
    "company": "experience.company",
    "employer": "experience.company",

    "title": "experience.title",
    "job_title": "experience.title",
    "position": "experience.title",

    "linkedin": "links.linkedin",
    "linkedin_url": "links.linkedin",
    "github": "links.github",
    "github_url": "links.github",

    "location": "location.city",
    "city": "location.city",
    "country": "location.country",

    "headline": "headline",
    "summary": "headline",

    "years_experience": "years_experience",
    "experience_years": "years_experience",
}

_MULTI_SPLIT_RE = re.compile(r"[;,/|]+|\s{2,}")

def _normalize_sci_notation(value: str) -> str:
    """Convert Excel scientific notation phone numbers to digit strings.
    e.g. '9.17484E+11' → '917484000000'. Returns original string unchanged
    if it doesn't look like scientific notation.
    """
    sci_re = re.compile(r'^[\+\-]?\d+\.?\d*[eE][\+\-]?\d+$')
    if sci_re.match(value.strip()):
        try:
            return str(int(float(value.strip())))
        except (ValueError, OverflowError):
            pass
    return value


def _split_multi_value(raw: str) -> List[str]:
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []
    parts = [p.strip() for p in _MULTI_SPLIT_RE.split(text) if p.strip()]
    return parts if parts else [text]

def extract(csv_path: str) -> List[RawFieldValue]:
    claims: List[RawFieldValue] = []

    try:
        df = pd.read_csv(csv_path, dtype=str)
    except Exception as e:
        logger.warning(f"recruiter_csv: could not read '{csv_path}': {e}")
        return claims

    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    for row_idx, row in df.iterrows():
        candidate_id = str(row.get("candidate_id", "")).strip()
        if not candidate_id:
            candidate_id = f"csv_row_{row_idx}_{uuid.uuid4().hex[:6]}"

        claims.append(RawFieldValue(
            field="candidate_id",
            value=candidate_id,
            source="recruiter_csv",
            method="direct_field",
            confidence=1.0,
        ))

        for col, value in row.items():
            if col == "candidate_id":
                continue

            canonical = _COLUMN_MAP.get(col)
            if canonical is None:
                continue

            if pd.isna(value) or str(value).strip() == "":
                continue

            raw_value = str(value).strip()

            # Fix Excel scientific notation in phone fields before any splitting
            if canonical == "phones":
                raw_value = _normalize_sci_notation(raw_value)

            if canonical in ("emails", "phones", "links.other"):
                for part in _split_multi_value(raw_value):
                    claims.append(RawFieldValue(
                        field=canonical,
                        value=part,
                        source="recruiter_csv",
                        method="direct_field",
                        confidence=1.0,
                    ))
            else:
                claims.append(RawFieldValue(
                    field=canonical,
                    value=raw_value,
                    source="recruiter_csv",
                    method="direct_field",
                    confidence=1.0,
                ))

    logger.info(f"recruiter_csv: extracted {len(claims)} claims from '{csv_path}'")
    return claims