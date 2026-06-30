from __future__ import annotations
import logging
import re
import time
from typing import List

import requests

from candidate_schema import RawFieldValue

logger = logging.getLogger(__name__)

_API_BASE = "https://api.github.com"
_HEADERS = {"Accept": "application/vnd.github+json"}


def _username_from_input(raw: str) -> str:
    """
    Accept either a full GitHub URL or a bare username.
    e.g. 'https://github.com/torvalds' → 'torvalds'
         'torvalds' → 'torvalds'
    """
    raw = raw.strip().rstrip("/")
    match = re.search(r"github\.com/([\w\-]+)", raw, re.IGNORECASE)
    return match.group(1) if match else raw


def _safe_get(url: str, retries: int = 2) -> dict | list | None:
    """GET with basic retry on rate-limit (429) and transient errors."""
    for attempt in range(retries + 1):
        try:
            resp = requests.get(url, headers=_HEADERS, timeout=10)
            if resp.status_code == 200:
                return resp.json()
            if resp.status_code == 404:
                logger.warning(f"github_profile: 404 for {url}")
                return None
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 15))
                logger.warning(f"github_profile: rate limited, waiting {wait}s")
                time.sleep(wait)
                continue
            logger.warning(f"github_profile: HTTP {resp.status_code} for {url}")
            return None
        except requests.RequestException as e:
            logger.warning(f"github_profile: request error ({e}), attempt {attempt + 1}")
            time.sleep(2)
    return None


def extract(github_input: str) -> List[RawFieldValue]:
    """
    Hit the GitHub REST API for a user profile and their public repos.

    Only extracts:
      - links.github  (confirmed URL, high confidence)
      - headline/bio  (single source → 0.65)
      - language skills from repos (weighted by repo count, 0.60–0.80)

    Intentionally omitted:
      - location: GitHub returns a free-text string ("Earth", "Bengaluru, India").
        Splitting it into city/region/country is unreliable; callers should use
        CSV or resume for structured location.
      - links.portfolio/blog: too noisy (many users leave it blank or put non-URLs).
      - email: rarely public; causes duplicate-provenance noise when the CSV
        already has the same email at 1.0 confidence.
    """
    claims: List[RawFieldValue] = []
    username = _username_from_input(github_input)
    if not username:
        logger.warning("github_profile: empty username, skipping")
        return claims

    # ── User profile ──────────────────────────────────────────────────────────
    profile = _safe_get(f"{_API_BASE}/users/{username}")
    if not profile or not isinstance(profile, dict):
        return claims

    def add(field: str, value, confidence: float = 0.65):
        if value is not None and str(value).strip():
            claims.append(RawFieldValue(
                field=field,
                value=str(value).strip(),
                source="github_api",
                method="rest_api",
                confidence=confidence,
            ))

    # Confirmed canonical GitHub URL — high confidence
    add("links.github", profile.get("html_url"), confidence=0.95)

    # Bio is a free-text field; single source → lower confidence band
    bio = profile.get("bio")
    if bio and bio.strip():
        add("headline", bio, confidence=0.65)

    # ── Repos → language skills ───────────────────────────────────────────────
    repos = _safe_get(f"{_API_BASE}/users/{username}/repos?per_page=100&sort=updated")
    if repos and isinstance(repos, list):
        lang_counts: dict[str, int] = {}
        for repo in repos:
            # Skip forks — they inflate language counts with upstream code
            if repo.get("fork"):
                continue
            lang = repo.get("language")
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1

        if lang_counts:
            total = sum(lang_counts.values()) or 1
            # Top 10 languages; confidence weighted by share of non-fork repos.
            # Range: 0.60 (rare language) → 0.80 (dominant language).
            # Single-source cap at 0.80 per spec (multi-source bumps further in merge).
            for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1])[:10]:
                lang_conf = round(0.60 + 0.20 * (count / total), 3)
                claims.append(RawFieldValue(
                    field="skills",
                    value=lang,
                    source="github_api",
                    method="repo_language_count",
                    confidence=min(lang_conf, 0.80),
                ))

    logger.info(f"github_profile: extracted {len(claims)} claims for '{username}'")
    return claims