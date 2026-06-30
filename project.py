from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from normalize import normalize_phone, normalize_date, normalize_skill
from candidate_schema import Candidate

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Serialization helper
# ─────────────────────────────────────────────────────────────────────────────

def _to_serializable(value: Any) -> Any:
    """
    Recursively convert Pydantic models → plain dicts so json.dump works.
    Lists of models → lists of dicts.
    """
    if isinstance(value, BaseModel):
        return value.model_dump()
    if isinstance(value, list):
        return [_to_serializable(item) for item in value]
    return value


# ─────────────────────────────────────────────────────────────────────────────
# Path resolver — supports these patterns:
#   "full_name"          → candidate.full_name
#   "location.country"   → candidate.location.country
#   "emails[0]"          → candidate.emails[0]
#   "skills[].name"      → [s.name for s in candidate.skills]
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_path(candidate: Candidate, path: str) -> Any:
    """
    Walk a dotted/bracket path on the Candidate object.
    Returns None if any step is missing — never raises.
    """
    # List-map pattern: "skills[].name" → extract attribute from each item
    if "[]." in path:
        list_part, attr = path.split("[].", 1)
        list_val = _resolve_path(candidate, list_part)
        if not isinstance(list_val, list):
            return None
        result = []
        for item in list_val:
            v = _get_attr_or_key(item, attr)
            if v is not None:
                result.append(v)
        return result if result else None

    parts = _split_path(path)
    current: Any = candidate

    for part in parts:
        if current is None:
            return None

        # Bracket index: "emails[0]" → attr="emails", index=0
        if "[" in part and part.endswith("]"):
            attr, idx_str = part[:-1].split("[", 1)
            current = _get_attr_or_key(current, attr)
            if current is None:
                return None
            try:
                idx = int(idx_str)
                current = current[idx]
            except (IndexError, ValueError, TypeError):
                return None
        else:
            current = _get_attr_or_key(current, part)

    return current


def _get_attr_or_key(obj: Any, key: str) -> Any:
    """Try getattr first (Pydantic model), then dict key access."""
    if obj is None:
        return None
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key)
    return None


def _split_path(path: str) -> List[str]:
    """Split 'location.country' → ['location', 'country'], preserving brackets."""
    parts = []
    current = ""
    for ch in path:
        if ch == "." and "[" not in current:
            if current:
                parts.append(current)
            current = ""
        else:
            current += ch
    if current:
        parts.append(current)
    return parts


# ─────────────────────────────────────────────────────────────────────────────
# Normalizer dispatcher
# ─────────────────────────────────────────────────────────────────────────────

def _apply_normalize(value: Any, normalize_spec: str) -> Any:
    """
    Apply a named normalizer to a value or list of values.
    Supported specs: "E164", "canonical" (skills), "date"
    """
    if value is None:
        return None

    spec = normalize_spec.upper()

    def _normalize_one(v):
        if spec == "E164":
            return normalize_phone(str(v)) or v
        if spec == "CANONICAL":
            return normalize_skill(str(v))
        if spec == "DATE":
            return normalize_date(str(v)) or v
        return v

    if isinstance(value, list):
        return [_normalize_one(item) for item in value]
    return _normalize_one(value)


# ─────────────────────────────────────────────────────────────────────────────
# Confidence lookup from provenance
# ─────────────────────────────────────────────────────────────────────────────

def _get_field_confidence(candidate: Candidate, field_path: str) -> Optional[float]:
    """
    Look up the confidence score for a field from the candidate's provenance list.
    Returns None if not found.
    """
    lookup = field_path.replace("[]", "").replace("[0]", "")
    for entry in candidate.provenance:
        if entry.field == lookup or entry.field.startswith(lookup):
            return entry.confidence
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Main projection function
# ─────────────────────────────────────────────────────────────────────────────

def project(candidate: Candidate, config: dict) -> dict:
    """
    Project a canonical Candidate into a config-shaped output dict.

    Config structure:
    {
      "fields": [
        { "path": "output_key", "from": "source_path", "type": "string",
          "required": true, "normalize": "E164" }
      ],
      "include_confidence": true,
      "on_missing": "null"   // "null" | "omit" | "error"
    }
    """
    fields_spec: List[dict] = config.get("fields", [])
    include_confidence: bool = config.get("include_confidence", False)
    on_missing: str = config.get("on_missing", "null")

    output: Dict[str, Any] = {}

    for field_def in fields_spec:
        output_key     = field_def.get("path")
        source_path    = field_def.get("from", output_key)
        required       = field_def.get("required", False)
        normalize_spec = field_def.get("normalize")

        if not output_key:
            logger.warning("project: field entry missing 'path', skipping")
            continue

        # 1 — Resolve value from canonical candidate
        value = _resolve_path(candidate, source_path)

        # 2 — Apply normalizer if specified
        if normalize_spec and value is not None:
            value = _apply_normalize(value, normalize_spec)

        # 3 — Handle missing values
        if value is None or value == [] or value == "":
            if required:
                if on_missing == "error":
                    raise ValueError(
                        f"Validation error: required field '{output_key}' "
                        f"(from '{source_path}') is missing in the candidate profile."
                    )
                elif on_missing == "omit":
                    continue
                else:
                    output[output_key] = None
            else:
                if on_missing == "omit":
                    continue
                else:
                    output[output_key] = None
            continue

        # 4 — Serialize Pydantic models → plain dicts/lists for JSON output
        value = _to_serializable(value)

        # 5 — Write resolved value
        output[output_key] = value

        # 6 — Attach per-field confidence if requested
        if include_confidence:
            conf = _get_field_confidence(candidate, source_path)
            if conf is not None:
                output[f"_{output_key}_confidence"] = conf

    # 7 — Attach overall confidence if requested
    if include_confidence:
        output["_overall_confidence"] = candidate.overall_confidence

    return output