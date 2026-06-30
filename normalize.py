from __future__ import annotations
import re
from typing import Optional

import dateparser
import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat

# ── Skill alias dictionary (case-insensitive lookup) ─────────────────────────

_SKILL_MAP: dict[str, str] = {
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "dl": "Deep Learning",
    "deep learning": "Deep Learning",
    "ai": "Artificial Intelligence",
    "nlp": "NLP",
    "natural language processing": "NLP",
    "cv": "Computer Vision",
    "computer vision": "Computer Vision",
    "tensorflow": "TensorFlow",
    "tf": "TensorFlow",
    "pytorch": "PyTorch",
    "py torch": "PyTorch",
    "torch": "PyTorch",
    "sklearn": "Scikit-learn",
    "scikit-learn": "Scikit-learn",
    "scikit learn": "Scikit-learn",
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "py": "Python",
    "python": "Python",
    "sql": "SQL",
    "mysql": "MySQL",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "react": "React",
    "reactjs": "React",
    "react.js": "React",
    "node": "Node.js",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "docker": "Docker",
    "kubernetes": "Kubernetes",
    "k8s": "Kubernetes",
    "aws": "AWS",
    "gcp": "GCP",
    "azure": "Azure",
    "git": "Git",
    "github": "GitHub",
    "linux": "Linux",
    "bash": "Bash",
    "rest": "REST API",
    "restapi": "REST API",
    "rest api": "REST API",
    "html": "HTML",
    "css": "CSS",
    "java": "Java",
    "c++": "C++",
    "cpp": "C++",
    "golang": "Go",
    "go": "Go",
    "rust": "Rust",
    "r": "R",
    "matlab": "MATLAB",
    "spark": "Apache Spark",
    "apache spark": "Apache Spark",
    "hadoop": "Hadoop",
    "mongodb": "MongoDB",
    "mongo": "MongoDB",
    "redis": "Redis",
    "fastapi": "FastAPI",
    "flask": "Flask",
    "django": "Django",
    "spring": "Spring",
    "springboot": "Spring Boot",
    "spring boot": "Spring Boot",
}


# ── Public normalizers ────────────────────────────────────────────────────────

def normalize_phone(raw: str, default_region: str = "IN") -> Optional[str]:
    """
    Parse raw phone string and return E.164 format.
    Returns None if the string cannot be parsed — never invents a number.

    Handles:
    - Scientific notation from Excel-exported CSVs (e.g. "9.17484E+11")
    - Standard international formats (+91..., 0044..., etc.)
    - Indian 10-digit mobile numbers
    """
    if not raw or not str(raw).strip():
        return None
    raw = str(raw).strip()

    # ── Pre-process scientific notation (Excel saves large numbers as 9.17E+11)
    # Python's float() correctly handles "9.17484E+11" → 917484000000.0
    _SCI_RE = re.compile(r'^[\+\-]?\d+\.?\d*[eE][\+\-]?\d+$')
    if _SCI_RE.match(raw):
        try:
            raw = str(int(float(raw)))
        except (ValueError, OverflowError):
            return None

    try:
        parsed = phonenumbers.parse(raw, default_region)
        if phonenumbers.is_valid_number(parsed):
            return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)
    except NumberParseException:
        pass
    return None


def normalize_date(raw: str) -> Optional[str]:
    """
    Parse a date string and return YYYY-MM or YYYY.
    Returns None on failure — never invents a date.
    """
    if not raw or not str(raw).strip():
        return None
    raw = str(raw).strip()

    # Year-only check first (avoids dateparser misinterpreting "2020" as today)
    if re.fullmatch(r"\d{4}", raw):
        return raw

    # "Present" / "Current" → return as-is for display
    if raw.lower() in ("present", "current", "now", "ongoing"):
        return "Present"

    parsed = dateparser.parse(
        raw,
        settings={
            "PREFER_DAY_OF_MONTH": "first",
            "RETURN_TIME_AS_PERIOD": False,
            "PREFER_LOCALE_DATE_ORDER": True,
        },
    )
    if parsed:
        return parsed.strftime("%Y-%m")
    return None


def normalize_skill(raw: str) -> str:
    """
    Map raw skill string to a canonical name.
    Falls back to title-cased original if not found in the dictionary.
    """
    if not raw:
        return raw
    key = raw.strip().lower()
    return _SKILL_MAP.get(key, raw.strip().title())