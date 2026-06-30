from __future__ import annotations
import logging
from typing import Any, Dict, List

from pydantic import BaseModel as _BaseModel

logger = logging.getLogger(__name__)


# Type checkers — maps config type string → accepted Python types
_TYPE_MAP = {
    "string":   (str,),
    "number":   (int, float),
    "boolean":  (bool,),
    "string[]": (list,),
    "number[]": (list,),
    "object":   (dict, _BaseModel),   # accept both plain dicts and Pydantic models
}


def _check_type(value: Any, type_spec: str) -> bool:
    """Return True if value matches the expected type spec."""
    if value is None:
        return True
    expected = _TYPE_MAP.get(type_spec)
    if expected is None:
        return True   # Unknown type spec — don't block
    return isinstance(value, expected)


def check(output: dict, config: dict) -> None:
    """
    Validate the projected output dict against the config's field specs.

    Raises ValueError with a descriptive message on hard failures.
    Logs warnings for soft failures (type mismatches on non-required fields).
    """
    fields_spec: List[dict] = config.get("fields", [])
    on_missing: str         = config.get("on_missing", "null")
    errors: List[str]       = []

    for field_def in fields_spec:
        output_key = field_def.get("path")
        required   = field_def.get("required", False)
        type_spec  = field_def.get("type")

        if not output_key:
            continue

        value = output.get(output_key)

        # ── Required field check ──────────────────────────────────────────────
        if required:
            if output_key not in output:
                if on_missing != "omit":
                    errors.append(
                        f"Required field '{output_key}' is missing from output."
                    )
                continue
            if value is None and on_missing != "null":
                errors.append(
                    f"Required field '{output_key}' is null in output."
                )
                continue

        # ── Type check ────────────────────────────────────────────────────────
        if type_spec and value is not None:
            if not _check_type(value, type_spec):
                actual_type = type(value).__name__
                msg = (
                    f"Type mismatch for '{output_key}': "
                    f"expected '{type_spec}', got '{actual_type}' "
                    f"(value={repr(value)[:60]})"
                )
                if required:
                    errors.append(msg)
                else:
                    logger.warning(f"validate: {msg}")

    if errors:
        raise ValueError(
            "Output validation failed:\n" + "\n".join(f"  • {e}" for e in errors)
        )

    logger.info(
        f"validate: output passed all checks ({len(fields_spec)} fields verified)"
    )