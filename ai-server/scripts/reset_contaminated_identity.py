#!/usr/bin/env python3
"""
FishDex — Reset Contaminated Identity Data
============================================

Safely removes or quarantines contaminated fish identity data from the canonical
databases used by the active identification pipeline.

Supports:
  --fish-id         Remove/quarantine a specific fish and its embeddings
  --area            Remove all fish in an area
  --species         Remove all fish of a species
  --full-dev-reset  Wipe all identity data (both SQLite DBs + artifacts)
  --dry-run         Show what would be deleted without modifying anything (DEFAULT)
  --backup          Create backup before any modifications

Usage:
  cd ai-server
  python scripts/reset_contaminated_identity.py --fish-id FISH-001 --dry-run
  python scripts/reset_contaminated_identity.py --full-dev-reset --backup
"""

import argparse
import json
import logging
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def get_main_db_path() -> Path:
    return Path(settings.server_data_dir) / "fishdex_local.sqlite"


def get_embeddings_db_path() -> Path:
    return Path(settings.embeddings_db_path)


def backup_file(path: Path, backup_dir: Path) -> None:
    """Create timestamped backup of a file."""
    if not path.exists():
        return
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"{path.name}.{timestamp}.bak"
    shutil.copy2(path, dest)
    logger.info(f"Backed up {path} -> {dest}")
    # Also backup WAL/SHM if they exist
    for suffix in ("-wal", "-shm"):
        wal = Path(str(path) + suffix)
        if wal.exists():
            shutil.copy2(wal, backup_dir / f"{wal.name}.{timestamp}.bak")


def reset_fish_id(fish_id: str, dry_run: bool, main_db: Path, emb_db: Path) -> dict:
    """Remove all data for a specific fish_id."""
    stats = {"embeddings_deleted": 0, "sightings_deleted": 0, "individuals_deleted": 0, "jobs_updated": 0}

    # Embeddings DB
    if emb_db.exists():
        conn = sqlite3.connect(str(emb_db))
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM fish_embeddings WHERE fish_id = ?", (fish_id,))
        count = cursor.fetchone()[0]
        stats["embeddings_deleted"] = count
        if not dry_run and count > 0:
            cursor.execute("DELETE FROM fish_embeddings WHERE fish_id = ?", (fish_id,))
            conn.commit()
        conn.close()

    # Main DB
    if main_db.exists():
        conn = sqlite3.connect(str(main_db))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Sightings
        cursor.execute("SELECT COUNT(*) FROM fish_sightings WHERE fish_id = ?", (fish_id,))
        stats["sightings_deleted"] = cursor.fetchone()[0]

        # Individuals
        cursor.execute("SELECT COUNT(*) FROM fish_individuals WHERE fish_id = ?", (fish_id,))
        stats["individuals_deleted"] = cursor.fetchone()[0]

        # Jobs referencing this fish
        cursor.execute(
            "SELECT COUNT(*) FROM identification_jobs WHERE result_fish_id = ?",
            (fish_id,),
        )
        stats["jobs_updated"] = cursor.fetchone()[0]

        if not dry_run:
            cursor.execute("DELETE FROM fish_sightings WHERE fish_id = ?", (fish_id,))
            cursor.execute("DELETE FROM fish_individuals WHERE fish_id = ?", (fish_id,))
            cursor.execute(
                "UPDATE identification_jobs SET result_fish_id = NULL, status = 'reset' "
                "WHERE result_fish_id = ?",
                (fish_id,),
            )
            conn.commit()
        conn.close()

    return stats


def reset_by_filter(area: str = None, species: str = None, dry_run: bool = True,
                    main_db: Path = None, emb_db: Path = None) -> dict:
    """Remove data filtered by area and/or species."""
    stats = {"fish_ids_affected": [], "embeddings_deleted": 0, "sightings_deleted": 0}

    # Find fish_ids matching filter
    if main_db.exists():
        conn = sqlite3.connect(str(main_db))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        conditions = []
        params = []
        if area:
            conditions.append("area_code = ?")
            params.append(area)
        if species:
            conditions.append("species_slug = ?")
            params.append(species)

        where = " AND ".join(conditions) if conditions else "1=1"
        cursor.execute(f"SELECT DISTINCT fish_id FROM fish_sightings WHERE {where}", params)
        fish_ids = [row[0] for row in cursor.fetchall() if row[0]]
        conn.close()

        stats["fish_ids_affected"] = fish_ids
        for fid in fish_ids:
            sub_stats = reset_fish_id(fid, dry_run, main_db, emb_db)
            stats["embeddings_deleted"] += sub_stats["embeddings_deleted"]
            stats["sightings_deleted"] += sub_stats["sightings_deleted"]

    return stats


