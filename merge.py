from __future__ import annotations
import hashlib
import logging
import uuid
from collections import defaultdict
from difflib import SequenceMatcher
from statistics import mean
from typing import Any, Dict, List, Optional, Tuple

from normalize import normalize_phone, normalize_date, normalize_skill
from candidate_schema import Candidate, Education, Experience, ProvenanceEntry, RawFieldValue, Skill

logger = logging.getLogger(__name__)

def _norm_str(s: Any) -> str:
    return str(s).strip().lower() if s else ""

def _fuzzy_match(a: str, b: str, threshold: float = 0.85) -> bool:
    return SequenceMatcher(None, _norm_str(a), _norm_str(b)).ratio() >= threshold

def _confidence_from_count(n: int) -> float:
    if n >= 3:
        return 0.95
    if n == 2:
        return 0.85
    return 0.6

def _gen_id(seed: str) -> str:
    return hashlib.md5(seed.encode()).hexdigest()[:12]

def _group_claims(all_claims: List[RawFieldValue]) -> List[List[RawFieldValue]]:
    id_claims = [c for c in all_claims if c.field == "candidate_id"]
    if not id_claims:
        return [all_claims]

    groups: Dict[str, List[RawFieldValue]] = defaultdict(list)
    current_id = None
    for claim in all_claims:
        if claim.field == "candidate_id":
            current_id = claim.value
        if current_id:
            groups[current_id].append(claim)

    return list(_merge_groups_by_contact(groups).values()) if groups else [all_claims]

def _merge_groups_by_contact(groups: Dict[str, List[RawFieldValue]]) -> Dict[str, List[RawFieldValue]]:
    keys = list(groups.keys())
    merged: Dict[str, bool] = {}

    def get_emails(claims):
        return {_norm_str(c.value) for c in claims if c.field == "emails"}

    def get_phones(claims):
        return {normalize_phone(c.value) for c in claims if c.field == "phones" and normalize_phone(c.value)}

    def get_name(claims):
        for c in claims:
            if c.field == "full_name":
                return _norm_str(c.value)
        return ""

    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            ki, kj = keys[i], keys[j]
            if merged.get(kj):
                continue
            ci, cj = groups[ki], groups[kj]
            same = (
                bool(get_emails(ci) & get_emails(cj))
                or bool(get_phones(ci) & get_phones(cj))
                # Use 0.80 threshold so slight name variations (e.g. "Priya Nair" vs
                # "Priya Nair" from different sources) still merge correctly.
                or (get_name(ci) and get_name(cj) and _fuzzy_match(get_name(ci), get_name(cj), threshold=0.80))
            )
            if same:
                groups[ki].extend(groups[kj])
                merged[kj] = True

    return {k: v for k, v in groups.items() if not merged.get(k)}

def _resolve_scalar(field: str, claims: List[RawFieldValue]) -> Tuple[Optional[Any], float, str, str]:
    if not claims:
        return None, 0.0, "", ""

    normed = []
    for c in claims:
        if field == "phones":
            n = normalize_phone(str(c.value)) or _norm_str(c.value)
        elif field in ("years_experience",):
            n = _norm_str(c.value)
        else:
            n = _norm_str(c.value)
        normed.append((n, c))

    groups = defaultdict(list)
    for n, c in normed:
        groups[n].append(c)

    best_norm = max(groups, key=lambda k: len(groups[k]))
    best_claims = groups[best_norm]
    winning = max(best_claims, key=lambda c: c.confidence)
    return str(winning.value).strip(), _confidence_from_count(len(best_claims)), winning.source, winning.method

def _resolve_list_field(claims: List[RawFieldValue], normalizer=None):
    seen = {}
    for c in claims:
        raw = str(c.value).strip()
        key = normalizer(raw) if normalizer else _norm_str(raw)
        if not key:
            continue
        if key not in seen or c.confidence > seen[key][1]:
            seen[key] = (raw, c.confidence, c.source, c.method)
    return list(seen.values())

def _build_experience_list(claims: List[RawFieldValue]) -> List[Experience]:
    companies = [c.value for c in claims if c.field == "experience.company"]
    titles = [c.value for c in claims if c.field == "experience.title"]
    starts = [normalize_date(c.value) or c.value for c in claims if c.field == "experience.start"]
    ends = [normalize_date(c.value) or c.value for c in claims if c.field == "experience.end"]
    summaries = [c.value for c in claims if c.field == "experience.summary"]

    n = max(len(companies), len(titles), len(starts), len(ends), len(summaries), 0)
    items = []
    for i in range(n):
        exp = Experience(
            company=companies[i] if i < len(companies) else None,
            title=titles[i] if i < len(titles) else None,
            start=starts[i] if i < len(starts) else None,
            end=ends[i] if i < len(ends) else None,
            summary=summaries[i] if i < len(summaries) else None,
        )
        if any([exp.company, exp.title, exp.start, exp.end, exp.summary]):
            items.append(exp)
    return items

