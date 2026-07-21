import argparse
import json
import logging
import os
import random
import sqlite3
import sys
from pathlib import Path

import numpy as np
from app.config import settings
from app.database import get_db_connection
from app.services.matching_service import get_matching_service
from app.services.reid_embedding_service import get_reid_embedding_service

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def verify_checkpoint(model_version: str) -> bool:
    checkpoint_path = Path(settings.reid_model_path)
    if not checkpoint_path.exists():
        logger.warning(f"Checkpoint not found at {checkpoint_path}")
        return False
    return True

def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-version", required=True)
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--rollback", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.rollback:
        rollback_file = Path(".env.rollback")
        if rollback_file.exists():
            logger.info("Restoring from .env.rollback...")
            with open(rollback_file, "r") as f:
                print(f.read())
            logger.info("Rollback instructions printed.")
        else:
            logger.error("No .env.rollback found.")
        sys.exit(0)

    checks_passed = True
    x_start, x_end, y_start, y_end = 0.0, 1.0, 0.0, 1.0

    # 1. Spec check
    if not verify_checkpoint(args.model_version):
        if not args.force:
            checks_passed = False
            logger.error("Spec check failed.")
    else:
        logger.info("Spec check passed.")

    # 2. Calibration check — uses the same validation as production
    from app.calibration import load_calibration, is_calibration_valid, reset_calibration_cache
    reset_calibration_cache()  # Force fresh load
    
    calib_path = Path(f"calibration/{args.model_version}.json")
    if not calib_path.exists():
        logger.error(f"Calibration file {calib_path} not found.")
        checks_passed = False
    else:
        cal = load_calibration(args.model_version)
        if cal is None:
            logger.error("Calibration file could not be loaded.")
            checks_passed = False
        else:
            valid, reason = is_calibration_valid(cal)
            if not valid:
                logger.error(
                    "Calibration INVALID for auto_match: %s. "
                    "test_far=%s, validation_far=%s, validated=%s",
                    reason, cal.test_far, cal.validation_far, cal.validated,
                )
                # --force cannot bypass scientific validation for auto_match
                checks_passed = False
            else:
                logger.info(
                    "Calibration check passed (test_far=%.6f, validation_far=%.6f).",
                    float(cal.test_far), float(cal.validation_far),
                )

    # 3. Dorsal audit check
    audit_path = Path("audit/dorsal_audit.json")
    if not audit_path.exists():
        logger.error(f"Dorsal audit file {audit_path} not found.")
        logger.info("Instructions: Run generate_contact_sheet.py and complete the audit first.")
        checks_passed = False
    else:
        with open(audit_path, "r") as f:
            audit_data = json.load(f)
            if not audit_data.get("dorsal_audit_passed"):
                logger.error("Dorsal audit not passed.")
                logger.info("Instructions: Run generate_contact_sheet.py and complete the audit first.")
                checks_passed = False
            else:
                logger.info("Dorsal audit check passed.")
                bounds = audit_data.get("fingerprint_bounds", {})
                x_start = bounds.get("x_start", 0.0)
                x_end = bounds.get("x_end", 1.0)
                y_start = bounds.get("y_start", 0.0)
                y_end = bounds.get("y_end", 1.0)

    db_conn = get_db_connection()
    db_conn.row_factory = sqlite3.Row
    matching_service = get_matching_service()
    emb_conn = matching_service._connect()

    # 4. Coverage check
    cursor = db_conn.cursor()
    cursor.execute("SELECT id, fish_id, artifact_dir FROM fish_sightings WHERE fish_id IS NOT NULL AND artifact_dir IS NOT NULL")
    eligible_sightings = cursor.fetchall()
    total_eligible = len(eligible_sightings)

    emb_cursor = emb_conn.cursor()
    emb_cursor.execute(
        "SELECT sighting_id, embedding, vector_type FROM fish_embeddings "
        "WHERE model_version = ?",
        (args.model_version,),
    )
    embeddings = emb_cursor.fetchall()
    emb_sighting_ids = set([e[0] for e in embeddings])

    covered = [s for s in eligible_sightings if s["id"] in emb_sighting_ids]
    total_covered = len(covered)
    covered_fishes = len(set([s["fish_id"] for s in covered]))

    logger.info(f"Coverage: {total_covered}/{total_eligible} sightings covered.")
    logger.info(f"Coverage by fish: {covered_fishes} fishes covered.")

    if total_eligible > 0 and total_covered / total_eligible < 0.95:
        logger.warning("Coverage is below 95%.")
        if not args.force:
            checks_passed = False
            logger.error("Blocked due to low coverage. Use --force to override.")

    # 5. Dimensions/norms
    sample_size = min(100, len(embeddings))
    if sample_size > 0:
        samples = random.sample(embeddings, sample_size)
        for row in samples:
            vec = np.frombuffer(row[1], dtype=np.float32)
            if vec.shape != (512,):
                logger.error(f"Invalid embedding shape: {vec.shape}")
                checks_passed = False
                break
            if not np.isfinite(vec).all():
                logger.error("Invalid embedding values (NaN/Inf).")
                checks_passed = False
                break
            norm = np.linalg.norm(vec)
            if not (0.95 <= norm <= 1.05):
                logger.error(f"Invalid embedding norm: {norm}")
                checks_passed = False
                break
        logger.info("Dimensions/norms check passed.")
    else:
        logger.warning("No embeddings to check dimensions/norms.")

    # 6. Duplicates
    emb_cursor.execute(
        "SELECT sighting_id, COUNT(*) FROM fish_embeddings "
        "WHERE model_version = ? "
        "GROUP BY sighting_id, vector_type HAVING COUNT(*) > 1",
        (args.model_version,),
    )
    duplicates = emb_cursor.fetchall()
    if duplicates:
        logger.error(f"Found {len(duplicates)} duplicates in embeddings DB.")
        checks_passed = False
    else:
        logger.info("Duplicates check passed.")

    # Smoke test
    reid_service = get_reid_embedding_service()
    smoke_samples = random.sample(covered, min(5, len(covered))) if covered else []
    smoke_passed = True
    storage_base = Path(settings.server_data_dir) / 'storage'
    
    for sighting in smoke_samples:
        sighting_id = sighting["id"]
        artifact_dir = sighting["artifact_dir"]
        crop_path = storage_base / artifact_dir / "images" / "crop_00.jpg"
        if not crop_path.exists():
            continue
        try:
            import cv2
            emb_cursor.execute(
                "SELECT embedding FROM fish_embeddings "
                "WHERE sighting_id = ? AND model_version = ? LIMIT 1",
                (sighting_id, args.model_version),
            )
            row = emb_cursor.fetchone()
            if not row:
                continue
            stored_emb = np.frombuffer(row[0], dtype=np.float32)

            # Load crop via cv2 (BGR ndarray) — same as ReIDEmbeddingService
            img_bgr = cv2.imread(str(crop_path))
            if img_bgr is None:
                logger.warning(f"Could not read crop for smoke test: {crop_path}")
                continue
            regen_emb = reid_service.extract_embedding(img_bgr)

            sim = cosine_similarity(regen_emb, stored_emb)
            if sim < 0.97:
                logger.error(f"Smoke test failed for sighting {sighting_id}. Cosine similarity: {sim}")
                smoke_passed = False
                break
            else:
                logger.info(f"Smoke test sighting {sighting_id}: cosine={sim:.4f} OK")
        except Exception as e:
            logger.error(f"Error in smoke test: {e}")
            smoke_passed = False
            break

    if smoke_samples and smoke_passed:
        logger.info("Smoke test passed.")
    elif smoke_samples:
        checks_passed = False
    else:
        logger.warning("No smoke test samples available.")

    if not checks_passed:
        logger.error("Pre-flight checks failed. Cannot activate.")
        sys.exit(1)

    if args.confirm:
        with open(".env.rollback", "w") as f:
            f.write(f"FISHDEX_REID_FINGERPRINT_CROP_ENABLED={getattr(settings, 'reid_fingerprint_crop_enabled', 'false')}\n")
            f.write(f"FISHDEX_REID_FINGERPRINT_X_START={getattr(settings, 'reid_fingerprint_x_start', '0.0')}\n")
            f.write(f"FISHDEX_REID_FINGERPRINT_X_END={getattr(settings, 'reid_fingerprint_x_end', '1.0')}\n")
            f.write(f"FISHDEX_REID_FINGERPRINT_Y_START={getattr(settings, 'reid_fingerprint_y_start', '0.0')}\n")
            f.write(f"FISHDEX_REID_FINGERPRINT_Y_END={getattr(settings, 'reid_fingerprint_y_end', '1.0')}\n")
            f.write(f"FISHDEX_REID_CACHE_NAME={getattr(settings, 'reid_cache_name', 'default')}\n")
            f.write(f"FISHDEX_REID_CALIBRATION_PATH={getattr(settings, 'reid_calibration_path', '')}\n")
        logger.info("Generated .env.rollback")

        with open(".env.fingerprint", "w") as f:
            f.write("FISHDEX_REID_FINGERPRINT_CROP_ENABLED=true\n")
            f.write(f"FISHDEX_REID_FINGERPRINT_X_START={x_start}\n")
            f.write(f"FISHDEX_REID_FINGERPRINT_X_END={x_end}\n")
            f.write(f"FISHDEX_REID_FINGERPRINT_Y_START={y_start}\n")
            f.write(f"FISHDEX_REID_FINGERPRINT_Y_END={y_end}\n")
            f.write(f"FISHDEX_REID_CACHE_NAME={args.model_version}\n")
            f.write(f"FISHDEX_REID_CALIBRATION_PATH=calibration/{args.model_version}.json\n")
        logger.info("Generated .env.fingerprint")
        logger.info("Activation successful. Please update the environment variables and restart the server.")
    else:
        logger.info("Pre-flight checks passed. Run with --confirm to activate.")

if __name__ == "__main__":
    main()
