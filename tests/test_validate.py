"""
tests/test_validate.py
======================
Unit tests for validate.check().

Covers:
  - Hard failure: required field missing → ValueError raised
  - Hard failure: required field is null and on_missing != "null" → ValueError
  - Hard failure: type mismatch on required field → ValueError
  - Soft warning: type mismatch on non-required field → only logs, no raise
  - on_missing="omit": required field missing is tolerated (not in output) 
  - on_missing="error": required field null → ValueError
  - on_missing="null": required field null → accepted (null is OK)
  - Empty fields spec → passes with no errors
  - Unknown type spec → treated as valid (don't block unknown specs)
  - Field entry missing "path" key → skipped without error
"""

import pytest
from validate import check


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _config(*fields, on_missing: str = "null") -> dict:
    """Build a minimal config dict from field defs."""
    return {"fields": list(fields), "on_missing": on_missing}


def _field(path: str, *, required: bool = False, type_: str | None = None) -> dict:
    d: dict = {"path": path, "required": required}
    if type_ is not None:
        d["type"] = type_
    return d


# ─────────────────────────────────────────────────────────────────────────────
# 1. Empty fields spec — always passes
# ─────────────────────────────────────────────────────────────────────────────

class TestEmptySpec:
    def test_no_fields_passes(self):
        """Config with empty fields list should always pass."""
        check({}, _config())

    def test_no_fields_with_data_passes(self):
        check({"full_name": "Alice"}, _config())


# ─────────────────────────────────────────────────────────────────────────────
# 2. Required field checks
# ─────────────────────────────────────────────────────────────────────────────

class TestRequiredFields:
    def test_required_field_present_passes(self):
        output = {"full_name": "Alice"}
        cfg = _config(_field("full_name", required=True))
        check(output, cfg)   # must not raise

    def test_required_field_missing_from_output_raises(self):
        """Required field not in output at all → ValueError."""
        output = {}
        cfg = _config(_field("full_name", required=True))
        with pytest.raises(ValueError, match="full_name"):
            check(output, cfg)

    def test_required_field_null_on_missing_null_raises(self):
        """
        Required + null value + on_missing != 'null' → ValueError.
        (on_missing default is 'null' but check interprets null value as error
        only when on_missing is NOT 'null'.)
        """
        output = {"full_name": None}
        cfg = _config(_field("full_name", required=True), on_missing="error")
        with pytest.raises(ValueError, match="full_name"):
            check(output, cfg)

    def test_required_field_null_on_missing_null_mode_passes(self):
        """Required + null value + on_missing='null' → accepted (null is the intended behavior)."""
        output = {"full_name": None}
        cfg = _config(_field("full_name", required=True), on_missing="null")
        check(output, cfg)   # should NOT raise

    def test_required_field_missing_on_missing_omit_raises(self):
        """
        Even with on_missing='omit', if the field is truly absent from output,
        validate still adds an error (it's required and not present).
        omit means the projector may skip it; but if it's absent in output
        validate must flag it unless on_missing == 'omit'.
        """
        output = {}
        cfg = _config(_field("full_name", required=True), on_missing="omit")
        # on_missing='omit' means missing field is NOT an error at validate stage
        # (the projector already omitted it; that was intentional)
        check(output, cfg)   # should NOT raise when on_missing is 'omit'

    def test_multiple_required_fields_missing_lists_all(self):
        """ValueError message should mention every missing required field."""
        output = {}
        cfg = _config(
            _field("full_name", required=True),
            _field("emails", required=True),
        )
        with pytest.raises(ValueError) as exc_info:
            check(output, cfg)
        msg = str(exc_info.value)
        assert "full_name" in msg
        assert "emails" in msg

    def test_non_required_field_missing_passes(self):
        """Non-required field absent from output → no error."""
        output = {}
        cfg = _config(_field("headline", required=False))
        check(output, cfg)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Type checks
# ─────────────────────────────────────────────────────────────────────────────

