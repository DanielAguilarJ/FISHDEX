"""
Rebuild embeddings from sighting crops.

Scans fish_sightings for definitive sightings with crops on disk,
generates embeddings using the active ReID model + fingerprint config,
and stores them in fish_embeddings with proper model_version tagging.

Safety guarantees (fail-closed):
  - Refuses to run if fingerprint config doesn't match model_version label
  - Validates spec (checkpoint SHA, dimensions, TTA, coords) before any insert
  - Uses INSERT OR IGNORE with UNIQUE(sighting_id, model_version, vector_type)
  - Validates every vector: float32, 512-d, finite, L2-normalized
  - Requires migration >= 5 (UNIQUE index) before executing

Usage:
    python -m app.commands.rebuild_embeddings --dry-run [--species SLUG]
    python -m app.commands.rebuild_embeddings --execute [--species SLUG] [--backup]
"""
import argparse
import logging
import shutil
import sqlite3
import sys
from typing import NoReturn
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from app.config import settings
from app.database import DB_PATH, get_db_connection

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────────


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
    """
    Find OBB crop files in {artifact_dir}/images/crop_*.jpg.

    Searches ONLY the images/ subdirectory for primary OBB crops.
    Does NOT include: preview.jpg, images_bbox/, dataset/, frames/,
    annotated/, raw/, or any fingerprint crops.

    Each file is validated with cv2.imread before inclusion.
    """
    if not artifact_dir:
        return []

    # artifact_dir can be relative to server_data_dir/storage or absolute
    base = Path(settings.server_data_dir) / "storage"
    art_path = base / artifact_dir if not Path(artifact_dir).is_absolute() else Path(artifact_dir)

    images_dir = art_path / "images"
    if not images_dir.is_dir():
        return []

    # Only glob crop_*.jpg/.jpeg/.png in images/ — nothing else
    candidates: list[Path] = []
    for ext in ("*.jpg", "*.jpeg", "*.png"):
        candidates.extend(images_dir.glob(f"crop_{ext}"))

    # Sort for deterministic order
    candidates = sorted(candidates)

    # Validate each file is readable by OpenCV
    valid: list[Path] = []
    for p in candidates:
        if not p.is_file():
            continue
        img = cv2.imread(str(p))
        if img is not None and img.size > 0:
            valid.append(p)
        else:
            logger.warning("Crop file unreadable by OpenCV, skipping: %s", p)

    return valid


def _check_migration_version() -> int:
    """Check current migration version of embeddings DB schema."""
    try:
        conn = get_db_connection()
        try:
            row = conn.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()
            return row[0] if row and row[0] else 0
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 — version probe must never abort a rebuild
        logger.warning("Could not read schema_migrations version: %s", exc)
        return 0


# ── Main rebuild logic ───────────────────────────────────────────────────────


