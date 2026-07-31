"""
Audit embeddings database integrity and report statistics.

Usage:
    python -m app.commands.audit_embeddings [--strict] [--json-output PATH]
"""
import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

import numpy as np

from app.config import settings
from app.database import DB_PATH, get_db_connection

logger = logging.getLogger(__name__)

EXPECTED_DIM = 512  # default embedding dimension


def _get_embeddings_connection() -> sqlite3.Connection:
    """Open connection to the embeddings database."""
    emb_path = Path(settings.embeddings_db_path)
    if not emb_path.exists():
        logger.error("Embeddings DB not found at %s", emb_path)
        raise FileNotFoundError(f"Embeddings DB not found: {emb_path}")
    conn = sqlite3.connect(str(emb_path))
    conn.row_factory = sqlite3.Row
    return conn


def run_audit(strict: bool = False, json_output: str | None = None) -> dict:
    """Run full embeddings audit and return report dict."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s",
    )

    report: dict = {}

    # ── Main DB stats ────────────────────────────────────────────────────
    logger.info("Connecting to main DB: %s", DB_PATH)
    main_conn = get_db_connection()
    try:
        cur = main_conn.cursor()

        cur.execute("SELECT COUNT(*) FROM fish_sightings")
        total_sightings = cur.fetchone()[0]
        report["total_sightings"] = total_sightings

        cur.execute("SELECT COUNT(*) FROM fish_individuals")
        total_individuals = cur.fetchone()[0]
        report["total_individuals"] = total_individuals

        # Gather all fish_ids from individuals for orphan check
        cur.execute("SELECT fish_id FROM fish_individuals")
        known_fish_ids = {row[0] for row in cur.fetchall()}

        # Sighting fish_ids for coverage check
        cur.execute(
            "SELECT DISTINCT fish_id FROM fish_sightings WHERE fish_id IS NOT NULL"
        )
        sighting_fish_ids = {row[0] for row in cur.fetchall()}
    finally:
        main_conn.close()

    # ── Embeddings DB stats ──────────────────────────────────────────────
    emb_path = Path(settings.embeddings_db_path)
    logger.info("Connecting to embeddings DB: %s", emb_path)
    emb_conn = _get_embeddings_connection()
    try:
        ecur = emb_conn.cursor()

        ecur.execute("SELECT COUNT(*) FROM fish_embeddings")
        total_embeddings = ecur.fetchone()[0]
        report["total_embeddings"] = total_embeddings

        # Model version breakdown
        ecur.execute(
            "SELECT model_version, COUNT(*) as cnt "
            "FROM fish_embeddings GROUP BY model_version ORDER BY cnt DESC"
        )
        model_versions = {row[0] or "(NULL)": row[1] for row in ecur.fetchall()}
        report["model_version_counts"] = model_versions

        # Orphan embeddings: fish_id not in fish_individuals
        ecur.execute("SELECT DISTINCT fish_id FROM fish_embeddings")
        emb_fish_ids = {row[0] for row in ecur.fetchall()}
        orphan_ids = emb_fish_ids - known_fish_ids
        report["orphan_embeddings_count"] = len(orphan_ids)
        if orphan_ids:
            report["orphan_fish_ids_sample"] = sorted(orphan_ids)[:10]

        # Sightings without embeddings
        ecur.execute("SELECT DISTINCT fish_id FROM fish_embeddings")
        embedded_fish_ids = {row[0] for row in ecur.fetchall()}
        missing_embeddings = sighting_fish_ids - embedded_fish_ids
        report["sightings_without_embeddings_count"] = len(missing_embeddings)
        if missing_embeddings:
            report["sightings_without_embeddings_sample"] = sorted(missing_embeddings)[:10]

        # NULL lat/lng
        ecur.execute(
            "SELECT COUNT(*) FROM fish_embeddings WHERE latitude IS NULL OR longitude IS NULL"
        )
        report["embeddings_null_location"] = ecur.fetchone()[0]

        # NULL species_slug
        ecur.execute(
            "SELECT COUNT(*) FROM fish_embeddings WHERE species_slug IS NULL OR species_slug = ''"
        )
        report["embeddings_null_species"] = ecur.fetchone()[0]

        # Distinct species
        ecur.execute(
            "SELECT COUNT(DISTINCT species_slug) FROM fish_embeddings "
            "WHERE species_slug IS NOT NULL AND species_slug != ''"
        )
        report["distinct_species_with_embeddings"] = ecur.fetchone()[0]

        # Dimension check (sample up to 100)
        dimension_mismatches = 0
        ecur.execute("SELECT embedding FROM fish_embeddings LIMIT 100")
        for row in ecur.fetchall():
            blob = row[0]
            if blob is not None:
                arr = np.frombuffer(blob, dtype=np.float32)
                if arr.shape[0] != EXPECTED_DIM:
                    dimension_mismatches += 1
        report["dimension_mismatches_in_sample"] = dimension_mismatches

    finally:
        emb_conn.close()

    # ── Current model info ───────────────────────────────────────────────
    report["current_model_version"] = settings.reid_cache_name

    # ── Print report ─────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("EMBEDDINGS AUDIT REPORT")
    logger.info("=" * 60)
    logger.info("Main DB: %s", DB_PATH)
    logger.info("Embeddings DB: %s", emb_path)
    logger.info("-" * 60)
    logger.info("Total definitive sightings:        %d", report["total_sightings"])
    logger.info("Total fish individuals:            %d", report["total_individuals"])
    logger.info("Total embeddings stored:           %d", report["total_embeddings"])
    logger.info("-" * 60)
    logger.info("Model version counts:")
    for mv, cnt in report["model_version_counts"].items():
        logger.info("  %-40s %d", mv, cnt)
    logger.info("-" * 60)
    logger.info("Orphan embeddings (fish_id missing): %d", report["orphan_embeddings_count"])
    logger.info("Sightings without embeddings:        %d", report["sightings_without_embeddings_count"])
    logger.info("Embeddings with NULL location:       %d", report["embeddings_null_location"])
    logger.info("Embeddings with NULL species_slug:   %d", report["embeddings_null_species"])
    logger.info("Distinct species with embeddings:    %d", report["distinct_species_with_embeddings"])
    logger.info("Dimension mismatches (sample 100):   %d", report["dimension_mismatches_in_sample"])
    logger.info("-" * 60)
    logger.info("Current model_version (settings):    %s", report["current_model_version"])
    logger.info("=" * 60)

    # ── JSON output ──────────────────────────────────────────────────────
    if json_output:
        out_path = Path(json_output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, indent=2, default=str))
        logger.info("Report written to %s", out_path)

    # ── Strict mode ──────────────────────────────────────────────────────
    if strict:
        failures = []
        if report["orphan_embeddings_count"] > 0:
            failures.append(f"orphan embeddings: {report['orphan_embeddings_count']}")
        if report["dimension_mismatches_in_sample"] > 0:
            failures.append(f"dimension mismatches: {report['dimension_mismatches_in_sample']}")
        if failures:
            logger.error("STRICT CHECK FAILED: %s", "; ".join(failures))
            return report  # caller checks exit code
    return report


def main():
    """
    Parse arguments and run the embedding audit.

    Returns:
        Process exit status.
    """
    parser = argparse.ArgumentParser(
        description="Audit embeddings database integrity."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if orphans > 0 or dimension mismatches found.",
    )
    parser.add_argument(
        "--json-output",
        type=str,
        default=None,
        help="Write audit report as JSON to this file path.",
    )
    args = parser.parse_args()

    try:
        report = run_audit(strict=args.strict, json_output=args.json_output)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(2)
    except Exception as e:
        logger.exception("Audit failed: %s", e)
        sys.exit(2)

    if args.strict:
        if report.get("orphan_embeddings_count", 0) > 0:
            sys.exit(1)
        if report.get("dimension_mismatches_in_sample", 0) > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
