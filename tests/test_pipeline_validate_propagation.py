"""
tests/test_pipeline_validate_propagation.py
============================================
Integration tests that confirm the bug fix:

  validate.check() raising ValueError on hard failures MUST propagate out
  of run_pipeline() to the caller — NOT be silently swallowed.

The specific bug was that pipeline.py wrapped check() in a try/except
ValueError and only logged a warning, so a required-and-missing field with
on_missing='error' would silently produce output. The fix removes that
try/except so the exception reaches the CLI (which already has its own
except-ValueError → sys.exit(1)).

Test strategy:
  - We use `config_dict` so no real files are needed for the config path.
  - We use a real (minimal) CSV with a valid row so the adapter/merge succeed.
  - We mock project_output (or use a thin candidate) to isolate the validate layer.
"""

import pytest
import sys
import os

# Add project root to path so imports resolve
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import patch, MagicMock
from candidate_schema import Candidate
from pipeline import run_pipeline


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_candidate(**kwargs) -> Candidate:
    """Build a minimal Candidate for patching."""
    defaults = dict(
        candidate_id="test-001",
        full_name="Test User",
        emails=["test@example.com"],
        phones=[],
        overall_confidence=0.8,
    )
    defaults.update(kwargs)
    return Candidate(**defaults)


def _patch_pipeline(candidate: Candidate, projected_output: dict):
    """
    Context manager that short-circuits adapters + merge so we can control
    what the projection layer sees.
    """
    return patch.multiple(
        "pipeline",
        resolve=MagicMock(return_value=candidate),
        project_output=MagicMock(return_value=projected_output),
    )


# ─────────────────────────────────────────────────────────────────────────────
# The critical fix: ValueError from check() must propagate
# ─────────────────────────────────────────────────────────────────────────────

class TestValidatePropagation:
    """
    These tests verify that pipeline.run_pipeline() does NOT silently suppress
    ValueError raised by validate.check().
    """

    def test_required_field_missing_raises_out_of_run_pipeline(self):
        """
        config has a required field, output is missing it,
        on_missing='null' (default) → check() raises ValueError →
        that MUST bubble up through run_pipeline().
        """
        candidate = _make_candidate()
        projected = {}   # missing 'full_name' entirely

        config = {
            "fields": [
                {"path": "full_name", "required": True, "type": "string"}
            ],
            "on_missing": "null",
        }

        with _patch_pipeline(candidate, projected):
            # Patch adapters to avoid needing real files
            with patch("pipeline.recruiter_csv.extract", return_value=[
                MagicMock(field="candidate_id", value="test-001",
                          source="csv", method="direct_field", confidence=0.9)
            ]):
                with pytest.raises(ValueError, match="full_name"):
                    run_pipeline(csv_path="dummy.csv", config_dict=config)

    def test_on_missing_error_with_null_field_raises(self):
        """
        on_missing='error', required field present but null →
        check() raises ValueError → must propagate out of run_pipeline.
        """
        candidate = _make_candidate()
        projected = {"full_name": None}   # present but null

        config = {
            "fields": [
                {"path": "full_name", "required": True, "type": "string"}
            ],
            "on_missing": "error",
        }

        with _patch_pipeline(candidate, projected):
            with patch("pipeline.recruiter_csv.extract", return_value=[
                MagicMock(field="candidate_id", value="test-001",
                          source="csv", method="direct_field", confidence=0.9)
            ]):
                with pytest.raises(ValueError):
                    run_pipeline(csv_path="dummy.csv", config_dict=config)

    def test_valid_output_does_not_raise(self):
        """
        When output satisfies the config (required field present with correct
        type) → run_pipeline returns normally without raising.
        """
        candidate = _make_candidate()
        projected = {"full_name": "Test User"}

        config = {
            "fields": [
                {"path": "full_name", "required": True, "type": "string"}
            ],
            "on_missing": "null",
        }

        with _patch_pipeline(candidate, projected):
            with patch("pipeline.recruiter_csv.extract", return_value=[
                MagicMock(field="candidate_id", value="test-001",
                          source="csv", method="direct_field", confidence=0.9)
            ]):
                result_candidate, result_output = run_pipeline(
                    csv_path="dummy.csv", config_dict=config
                )
        assert result_output["full_name"] == "Test User"

    def test_type_mismatch_on_required_field_raises(self):
        """
        Required field has wrong type (e.g. int instead of string) →
        check() raises ValueError → must bubble up.
        """
        candidate = _make_candidate()
        projected = {"full_name": 42}   # wrong type

        config = {
            "fields": [
                {"path": "full_name", "required": True, "type": "string"}
            ],
            "on_missing": "null",
        }

        with _patch_pipeline(candidate, projected):
            with patch("pipeline.recruiter_csv.extract", return_value=[
                MagicMock(field="candidate_id", value="test-001",
                          source="csv", method="direct_field", confidence=0.9)
            ]):
                with pytest.raises(ValueError, match="full_name"):
                    run_pipeline(csv_path="dummy.csv", config_dict=config)

    def test_type_mismatch_on_optional_field_does_not_raise(self):
        """
        Optional field has wrong type → check() only logs a warning,
        run_pipeline() should still return normally.
        """
        candidate = _make_candidate()
        projected = {"years_experience": "five"}   # should be number, not string

        config = {
            "fields": [
                {"path": "years_experience", "required": False, "type": "number"}
            ],
            "on_missing": "null",
        }

        with _patch_pipeline(candidate, projected):
            with patch("pipeline.recruiter_csv.extract", return_value=[
                MagicMock(field="candidate_id", value="test-001",
                          source="csv", method="direct_field", confidence=0.9)
            ]):
                _, output = run_pipeline(csv_path="dummy.csv", config_dict=config)
        assert output["years_experience"] == "five"   # returned as-is, not raised

    def test_empty_config_fields_does_not_raise(self):
        """
        Config with no fields spec → validate has nothing to check → no error.
        """
        candidate = _make_candidate()
        projected = {}

        config = {"fields": [], "on_missing": "null"}

        with _patch_pipeline(candidate, projected):
            with patch("pipeline.recruiter_csv.extract", return_value=[
                MagicMock(field="candidate_id", value="test-001",
                          source="csv", method="direct_field", confidence=0.9)
            ]):
                result_candidate, result_output = run_pipeline(
                    csv_path="dummy.csv", config_dict=config
                )
        assert result_output == {}
