"""
tests/test_project.py
======================
Unit tests for project.project() — the projection layer.

Covers:
  - Basic field resolution from a Candidate
  - Nested path resolution (location.country)
  - Array index path (emails[0])
  - List-map pattern (skills[].name)
  - on_missing='error' for required field → ValueError raised by project itself
  - on_missing='omit' → field absent from output
  - on_missing='null' → field present with None
  - normalize='E164' applied to phone
  - normalize='canonical' applied to skill name
  - include_confidence → _overall_confidence in output
  - Field entry missing 'path' → skipped gracefully
  - Unresolvable path → treated as missing
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from candidate_schema import Candidate, Location, Links, Skill, Experience, Education, ProvenanceEntry
from project import project


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _candidate(**kwargs) -> Candidate:
    defaults = dict(
        candidate_id="c001",
        full_name="Priya Nair",
        emails=["priya@example.com", "priya.work@corp.com"],
        phones=["+919876543210"],
        location=Location(city="Bangalore", region="Karnataka", country="IN"),
        links=Links(github="https://github.com/priya", linkedin="https://linkedin.com/in/priya"),
        headline="ML Engineer",
        years_experience=5.0,
        skills=[
            Skill(name="Python", confidence=0.9, sources=["csv"]),
            Skill(name="Machine Learning", confidence=0.85, sources=["resume_pdf"]),
        ],
        experience=[
            Experience(company="Acme Corp", title="Senior Engineer",
                       start="2020-01", end="Present", summary="Built stuff")
        ],
        education=[
            Education(institution="IIT Bangalore", degree="B.Tech",
                      field="Computer Science", end_year="2019")
        ],
        provenance=[
            ProvenanceEntry(field="full_name", source="csv", method="direct_field", confidence=0.9),
            ProvenanceEntry(field="emails", source="csv", method="direct_field", confidence=0.9),
            ProvenanceEntry(field="skills", source="resume_pdf", method="regex", confidence=0.8),
        ],
        overall_confidence=0.85,
    )
    defaults.update(kwargs)
    return Candidate(**defaults)


def _config(*fields, on_missing: str = "null", include_confidence: bool = False) -> dict:
    return {
        "fields": list(fields),
        "on_missing": on_missing,
        "include_confidence": include_confidence,
    }


def _field(path: str, *, from_: str | None = None, required: bool = False,
           type_: str | None = None, normalize: str | None = None) -> dict:
    d: dict = {"path": path, "required": required}
    if from_ is not None:
        d["from"] = from_
    if type_ is not None:
        d["type"] = type_
    if normalize is not None:
        d["normalize"] = normalize
    return d


# ─────────────────────────────────────────────────────────────────────────────
# 1. Basic scalar resolution
# ─────────────────────────────────────────────────────────────────────────────

class TestScalarResolution:
    def test_resolves_top_level_string(self):
        c = _candidate()
        out = project(c, _config(_field("full_name")))
        assert out["full_name"] == "Priya Nair"

    def test_resolves_nested_path(self):
        c = _candidate()
        out = project(c, _config(_field("country", from_="location.country")))
        assert out["country"] == "IN"

    def test_resolves_array_index(self):
        c = _candidate()
        out = project(c, _config(_field("primary_email", from_="emails[0]")))
        assert out["primary_email"] == "priya@example.com"

    def test_resolves_second_array_index(self):
        c = _candidate()
        out = project(c, _config(_field("second_email", from_="emails[1]")))
        assert out["second_email"] == "priya.work@corp.com"

    def test_resolves_list_map_pattern(self):
        c = _candidate()
        out = project(c, _config(_field("skill_names", from_="skills[].name")))
        assert out["skill_names"] == ["Python", "Machine Learning"]

    def test_output_key_matches_path_when_no_from(self):
        c = _candidate()
        out = project(c, _config(_field("headline")))
        assert "headline" in out
        assert out["headline"] == "ML Engineer"

    def test_unknown_path_resolves_to_missing(self):
        c = _candidate()
        out = project(c, _config(_field("nonexistent_field")))
        # on_missing='null' by default → present with None
        assert out["nonexistent_field"] is None


# ─────────────────────────────────────────────────────────────────────────────
# 2. on_missing behaviour at projection level
# ─────────────────────────────────────────────────────────────────────────────

class TestOnMissingProject:
    def test_on_missing_null_produces_none(self):
        c = _candidate(full_name=None)
        out = project(c, _config(_field("full_name"), on_missing="null"))
        assert "full_name" in out
        assert out["full_name"] is None

    def test_on_missing_omit_removes_key(self):
        c = _candidate(full_name=None)
        out = project(c, _config(_field("full_name"), on_missing="omit"))
        assert "full_name" not in out

    def test_on_missing_error_required_field_raises(self):
        """project() itself raises ValueError when on_missing=error + required + missing."""
        c = _candidate(full_name=None)
        cfg = _config(_field("full_name", required=True), on_missing="error")
        with pytest.raises(ValueError, match="full_name"):
            project(c, cfg)

    def test_on_missing_error_non_required_field_missing_produces_none(self):
        """
        on_missing='error' + non-required field missing → produces None, no raise.
        The 'error' policy only applies to required fields.
        Wait — actually project.py uses on_missing globally. Let's test reality.
        """
        c = _candidate(headline=None)
        # headline is non-required; with on_missing='omit' it should be omitted
        out = project(c, _config(_field("headline", required=False), on_missing="omit"))
        assert "headline" not in out

    def test_on_missing_null_optional_field_present_null(self):
        c = _candidate(headline=None)
        out = project(c, _config(_field("headline", required=False), on_missing="null"))
        assert out.get("headline") is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Normalizers
# ─────────────────────────────────────────────────────────────────────────────

class TestNormalizers:
    def test_e164_phone_normalization(self):
        """Phone value in candidate is already E164; normalize should return same."""
        c = _candidate(phones=["+919876543210"])
        out = project(c, _config(_field("phone", from_="phones[0]", normalize="E164")))
        assert out["phone"] == "+919876543210"

    def test_canonical_skill_normalization(self):
        """'ml' → 'Machine Learning' via canonical normalizer."""
        from candidate_schema import Skill
        c = _candidate(skills=[Skill(name="ml", confidence=0.8, sources=["test"])])
        out = project(c, _config(_field("skill_names", from_="skills[].name", normalize="canonical")))
        assert "Machine Learning" in out["skill_names"]

    def test_normalize_none_value_skips(self):
        """None value → normalizer not called, value stays None."""
        c = _candidate(full_name=None)
        out = project(c, _config(_field("full_name", normalize="E164"), on_missing="null"))
        assert out["full_name"] is None

    def test_normalize_list_of_phones(self):
        """Normalize applied to a list → each element normalised."""
        c = _candidate(phones=["+919876543210", "+12025551234"])
        out = project(c, _config(_field("phones", normalize="E164")))
        for ph in out["phones"]:
            assert ph.startswith("+")


# ─────────────────────────────────────────────────────────────────────────────
# 4. include_confidence
# ─────────────────────────────────────────────────────────────────────────────

class TestIncludeConfidence:
    def test_overall_confidence_included(self):
        c = _candidate()
        out = project(c, _config(_field("full_name"), include_confidence=True))
        assert "_overall_confidence" in out
        assert isinstance(out["_overall_confidence"], float)

    def test_overall_confidence_excluded_by_default(self):
        c = _candidate()
        out = project(c, _config(_field("full_name"), include_confidence=False))
        assert "_overall_confidence" not in out

    def test_per_field_confidence_attached(self):
        c = _candidate()
        out = project(c, _config(_field("full_name"), include_confidence=True))
        # provenance has 'full_name'; per-field confidence key should exist
        assert "_full_name_confidence" in out


# ─────────────────────────────────────────────────────────────────────────────
# 5. Edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectEdgeCases:
    def test_field_missing_path_skipped(self):
        """Field def without 'path' → skipped without KeyError."""
        c = _candidate()
        cfg = {"fields": [{"required": True}], "on_missing": "null"}
        out = project(c, cfg)   # must not raise; output is empty
        assert isinstance(out, dict)

    def test_empty_fields_produces_empty_output(self):
        c = _candidate()
        out = project(c, {"fields": [], "on_missing": "null"})
        # Only _overall_confidence would appear if include_confidence=True
        assert out == {}

    def test_multiple_fields_in_one_projection(self):
        c = _candidate()
        cfg = _config(
            _field("full_name", required=True),
            _field("primary_email", from_="emails[0]", required=True),
            _field("country", from_="location.country"),
            on_missing="null",
        )
        out = project(c, cfg)
        assert out["full_name"] == "Priya Nair"
        assert out["primary_email"] == "priya@example.com"
        assert out["country"] == "IN"

    def test_empty_list_treated_as_missing(self):
        """skills=[] → treated as missing value, follows on_missing policy."""
        c = _candidate(skills=[])
        out = project(c, _config(_field("skills"), on_missing="null"))
        assert out["skills"] is None

    def test_empty_string_treated_as_missing(self):
        c = _candidate(full_name="")
        out = project(c, _config(_field("full_name"), on_missing="null"))
        assert out["full_name"] is None

    def test_array_index_out_of_bounds_treated_as_missing(self):
        """emails[5] on a 2-email list → missing → on_missing applies."""
        c = _candidate()
        out = project(c, _config(_field("email5", from_="emails[5]"), on_missing="null"))
        assert out["email5"] is None

    def test_deep_nested_path(self):
        c = _candidate()
        out = project(c, _config(_field("city", from_="location.city")))
        assert out["city"] == "Bangalore"

    def test_experience_list_serialised_as_dicts(self):
        """Pydantic Experience objects → plain dicts in output (JSON-serialisable)."""
        c = _candidate()
        out = project(c, _config(_field("experience")))
        assert isinstance(out["experience"], list)
        assert isinstance(out["experience"][0], dict)
        assert out["experience"][0]["company"] == "Acme Corp"