class TestTypeChecks:
    def test_correct_string_type_passes(self):
        output = {"full_name": "Alice"}
        cfg = _config(_field("full_name", required=True, type_="string"))
        check(output, cfg)

    def test_correct_number_type_passes(self):
        output = {"years_experience": 5}
        cfg = _config(_field("years_experience", type_="number"))
        check(output, cfg)

    def test_correct_float_number_type_passes(self):
        output = {"years_experience": 5.5}
        cfg = _config(_field("years_experience", type_="number"))
        check(output, cfg)

    def test_correct_list_type_passes(self):
        output = {"emails": ["a@b.com"]}
        cfg = _config(_field("emails", type_="string[]"))
        check(output, cfg)

    def test_correct_boolean_type_passes(self):
        output = {"flag": True}
        cfg = _config(_field("flag", type_="boolean"))
        check(output, cfg)

    def test_correct_object_type_passes(self):
        output = {"location": {"city": "Bangalore"}}
        cfg = _config(_field("location", type_="object"))
        check(output, cfg)

    def test_type_mismatch_on_required_field_raises(self):
        """Wrong type on required field → ValueError (hard failure)."""
        output = {"full_name": 123}   # should be string
        cfg = _config(_field("full_name", required=True, type_="string"))
        with pytest.raises(ValueError, match="full_name"):
            check(output, cfg)

    def test_type_mismatch_on_optional_field_does_not_raise(self):
        """Wrong type on non-required field → only a log warning, no raise."""
        output = {"years_experience": "five"}   # should be number
        cfg = _config(_field("years_experience", required=False, type_="number"))
        check(output, cfg)   # must NOT raise

    def test_none_value_skips_type_check(self):
        """None value bypasses type check (it's a valid missing/null state)."""
        output = {"full_name": None}
        cfg = _config(_field("full_name", required=False, type_="string"))
        check(output, cfg)

    def test_unknown_type_spec_passes(self):
        """Unrecognised type spec → treated as valid, not blocked."""
        output = {"custom_field": "whatever"}
        cfg = _config(_field("custom_field", required=True, type_="exotic_type"))
        check(output, cfg)


# ─────────────────────────────────────────────────────────────────────────────
# 4. on_missing behaviour
# ─────────────────────────────────────────────────────────────────────────────

class TestOnMissing:
    def test_on_missing_null_required_field_absent_raises(self):
        """on_missing='null' + required field absent → error."""
        output = {}
        cfg = _config(_field("full_name", required=True), on_missing="null")
        with pytest.raises(ValueError):
            check(output, cfg)

    def test_on_missing_error_required_field_null_raises(self):
        """on_missing='error' + required field null in output → error."""
        output = {"full_name": None}
        cfg = _config(_field("full_name", required=True), on_missing="error")
        with pytest.raises(ValueError, match="full_name"):
            check(output, cfg)

    def test_on_missing_omit_required_field_absent_passes(self):
        """
        on_missing='omit' means the projector intentionally skipped missing
        fields. validate should not re-flag them.
        """
        output = {}   # field was omitted by projector
        cfg = _config(_field("full_name", required=True), on_missing="omit")
        check(output, cfg)   # must NOT raise

    def test_on_missing_null_required_field_null_passes(self):
        """on_missing='null' + required field present but null → acceptable."""
        output = {"full_name": None}
        cfg = _config(_field("full_name", required=True), on_missing="null")
        check(output, cfg)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Field entry edge cases
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_field_missing_path_key_is_skipped(self):
        """Field def without 'path' key should be silently skipped."""
        cfg = {"fields": [{"required": True, "type": "string"}], "on_missing": "null"}
        check({"something": "x"}, cfg)   # must NOT raise

    def test_config_missing_fields_key_passes(self):
        """Config without 'fields' key at all → default empty list, no error."""
        check({"full_name": "Bob"}, {})

    def test_config_missing_on_missing_defaults_to_null(self):
        """Config without 'on_missing' key defaults to 'null' behaviour."""
        output = {}
        cfg = {"fields": [{"path": "full_name", "required": True}]}
        with pytest.raises(ValueError):
            check(output, cfg)

    def test_valid_output_with_multiple_fields_passes(self):
        """All required fields present with correct types → passes cleanly."""
        output = {
            "full_name": "Alice Chen",
            "emails": ["alice@example.com"],
            "years_experience": 7,
        }
        cfg = _config(
            _field("full_name", required=True, type_="string"),
            _field("emails", required=True, type_="string[]"),
            _field("years_experience", required=False, type_="number"),
        )
        check(output, cfg)

    def test_error_message_is_descriptive(self):
        """ValueError message should clearly identify the offending field."""
        output = {}
        cfg = _config(_field("primary_email", required=True, type_="string"))
        with pytest.raises(ValueError) as exc_info:
            check(output, cfg)
        assert "primary_email" in str(exc_info.value)
        assert "missing" in str(exc_info.value).lower()
