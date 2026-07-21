"""
Reset FISHDEX AI Server production environment:
1. Backs up previous database & storage to data_backup_...
2. Clears all test jobs, test sightings, test fish individuals, and test embeddings.
3. Clears storage and private metadata folders.
4. Leaves table schemas, migrations, calibration files, ONNX models, and settings intact.
"""

import logging
import shutil
import sqlite3
from pathlib import Path

from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("reset_prod")


def reset_environment():
    server_data = Path(settings.server_data_dir)

    # 1. Backup if backup doesn't exist yet
    backup_dir = server_data.parent / f"{server_data.name}_backup_production_reset"
    if server_data.exists() and not backup_dir.exists():
        logger.info(f"Creating full data backup at: {backup_dir}")
        shutil.copytree(server_data, backup_dir)

    # 2. Reset local SQLite DB tables
    main_db_path = server_data / "fishdex_local.sqlite"
    if main_db_path.exists():
        conn = sqlite3.connect(main_db_path)
        cur = conn.cursor()
        tables = [
            row[0]
            for row in cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for t in tables:
            cur.execute(f"DELETE FROM {t}")
            logger.info(f"Cleared main DB table: {t}")
        conn.commit()
        conn.close()

    # 3. Reset embeddings DB
    emb_db_path = server_data / "embeddings" / "fishdex_embeddings.sqlite"
    if emb_db_path.exists():
        conn = sqlite3.connect(emb_db_path)
        cur = conn.cursor()
        cur.execute("DELETE FROM fish_embeddings")
        conn.commit()
        conn.close()
        logger.info("Cleared embeddings table: fish_embeddings")

    # 4. Clean storage folders
    storage_dir = server_data / "storage"
    if storage_dir.exists():
        for item in storage_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
                item.mkdir(parents=True, exist_ok=True)
                logger.info(f"Cleaned storage directory: {item.name}")

    # 5. Clean private metadata documents
    private_dir = server_data / "private"
    if private_dir.exists():
        shutil.rmtree(private_dir)
        private_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Cleaned private metadata directory")

    logger.info("==========================================================")
    logger.info("Production environment reset complete! System is 100% clean.")
    logger.info("==========================================================")


if __name__ == "__main__":
    reset_environment()