def full_dev_reset(dry_run: bool, main_db: Path, emb_db: Path) -> dict:
    """Complete development reset — wipe both databases and artifacts."""
    stats = {
        "main_db_deleted": False,
        "embeddings_db_deleted": False,
        "artifacts_deleted": [],
    }

    paths_to_delete = [
        main_db,
        Path(str(main_db) + "-wal"),
        Path(str(main_db) + "-shm"),
        emb_db,
        Path(str(emb_db) + "-wal"),
        Path(str(emb_db) + "-shm"),
    ]

    artifact_dirs = [
        Path(settings.server_data_dir) / "storage" / "fish_media",
        Path(settings.server_data_dir) / "private" / "fish_documents",
        Path(settings.server_data_dir) / "storage" / "jobs",
    ]

    # Also legacy storage
    data_dir = Path(settings.server_data_dir)
    for d in data_dir.iterdir():
        if d.is_dir() and d.name not in ("storage", "private", "embeddings"):
            # Could be legacy data/{area}/{species}
            artifact_dirs.append(d)

    for p in paths_to_delete:
        if p.exists():
            logger.info(f"{'[DRY RUN] Would delete' if dry_run else 'Deleting'}: {p}")
            if not dry_run:
                p.unlink()
            if "main" in str(p.name):
                stats["main_db_deleted"] = True
            elif "embed" in str(p.name):
                stats["embeddings_db_deleted"] = True

    for d in artifact_dirs:
        if d.exists():
            logger.info(f"{'[DRY RUN] Would remove' if dry_run else 'Removing'}: {d}")
            stats["artifacts_deleted"].append(str(d))
            if not dry_run:
                shutil.rmtree(d, ignore_errors=True)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Reset contaminated fish identity data from canonical databases"
    )
    parser.add_argument("--fish-id", type=str, help="Specific fish_id to remove")
    parser.add_argument("--area", type=str, help="Area code to filter")
    parser.add_argument("--species", type=str, help="Species slug to filter")
    parser.add_argument(
        "--full-dev-reset",
        action="store_true",
        help="Wipe ALL identity data (dev/testing only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show what would be deleted without modifying (DEFAULT)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform the reset (disables dry-run)",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Create backup before modifications",
    )
    parser.add_argument(
        "--backup-dir",
        type=str,
        default=None,
        help="Directory for backups (default: data/backups/)",
    )

    args = parser.parse_args()

    dry_run = not args.execute
    main_db = get_main_db_path()
    emb_db = get_embeddings_db_path()

    if dry_run:
        logger.info("=== DRY RUN MODE (use --execute to apply changes) ===")

    # Backup
    if args.backup and not dry_run:
        backup_dir = Path(args.backup_dir) if args.backup_dir else Path(settings.server_data_dir) / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        backup_file(main_db, backup_dir)
        backup_file(emb_db, backup_dir)

    # Execute requested operation
    if args.full_dev_reset:
        if not dry_run:
            confirm = input("FULL DEV RESET will delete ALL identity data. Type 'yes' to confirm: ")
            if confirm.strip().lower() != "yes":
                logger.info("Aborted.")
                sys.exit(0)
        stats = full_dev_reset(dry_run, main_db, emb_db)
    elif args.fish_id:
        stats = reset_fish_id(args.fish_id, dry_run, main_db, emb_db)
    elif args.area or args.species:
        stats = reset_by_filter(args.area, args.species, dry_run, main_db, emb_db)
    else:
        parser.print_help()
        sys.exit(1)

    # Report
    logger.info("=" * 60)
    logger.info("RESULT%s:", " (DRY RUN)" if dry_run else "")
    for k, v in stats.items():
        logger.info(f"  {k}: {v}")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
