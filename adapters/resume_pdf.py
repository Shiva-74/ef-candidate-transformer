from __future__ import annotations
import logging
import re
from typing import List, Optional

import fitz

from candidate_schema import RawFieldValue

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[\w\.\+\-]+@[\w\.\-]+\.\w{2,}")

# Phone patterns — intentionally strict to avoid matching date fragments.
#
# Pattern A: International format starting with + (e.g. +91 98765 00001)
#   Must start with +, then 1+ digits, then separators, 7–14 more digits total.
# Pattern B: Run of 10–15 consecutive digits (e.g. 9876500001 or 919876500001)
#   No separators allowed so date fragments like "06 - 2021-12" never match.
#
# Deliberately NOT matching "(\d{3})-(\d{3})-(\d{4})" style because those
# 3-3-4 dash patterns collide too easily with date ranges in resumes.
_PHONE_RE = re.compile(
    r"(\+\d[\d\s\-\.\(\)]{6,14}\d)"   # Pattern A: international with +
    r"|"
    r"(\b\d{10,15}\b)"                  # Pattern B: 10-15 raw digits, no spaces/dashes
)
_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)

_LINKEDIN_URL_RE = re.compile(r"https?://(?:www\.)?linkedin\.com/in/[\w\-]+", re.IGNORECASE)
_GITHUB_URL_RE = re.compile(r"https?://(?:www\.)?github\.com/[\w\-]+", re.IGNORECASE)

_DATE_TOKEN = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}|\d{4}-\d{2}|\d{4}"
_DATE_RANGE_RE = re.compile(rf"({_DATE_TOKEN})\s*[-–—]\s*((?:Present|Current|Now)|{_DATE_TOKEN})", re.IGNORECASE)

_SECTION_PATTERNS = {
    # Patterns use search() not match(), so they detect the keyword anywhere
    # in the line, handling compound headers like:
    #   "ACHIEVEMENTS & EXTRACURRICULARS", "TECHNICAL SKILLS & TOOLS",
    #   "PROFESSIONAL EXPERIENCE AND EMPLOYMENT", etc.
    # The len < 60 guard in _split_sections still prevents body lines
    # from being mistaken for headers.
    "summary":        re.compile(r"\b(professional\s+summary|summary|profile|about me|objective)\b", re.IGNORECASE),
    "skills":         re.compile(r"\b(technical\s+skills|skills|competencies|technologies|tech\s+stack)\b", re.IGNORECASE),
    "experience":     re.compile(r"\b(professional\s+experience|work\s+experience|experience|employment|work\s+history)\b", re.IGNORECASE),
    "education":      re.compile(r"\b(education|academic\s+background|academics|qualifications)\b", re.IGNORECASE),
    "projects":       re.compile(r"\b(projects|personal\s+projects|key\s+projects|academic\s+projects)\b", re.IGNORECASE),
    "certifications": re.compile(r"\b(certifications?|licenses?|credentials|courses?)\b", re.IGNORECASE),
    # achievements must come AFTER certifications in the dict so that a line
    # containing only "Certifications" doesn't accidentally also match here.
    "achievements":   re.compile(r"\b(achievements?|awards?|honors?|extracurriculars?|accomplishments?)\b", re.IGNORECASE),
}

_CITY_COUNTRY_RE = re.compile(r"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*),\s*([A-Z]{2}|India|USA|United States|UK)\b")

def _extract_text(pdf_path: str) -> str:
    try:
        doc = fitz.open(pdf_path)
        text = "\n".join(page.get_text("text") for page in doc)
        doc.close()
        return text
    except Exception as e:
        logger.warning(f"resume_pdf: could not open '{pdf_path}': {e}")
        return ""

def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()

def _split_sections(lines: List[str]) -> dict:
    sections = {"header": []}
    current = "header"
    for raw in lines:
        line = _clean_line(raw)
        if not line:
            continue
        matched = False
        for name, pat in _SECTION_PATTERNS.items():
            if pat.match(line) and len(line) < 60:
                current = name
                sections.setdefault(current, [])
                matched = True
                break
        if not matched:
            sections.setdefault(current, []).append(line)
    return sections

def _guess_name(header_lines: List[str]) -> Optional[str]:
    bad = re.compile(r"@|http|linkedin|github|\d|\+|phone|email", re.IGNORECASE)
    for line in header_lines[:8]:
        if bad.search(line):
            continue
        words = line.split()
        if 2 <= len(words) <= 4 and len(line) <= 50:
            return line
    return None

