"""
Reset FISHDEX AI Server production environment safely:
1. Requires explicit CLI flag --confirm RESET.
2. Creates timestamped full backup directory data_backup_YYYYMMDD_HHMMSS.
3. Clears operational tables (identification_jobs, fish_sightings, fish_individuals, processing_stats, reid_identities).
4. Preserves users and schema_migrations tables.
5. Clears fish_embeddings from fishdex_embeddings.sqlite.
6. Cleans storage/, private/, and artifacts/ directories.
7. Executes VACUUM on both SQLite databases.
8. Asserts 0 records remain in all operational tables and embedding indices.
"""

import argparse
import datetime
import logging
import shutil
import sqlite3
import sys
from pathlib import Path

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("reset_prod")


def reset_environment(confirm_flag: str):
    if confirm_flag != "RESET":
        logger.error("Safety check failed: You must specify --confirm RESET to perform production reset.")
        sys.exit(1)

    server_data = Path(settings.server_data_dir)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = server_data.parent / f"data_backup_{timestamp}"

    if server_data.exists():
        logger.info(f"Creating timestamped production backup at: {backup_dir}")
        shutil.copytree(server_data, backup_dir)

    # 1. Main database cleaning
    main_db_path = server_data / "fishdex_local.sqlite"
    if main_db_path.exists():
        conn = sqlite3.connect(main_db_path)
        cur = conn.cursor()
        
        tables_to_clear = [
            "identification_jobs",
            "fish_sightings",
            "fish_individuals",
            "processing_stats",
            "reid_identities",
        ]
        
        existing_tables = [
            row[0]
            for row in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        
        for table in tables_to_clear:
            if table in existing_tables:
                cur.execute(f"DELETE FROM {table}")
                logger.info(f"Cleared table: {table}")

        conn.commit()
        cur.execute("VACUUM")

        # Assert 0 records in operational tables
        for table in tables_to_clear:
            if table in existing_tables:
                count = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                assert count == 0, f"Table {table} count is {count}, expected 0!"
                logger.info(f"Verified {table} count == 0")

        conn.close()

    # 2. Embeddings database cleaning
    emb_db_path = server_data / "embeddings" / "fishdex_embeddings.sqlite"
    if emb_db_path.exists():
        conn = sqlite3.connect(emb_db_path)
        cur = conn.cursor()
        cur.execute("DELETE FROM fish_embeddings")
        conn.commit()
        cur.execute("VACUUM")
        
        emb_count = cur.execute("SELECT COUNT(*) FROM fish_embeddings").fetchone()[0]
        assert emb_count == 0, f"fish_embeddings count is {emb_count}, expected 0!"
        logger.info("Verified fish_embeddings count == 0")
        conn.close()

    # 3. Storage directories cleaning
    for dir_name in ["storage", "private", "artifacts"]:
        target_dir = server_data / dir_name
        if target_dir.exists():
            shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Cleaned and recreated directory: {dir_name}")

    logger.info("==========================================================")
    logger.info("Production reset complete and verified! 0 operational items remaining.")
    logger.info("==========================================================")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean reset FISHDEX production environment.")
    parser.add_argument("--confirm", required=True, help="Must be set to RESET")
    args = parser.parse_args()
    reset_environment(args.confirm)