def _build_education_list(claims: List[RawFieldValue]) -> List[Education]:
    institutions = [c.value for c in claims if c.field == "education.institution"]
    degrees      = [c.value for c in claims if c.field == "education.degree"]
    fields       = [c.value for c in claims if c.field == "education.field"]
    end_years    = [c.value for c in claims if c.field == "education.end_year"]
    start_years  = [c.value for c in claims if c.field == "education.start_year"]

    n = max(len(institutions), len(degrees), len(fields), len(end_years), len(start_years), 0)
    items = []
    for i in range(n):
        edu = Education(
            institution=institutions[i]  if i < len(institutions)  else None,
            degree=     degrees[i]       if i < len(degrees)       else None,
            field=      fields[i]        if i < len(fields)        else None,
            start_year= start_years[i]   if i < len(start_years)   else None,
            end_year=   end_years[i]     if i < len(end_years)     else None,
        )
        if any([edu.institution, edu.degree, edu.field, edu.start_year, edu.end_year]):
            items.append(edu)
    return items

def _record(
    provenance: List[ProvenanceEntry],
    field_confidences: List[float],
    field: str,
    source: str,
    method: str,
    confidence: float,
):
    """Append a provenance entry, deduplicating by (field, source).

    If an entry for this (field, source) pair already exists, keep the higher
    confidence value. This prevents duplicate rows when a CSV multi-value
    column is split into N claims for the same source.
    """
    for entry in provenance:
        if entry.field == field and entry.source == source:
            if confidence > entry.confidence:
                entry.confidence = confidence
            return  # already recorded for this (field, source) pair
    provenance.append(ProvenanceEntry(field=field, source=source, method=method, confidence=confidence))
    field_confidences.append(confidence)