def _extract_location(header_lines: List[str]) -> tuple[Optional[str], Optional[str]]:
    for line in header_lines[:10]:
        m = _CITY_COUNTRY_RE.search(line)
        if m:
            city = m.group(1).strip()
            country_raw = m.group(2).strip()
            country = "IN" if country_raw.lower() in ("india", "in") else country_raw
            return city, country
    return None, None

def _parse_experience_blocks(lines: List[str]) -> List[dict]:
    blocks = []
    current = None

    for line in lines:
        m = _DATE_RANGE_RE.search(line)
        if m:
            if current:
                blocks.append(current)
            current = {
                "company": None,
                "title": None,
                "start": m.group(1),
                "end": m.group(2),
                "summary_lines": []
            }
            prefix = line[:m.start()].strip(" -|")
            if prefix:
                parts = [p.strip() for p in re.split(r"\s{2,}| \| | - ", prefix) if p.strip()]
                if len(parts) >= 2:
                    current["title"] = parts[0]
                    current["company"] = parts[1]
                elif len(parts) == 1:
                    current["company"] = parts[0]
        else:
            if current is None:
                continue
            if current["company"] is None:
                current["company"] = line
            elif current["title"] is None:
                current["title"] = line
            else:
                current["summary_lines"].append(line)

    if current:
        blocks.append(current)

    return blocks

def _parse_education_blocks(lines: List[str]) -> List[dict]:
    """
    Parse education lines into structured blocks.
    Strategy: each block ends when we see a year.  Within a block, the
    institution is the first substantial line that isn't a year/degree token;
    the degree is identified by keyword match.  A year-range line (e.g.
    '2021 – 2023') is kept as start/end, not as institution name.
    """
    _YEAR_ONLY_RE  = re.compile(r"^[\d\s%–\-\.]+$")          # lines that are ONLY years / numbers / % — skip as institution
    _YEAR_RANGE_RE = re.compile(
        r"(\d{4})\s*[–\-]\s*(\d{4}|Present|Current|Now)",
        re.IGNORECASE,
    )
    _DEGREE_RE = re.compile(
        r"\b(B\.?\s*Tech|M\.?\s*Tech|B\.?\s*E|M\.?\s*S|B\.?\s*S|MBA|Ph\.?\s*D|Bachelor|Master|B\.Sc|M\.Sc|Diploma|HSC|SSC|SSLC|Class\s+[IVX]+|Grade\s+\d+)\b",
        re.IGNORECASE,
    )

    # Split into raw blocks: close the current block on ANY year-bearing line
    # so that single-year entries ("2018", "97%  2018") also trigger a split.
    raw_blocks: List[List[str]] = []
    current: List[str] = []
    for line in lines:
        has_year = bool(re.search(r"\b(19|20)\d{2}\b", line))
        if has_year and current:
            current.append(line)
            raw_blocks.append(current)
            current = []
        else:
            current.append(line)
    if current:
        raw_blocks.append(current)

    parsed = []
    for block in raw_blocks:
        institution = None
        degree = None
        field = None
        start_year = None
        end_year = None

        for line in block:
            # 1. Extract year range
            yr = _YEAR_RANGE_RE.search(line)
            if yr:
                start_year = yr.group(1)
                end_str = yr.group(2)
                end_year = None if re.match(r"(?i)present|current|now", end_str) else end_str
                continue

            # 2. Extract single year (e.g. "97% 2022" or standalone "2022")
            single_yr = re.search(r"\b(19|20)\d{2}\b", line)
            if single_yr and _YEAR_ONLY_RE.search(re.sub(r"\b(19|20)\d{2}\b", "", line)):
                end_year = end_year or single_yr.group(0)
                continue

            # 3. Check for degree keyword
            dm = _DEGREE_RE.search(line)
            if dm and degree is None:
                degree = dm.group(0)
                # field = rest of the line after the degree keyword
                rest = line[dm.end():].strip(" –-–|·").strip()
                if rest and len(rest) > 2:
                    field = rest
                continue

            # 4. First non-year, non-degree line → institution
            if institution is None and not _YEAR_ONLY_RE.match(line):
                institution = line

        parsed.append({
            "institution": institution,
            "degree":      degree,
            "field":       field,
            "start_year":  start_year,
            "end_year":    end_year,
        })

    return parsed

