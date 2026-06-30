from __future__ import annotations
import argparse
import json
import logging
import os
import sys

from pipeline import run_pipeline

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s  %(name)s — %(message)s",
)


def _print_summary(candidate, output: dict) -> None:
    """Print a short human-readable summary to stdout."""
    print("\n" + "=" * 55)
    print("  CANDIDATE PROFILE SUMMARY")
    print("=" * 55)
    print(f"  ID         : {candidate.candidate_id}")
    print(f"  Name       : {candidate.full_name or '—'}")
    print(f"  Emails     : {', '.join(candidate.emails) or '—'}")
    print(f"  Phones     : {', '.join(candidate.phones) or '—'}")

    loc = candidate.location
    loc_str = ", ".join(filter(None, [loc.city, loc.region, loc.country])) or "—"
    print(f"  Location   : {loc_str}")
    print(f"  Headline   : {(candidate.headline or '—')[:70]}")
    print(f"  Skills     : {len(candidate.skills)} found")
    print(f"  Experience : {len(candidate.experience)} entry/entries")
    print(f"  Education  : {len(candidate.education)} entry/entries")
    print(f"  Confidence : {candidate.overall_confidence:.0%}")
    print("=" * 55)
    print(f"  Sources    : {len(candidate.provenance)} provenance entries")
    print("=" * 55 + "\n")


def main():
    parser = argparse.ArgumentParser(
        prog="candidate-transformer",
        description="Multi-source candidate data transformer — Eightfold assignment",
    )
    parser.add_argument("--csv",        metavar="PATH",  help="Path to recruiter CSV file")
    parser.add_argument("--resume",     metavar="PATH",  help="Path to PDF resume file")
    parser.add_argument("--github-url", metavar="URL",   help="GitHub profile URL or username")
    parser.add_argument("--config",     metavar="PATH",  help="Path to projection config JSON (default: configs/default_config.json)")
    parser.add_argument("--output",     metavar="PATH",  default="output/profile.json", help="Output JSON path (default: output/profile.json)")
    parser.add_argument("--full",       action="store_true", help="Also write full canonical record to output/candidate_full.json")
    parser.add_argument("--quiet",      action="store_true", help="Suppress INFO logs")

    args = parser.parse_args()

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    if not any([args.csv, args.resume, args.github_url]):
        parser.print_help()
        print("\nError: provide at least one of --csv, --resume, --github-url")
        sys.exit(1)

    # ── Run pipeline ──────────────────────────────────────────────────────────
    try:
        candidate, output = run_pipeline(
            csv_path=args.csv,
            resume_path=args.resume,
            github_url=args.github_url,
            config_path=args.config,
        )
    except ValueError as e:
        print(f"\nError: {e}")
        sys.exit(1)

    # ── Write projected output ─────────────────────────────────────────────────
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nProjected output written to: {args.output}")

    # ── Optionally write full canonical record ────────────────────────────────
    if args.full:
        full_path = "output/candidate_full.json"
        with open(full_path, "w", encoding="utf-8") as f:
            json.dump(candidate.model_dump(), f, indent=2, ensure_ascii=False)
        print(f"Full canonical record written to: {full_path}")

    # ── Print summary ─────────────────────────────────────────────────────────
    _print_summary(candidate, output)


if __name__ == "__main__":
    main()