def run_rebuild(
    dry_run: bool = True,
    execute: bool = False,
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
        "execute": execute,
        "species_filter": species_filter,
        "backup_created": None,
    }

    # ── Validate mode ────────────────────────────────────────────────────
    if not dry_run and not execute:
        logger.error(
            "Must specify either --dry-run or --execute. "
            "Use --dry-run to see what would be processed."
        )
        report["status"] = "error_no_mode"
        return report

    # ── If executing, perform strict validation ──────────────────────────
    spec = None
    if execute:
        # 1. Check migration version
        migration_ver = _check_migration_version()
        if migration_ver < 5:
            raise RuntimeError(
                f"Migration version is {migration_ver}, need >= 5. "
                "Run the server once to apply migration 005 "
                "(embeddings UNIQUE index) before rebuilding."
            )

        # 2. Build and validate preprocessing spec
        from app.services.reid_preprocessing_spec import ReIDPreprocessingSpec

        spec = ReIDPreprocessingSpec.from_active_config()
        logger.info("Active preprocessing spec:")
        logger.info("  model_version:      %s", spec.model_version)
        logger.info("  checkpoint_sha256:  %s", spec.checkpoint_sha256)
        logger.info("  fingerprint:        %s", spec.fingerprint_enabled)
        if spec.fingerprint_enabled:
            logger.info(
                "  bounds:             x=[%.3f, %.3f] y=[%.3f, %.3f]",
                spec.x_start, spec.x_end, spec.y_start, spec.y_end,
            )
        logger.info("  embedding_dim:      %d", spec.embedding_dim)
        logger.info("  img_size:           %d", spec.img_size)
        logger.info("  flip_tta:           %s", spec.flip_tta)

        # Full validation: consistency + ReID service loaded
        spec.validate_fingerprint_consistency()
        spec.validate_reid_service_loaded()

        logger.info("Spec validation PASSED")

    # ── Backup if requested ──────────────────────────────────────────────
    if backup and execute:
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
            SELECT id, fish_id, species_slug, artifact_dir,
                   location_lat, location_lng, area_code, catch_number, is_new_fish
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
        area_code = row[6] if len(row) > 6 else None
        catch_number = row[7] if len(row) > 7 else None
        is_new_fish = row[8] if len(row) > 8 else None

        crops = _find_crop_files(artifact_dir)
        entry = {
            "sighting_id": sighting_id,
            "fish_id": fish_id,
            "species_slug": species_slug,
            "artifact_dir": artifact_dir,
            "latitude": lat,
            "longitude": lng,
            "area_code": area_code,
            "catch_number": catch_number,
            "is_new_fish": is_new_fish,
            "crop_count": len(crops),
            "crop_paths": [str(p) for p in crops],
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

    # ── Dry run ──────────────────────────────────────────────────────────
    if dry_run:
        logger.info("DRY RUN: No modifications made.")
        logger.info(
            "Would process %d sightings across %d unique fish.",
            len(processable),
            len({p["fish_id"] for p in processable}),
        )
        report["status"] = "dry_run_complete"
        return report

    # ── Execute: generate and store embeddings ───────────────────────────
    assert spec is not None, "Spec must be set for --execute"

    from app.services.reid_embedding_service import get_reid_embedding_service
    from app.services.matching_service import get_matching_service

    reid = get_reid_embedding_service()
    matching = get_matching_service()

    model_version = spec.model_version
    logger.info("Target model_version: %s", model_version)

    inserted = 0
    skipped_existing = 0
    errors = 0
    start_time = time.time()
    total = len(processable)

    for idx, entry in enumerate(processable, 1):
        sighting_id = entry["sighting_id"]
        fish_id = entry["fish_id"]
        species_slug = entry["species_slug"]
        area_code = entry["area_code"]
        lat = entry["latitude"]
        lng = entry["longitude"]
        crop_paths = entry["crop_paths"]

        # Progress
        if idx % 50 == 0 or idx == 1 or idx == total:
            elapsed = time.time() - start_time
            rate = idx / elapsed if elapsed > 0 else 0
            eta = (total - idx) / rate if rate > 0 else 0
            logger.info(
                "[%d/%d] %s (%s) — %.1f sightings/s, ETA: %.0fs",
                idx, total, sighting_id, fish_id, rate, eta,
            )

        # Pre-check: skip if already exists
        if matching.embedding_exists(sighting_id, model_version, "prototype"):
            skipped_existing += 1
            continue

        try:
            # Extract embeddings from crop files
            # ReIDEmbeddingService's transform already includes the
            # fingerprint crop if enabled in settings. The spec validation
            # above ensures config matches the target model_version.
            matrix = reid.extract_embedding_matrix_from_paths(crop_paths)

            if matrix.shape[0] == 0:
                logger.warning(
                    "No valid crops for sighting %s (all unreadable?)",
                    sighting_id,
                )
                errors += 1
                continue

            # Compute L2-normalized prototype (mean embedding)
            mean_emb = matrix.mean(axis=0)
            norm = np.linalg.norm(mean_emb)
            if norm > 0:
                mean_emb = mean_emb / norm
            prototype = mean_emb.astype(np.float32)

            # Validate prototype before storage
            if prototype.shape[0] != spec.embedding_dim:
                logger.error(
                    "Dimension mismatch for %s: got %d, expected %d",
                    sighting_id, prototype.shape[0], spec.embedding_dim,
                )
                errors += 1
                continue

            if not np.all(np.isfinite(prototype)):
                logger.error(
                    "Non-finite values in prototype for %s", sighting_id,
                )
                errors += 1
                continue

            proto_norm = float(np.linalg.norm(prototype))
            if not (0.95 < proto_norm < 1.05):
                logger.error(
                    "Prototype not L2-normalized for %s: norm=%.4f",
                    sighting_id, proto_norm,
                )
                errors += 1
                continue

            # Store embedding (INSERT OR IGNORE for idempotency)
            is_anchor = (entry.get("is_new_fish") == 1 or entry.get("catch_number") == 1)
            v_status = "anchor_new" if is_anchor else "legacy_untrusted"
            matching.store_embedding(
                fish_id=fish_id,
                sighting_id=sighting_id,
                species_slug=species_slug,
                area_code=area_code,
                embedding=prototype,
                latitude=lat,
                longitude=lng,
                model_version=model_version,
                vector_type="prototype",
                dimensions=spec.embedding_dim,
                verification_status=v_status,
            )
            inserted += 1

        except Exception as exc:
            logger.error(
                "Error processing sighting %s: %s",
                sighting_id, exc, exc_info=True,
            )
            errors += 1

    elapsed = time.time() - start_time

    # ── Summary ──────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("REBUILD SUMMARY")
    logger.info("=" * 60)
    logger.info("Processed:         %d", total)
    logger.info("Inserted:          %d", inserted)
    logger.info("Skipped (exists):  %d", skipped_existing)
    logger.info("Errors:            %d", errors)
    logger.info("Model version:     %s", model_version)
    logger.info("Fingerprint:       %s", "ENABLED" if spec.fingerprint_enabled else "DISABLED")
    if spec.fingerprint_enabled:
        logger.info(
            "  Bounds:            x=[%.3f, %.3f] y=[%.3f, %.3f]",
            spec.x_start, spec.x_end, spec.y_start, spec.y_end,
        )
    logger.info("Duration:          %.1fs", elapsed)
    logger.info("=" * 60)

    report.update({
        "status": "execute_complete",
        "model_version": model_version,
        "inserted": inserted,
        "skipped_existing": skipped_existing,
        "errors": errors,
        "duration_seconds": round(elapsed, 1),
    })
    return report


def main() -> NoReturn:
    """
    Parse arguments, rebuild the embedding gallery and exit.

    Terminates the process with ``sys.exit`` rather than returning, so the
    exit status is the command's only output channel.
    """
    parser = argparse.ArgumentParser(
        description="Rebuild embeddings from sighting crop files.",
        epilog=(
            "Safety: --execute validates that the active fingerprint config, "
            "checkpoint SHA, dimensions, and TTA match the target model_version. "
            "Mismatches abort before any insert."
        ),
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report what would be processed; do not modify anything.",
    )
    mode_group.add_argument(
        "--execute",
        action="store_true",
        help="Actually generate and store embeddings. Requires valid spec.",
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
        report = run_rebuild(
            dry_run=args.dry_run,
            execute=args.execute,
            species_filter=args.species,
            backup=args.backup,
        )
        if report.get("errors", 0) > 0:
            logger.warning(
                "Completed with %d errors — check logs above.",
                report["errors"],
            )
            sys.exit(1)
    except RuntimeError as e:
        logger.error("ABORT: %s", e)
        sys.exit(2)
    except FileNotFoundError as e:
        logger.error(str(e))
        sys.exit(2)
    except Exception as e:
        logger.exception("Rebuild failed: %s", e)
        sys.exit(2)


if __name__ == "__main__":
    main()