def extract(pdf_path: str) -> List[RawFieldValue]:
    claims: List[RawFieldValue] = []
    text = _extract_text(pdf_path)
    if not text.strip():
        return claims

    lines = [_clean_line(x) for x in text.splitlines() if _clean_line(x)]
    sections = _split_sections(lines)

    def add(field, value, method, confidence):
        if value is None:
            return
        v = str(value).strip()
        if v:
            claims.append(RawFieldValue(
                field=field,
                value=v,
                source="resume_pdf",
                method=method,
                confidence=confidence,
            ))

    # ── Detect name early so we can emit a candidate_id for grouping ─────────
    # Without a candidate_id from the PDF, ALL pdf claims fall into the first
    # CSV row's group and the CSV data always overrides the PDF data.
    _name_early = _guess_name(sections.get("header", []))
    import hashlib as _hs, uuid as _uuid
    _pdf_candidate_id = (
        "pdf_" + _hs.md5(_name_early.lower().strip().encode()).hexdigest()[:10]
        if _name_early
        else "pdf_" + _uuid.uuid4().hex[:10]
    )
    claims.append(RawFieldValue(
        field="candidate_id",
        value=_pdf_candidate_id,
        source="resume_pdf",
        method="derived_from_name",
        confidence=0.9,
    ))

    for email in dict.fromkeys(_EMAIL_RE.findall(text)):
        add("emails", email, "regex", 0.9)

    seen_phone = set()
    # _PHONE_RE has two groups; findall returns list of (groupA, groupB) tuples.
    # Pick whichever group matched (the other will be empty string).
    for match_tuple in _PHONE_RE.findall(text):
        phone = next((g for g in match_tuple if g), "").strip()
        if not phone:
            continue
        digits = re.sub(r"\D", "", phone)
        # Digit count must be in valid phone range
        if len(digits) < 7 or len(digits) > 15:
            continue
        if digits not in seen_phone:
            seen_phone.add(digits)
            add("phones", phone, "regex", 0.8)


    for url in dict.fromkeys(_LINKEDIN_URL_RE.findall(text)):
        add("links.linkedin", url, "regex", 0.95)

    for url in dict.fromkeys(_GITHUB_URL_RE.findall(text)):
        add("links.github", url, "regex", 0.95)

    for url in dict.fromkeys(_URL_RE.findall(text)):
        if "linkedin.com" not in url.lower() and "github.com" not in url.lower():
            add("links.other", url, "regex", 0.75)

    name = _guess_name(sections.get("header", []))
    if name:
        add("full_name", name, "heuristic_section_parse", 0.75)

    city, country = _extract_location(sections.get("header", []))
    if city:
        add("location.city", city, "heuristic_section_parse", 0.8)
    if country:
        add("location.country", country, "heuristic_section_parse", 0.8)

    if sections.get("summary"):
        add("headline", " ".join(sections["summary"][:3])[:300], "heuristic_section_parse", 0.7)

    if sections.get("skills"):
        for line in sections["skills"]:
            for part in re.split(r"[,\u2022|;/]+", line):
                skill = part.strip()
                if 1 < len(skill) < 50:
                    add("skills", skill, "heuristic_section_parse", 0.7)

    for block in _parse_experience_blocks(sections.get("experience", [])):
        add("experience.company", block.get("company"), "heuristic_section_parse", 0.7)
        add("experience.title", block.get("title"), "heuristic_section_parse", 0.7)
        add("experience.start", block.get("start"), "regex", 0.8)
        add("experience.end", block.get("end"), "regex", 0.8)
        if block.get("summary_lines"):
            add("experience.summary", " ".join(block["summary_lines"])[:500], "heuristic_section_parse", 0.65)

    for block in _parse_education_blocks(sections.get("education", [])):
        add("education.institution", block.get("institution"), "heuristic_section_parse", 0.7)
        add("education.degree",     block.get("degree"),      "heuristic_section_parse", 0.7)
        add("education.field",      block.get("field"),       "heuristic_section_parse", 0.6)
        add("education.end_year",   block.get("end_year"),    "regex", 0.8)
        add("education.start_year", block.get("start_year"),  "regex", 0.8)

    for line in sections.get("projects", []):
        add("projects", line, "heuristic_section_parse", 0.7)

    for line in sections.get("certifications", []):
        add("certifications", line, "heuristic_section_parse", 0.7)

    for line in sections.get("achievements", []):
        add("achievements", line, "heuristic_section_parse", 0.7)

    years = re.findall(r"\b(19|20)\d{2}\b", text)
    if len(years) >= 2:
        nums = [int(y) for y in years]
        span = max(nums) - min(nums)
        if 0 < span <= 40:
            add("years_experience", str(span), "heuristic_section_parse", 0.55)

    logger.info(f"resume_pdf: extracted {len(claims)} claims from '{pdf_path}'")
    return claims