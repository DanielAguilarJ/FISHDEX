"""
Rebuild embeddings from sighting crops.

Phase 2: validates data layer and reports readiness.
Phase 3: will perform actual embedding generation.

Usage:
    python -m app.commands.rebuild_embeddings [--dry-run] [--species SLUG] [--backup]
"""
import argparse
import logging
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from app.config import settings
from app.database import DB_PATH, get_db_connection

logger = logging.getLogger(__name__)


def _get_embeddings_connection() -> sqlite3.Connection:
    """Open connection to the embeddings database."""
    emb_path = Path(settings.embeddings_db_path)
    if not emb_path.exists():
        logger.error("Embeddings DB not found at %s", emb_path)
        raise FileNotFoundError(f"Embeddings DB not found: {emb_path}")
    conn = sqlite3.connect(str(emb_path))
    conn.row_factory = sqlite3.Row
    return conn


def _backup_embeddings_db() -> Path:
    """Copy embeddings DB to a timestamped backup file."""
    emb_path = Path(settings.embeddings_db_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = emb_path.with_suffix(f".backup_{timestamp}.sqlite")
    shutil.copy2(str(emb_path), str(backup_path))
    logger.info("Backup created: %s", backup_path)
    return backup_path


def _find_crop_files(artifact_dir: str | None) -> list[Path]:
    """Find OBB crop files in the given artifact directory."""
    if not artifact_dir:
        return []

    # artifact_dir can be relative to server_data_dir/storage or absolute
    base = Path(settings.server_data_dir) / "storage"
    art_path = base / artifact_dir if not Path(artifact_dir).is_absolute() else Path(artifact_dir)

    if not art_path.exists():
        return []

    # Look for crop files (OBB crops are typically named *_crop_*.jpg or *_obb_*.jpg)
    crops = []
    for pattern in ("*crop*.jpg", "*crop*.png", "*obb*.jpg", "*obb*.png"):
        crops.extend(art_path.glob(pattern))

    return sorted(crops)


def run_rebuild(
    dry_run: bool = True,
    species_filter: str | None = None,
    backup: bool = False,
) -> dict:
    """Run rebuild analysis/execution and return summary dict."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s | %(message)s",
    )

    report: dict = {
        "dry_run": dry_run,
        "species_filter": species_filter,
        "backup_created": None,
    }

    # ── Backup if requested ──────────────────────────────────────────────
    if backup and not dry_run:
        try:
            backup_path = _backup_embeddings_db()
            report["backup_created"] = str(backup_path)
        except FileNotFoundError:
            logger.warning("No embeddings DB to backup (will be created on first run).")

    # ── Load sightings with fish_id ──────────────────────────────────────
    logger.info("Connecting to main DB: %s", DB_PATH)
    main_conn = get_db_connection()
    try:
        cur = main_conn.cursor()

        query = """
            SELECT id, fish_id, species_slug, artifact_dir, location_lat, location_lng
            FROM fish_sightings
            WHERE fish_id IS NOT NULL AND fish_id != ''
        """
        params: list = []
        if species_filter:
            query += " AND species_slug = ?"
            params.append(species_filter)

        query += " ORDER BY created_at ASC"
        cur.execute(query, params)
        sightings = cur.fetchall()
    finally:
        main_conn.close()

    logger.info("Found %d definitive sightings with fish_id", len(sightings))
    if species_filter:
        logger.info("  (filtered to species: %s)", species_filter)

    # ── Check crop availability ──────────────────────────────────────────
    processable = []
    missing_crops = []

    for row in sightings:
        sighting_id = row[0]
        fish_id = row[1]
        species_slug = row[2]
        artifact_dir = row[3]
        lat = row[4]
        lng = row[5]

        crops = _find_crop_files(artifact_dir)
        entry = {
            "sighting_id": sighting_id,
            "fish_id": fish_id,
            "species_slug": species_slug,
            "artifact_dir": artifact_dir,
            "latitude": lat,
            "longitude": lng,
            "crop_count": len(crops),
        }

        if crops:
            processable.append(entry)
        else:
            missing_crops.append(entry)

    report["total_sightings_checked"] = len(sightings)
    report["processable_count"] = len(processable)
    report["missing_crops_count"] = len(missing_crops)

    # ── Report ───────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("REBUILD EMBEDDINGS REPORT")
    logger.info("=" * 60)
    logger.info("Total sightings with fish_id:  %d", len(sightings))
    logger.info("Sightings with crops on disk:  %d", len(processable))
    logger.info("Sightings missing crops:       %d", len(missing_crops))
    logger.info("-" * 60)

    if processable:
        species_counts: dict[str, int] = {}
        for p in processable:
            slug = p["species_slug"] or "(unknown)"
            species_counts[slug] = species_counts.get(slug, 0) + 1
        logger.info("Processable by species:")
        for slug, cnt in sorted(species_counts.items(), key=lambda x: -x[1]):
            logger.info("  %-35s %d", slug, cnt)

    if missing_crops and len(missing_crops) <= 20:
        logger.info("Missing crops (sighting_ids):")
        for m in missing_crops:
            logger.info("  %s (artifact_dir=%s)", m["sighting_id"], m["artifact_dir"])

    logger.info("=" * 60)

    # ── Dry run vs execution ─────────────────────────────────────────────
    if dry_run:
        logger.info("DRY RUN: No modifications made.")
        logger.info(
            "Would process %d sightings across %d unique fish.",
            len(processable),
            len({p["fish_id"] for p in processable}),
        )
    else:
        logger.warning(
            "rebuild_embeddings requires model loading - not implemented in Phase 2"
        )
        logger.info(
            "Data layer validated. %d sightings ready for embedding generation.",
            len(processable),
        )
        logger.info(
            "Actual embedding generation will be added when the pipeline is "
            "unified (Phase 3)."
        )

    report["status"] = "dry_run_complete" if dry_run else "ready_for_phase3"
    return report


def main():
    parser = argparse.ArgumentParser(
        description="Rebuild embeddings from sighting crop files."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report what would be processed; do not modify anything.",
    )
    parser.add_argument(
        "--species",
        type=str,
        default=None,
        help="Filter to a specific species_slug.",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Backup current embeddings DB before modifying.",
    )
    args = parser.parse_args()

    try:
        run_rebuild(
            dry_run=args.dry_run,
            species_filter=args.species,
            backup=args.backup,
        )
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(2)
    except Exception as e:
        logger.exception("Rebuild failed: %s", e)
        sys.exit(2)


if __name__ == "__main__":
    main()