def _build_candidate(claims: List[RawFieldValue]) -> Candidate:
    candidate = Candidate()
    provenance: List[ProvenanceEntry] = []
    field_confidences: List[float] = []

    def fc(name: str):
        return [c for c in claims if c.field == name]

    id_claims = fc("candidate_id")
    if id_claims:
        candidate.candidate_id = str(id_claims[0].value)
    else:
        seed = "".join(str(c.value) for c in claims[:3])
        candidate.candidate_id = _gen_id(seed) if seed else uuid.uuid4().hex[:12]

    val, conf, src, meth = _resolve_scalar("full_name", fc("full_name"))
    if val:
        candidate.full_name = val
        _record(provenance, field_confidences, "full_name", src, meth, conf)

    val, conf, src, meth = _resolve_scalar("headline", fc("headline"))
    if val:
        candidate.headline = val
        _record(provenance, field_confidences, "headline", src, meth, conf)

    email_items = _resolve_list_field(fc("emails"))
    candidate.emails = [x[0] for x in email_items]
    # Collapse to one provenance row per unique source (not one per value).
    # If a candidate has two emails both from recruiter_csv, that's one row.
    _email_sources_seen: set = set()
    for _, c, s, m in email_items:
        if s not in _email_sources_seen:
            _email_sources_seen.add(s)
            _record(provenance, field_confidences, "emails", s, m, c)

    phone_items = _resolve_list_field(fc("phones"), normalizer=lambda x: normalize_phone(x) or x)
    candidate.phones = [normalize_phone(x[0]) or x[0] for x in phone_items]
    # Same: one provenance row per source, not one per phone number.
    _phone_sources_seen: set = set()
    for _, c, s, m in phone_items:
        if s not in _phone_sources_seen:
            _phone_sources_seen.add(s)
            _record(provenance, field_confidences, "phones", s, m, c)

    for sub in ("city", "region", "country"):
        val, conf, src, meth = _resolve_scalar(f"location.{sub}", fc(f"location.{sub}"))
        if val:
            setattr(candidate.location, sub, val)
            _record(provenance, field_confidences, f"location.{sub}", src, meth, conf)

    for sub in ("linkedin", "github", "portfolio"):
        items = _resolve_list_field(fc(f"links.{sub}"))
        if items:
            chosen = items[0]
            setattr(candidate.links, sub, chosen[0])
            _record(provenance, field_confidences, f"links.{sub}", chosen[2], chosen[3], chosen[1])

    other_items = _resolve_list_field(fc("links.other"))
    candidate.links.other = [x[0] for x in other_items]

    val, conf, src, meth = _resolve_scalar("years_experience", fc("years_experience"))
    if val:
        try:
            candidate.years_experience = float(val)
            _record(provenance, field_confidences, "years_experience", src, meth, conf)
        except Exception:
            pass

    skill_map: Dict[str, Skill] = {}
    for c in fc("skills"):
        canonical = normalize_skill(str(c.value))
        key = canonical.lower()
        if key not in skill_map:
            skill_map[key] = Skill(name=canonical, confidence=c.confidence, sources=[c.source])
        else:
            if c.source not in skill_map[key].sources:
                skill_map[key].sources.append(c.source)
                skill_map[key].confidence = _confidence_from_count(len(skill_map[key].sources))
    candidate.skills = list(skill_map.values())
    if candidate.skills:
        # Emit one provenance row per skill so the table is granular and
        # explainable (e.g. "why is skills 62%?" → see each skill row).
        # field name is "skills[<name>]" to distinguish rows in the UI.
        for skill in candidate.skills:
            prov_source = skill.sources[0] if len(skill.sources) == 1 else "merge"
            prov_method = "direct_field" if prov_source != "merge" else "aggregation"
            _record(provenance, field_confidences, f"skills[{skill.name}]", prov_source, prov_method, skill.confidence)

    exp_claims = [c for c in claims if c.field.startswith("experience.")]
    candidate.experience = _build_experience_list(exp_claims)
    if candidate.experience:
        # One provenance row per experience entry, keyed by company name.
        company_claims = [c for c in exp_claims if c.field == "experience.company"]
        for i, exp in enumerate(candidate.experience):
            label = exp.company or f"entry_{i+1}"
            src = company_claims[i].source if i < len(company_claims) else "merge"
            meth = company_claims[i].method if i < len(company_claims) else "aggregation"
            _record(provenance, field_confidences, f"experience[{label}]", src, meth, 0.7)

    edu_claims = [c for c in claims if c.field.startswith("education.")]
    candidate.education = _build_education_list(edu_claims)
    if candidate.education:
        # One provenance row per education entry, keyed by institution name.
        inst_claims = [c for c in edu_claims if c.field == "education.institution"]
        for i, edu in enumerate(candidate.education):
            label = edu.institution or f"entry_{i+1}"
            src = inst_claims[i].source if i < len(inst_claims) else "merge"
            meth = inst_claims[i].method if i < len(inst_claims) else "aggregation"
            _record(provenance, field_confidences, f"education[{label}]", src, meth, 0.7)

    candidate.projects = [x[0] for x in _resolve_list_field(fc("projects"))]
    candidate.certifications = [x[0] for x in _resolve_list_field(fc("certifications"))]
    candidate.achievements = [x[0] for x in _resolve_list_field(fc("achievements"))]

    candidate.provenance = provenance
    candidate.overall_confidence = round(mean(field_confidences), 3) if field_confidences else 0.0
    return candidate

def resolve(all_claims: List[RawFieldValue]) -> Candidate:
    if not all_claims:
        return Candidate(candidate_id=uuid.uuid4().hex[:12])
    groups = _group_claims(all_claims)
    logger.info(f"merge: {len(all_claims)} claims → {len(groups)} candidate group(s)")
    candidates = [_build_candidate(g) for g in groups]

    # When there is only one candidate group (e.g. resume-only), return it
    # directly. When multiple groups exist (e.g. multi-row CSV), pick the one
    # whose claims include a resume_pdf source — that is the candidate the user
    # actually wants to profile. Fall back to highest overall_confidence.
    if len(candidates) == 1:
        return candidates[0]

    def _has_pdf_source(group_claims: List[RawFieldValue]) -> bool:
        return any(c.source == "resume_pdf" for c in group_claims)

    pdf_groups = [(c, g) for c, g in zip(candidates, groups) if _has_pdf_source(g)]
    if pdf_groups:
        # Among groups that contain PDF data, pick the highest confidence one.
        # This correctly selects Priya Nair's merged group over Aarav Sharma's
        # CSV-only group when the resume belongs to Priya Nair.
        return max(pdf_groups, key=lambda pair: pair[0].overall_confidence)[0]

    return max(candidates, key=lambda c: c.overall_confidence)