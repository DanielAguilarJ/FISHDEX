import argparse
import json
import logging
import math
import os
import sqlite3
import sys
from pathlib import Path

import cv2
import numpy as np
from app.config import settings
from app.database import get_db_connection

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

CONFIGS = {
    "A": {"x": (0.20, 0.80), "y": (0.05, 0.55), "color": (0, 255, 0)},
    "B": {"x": (0.15, 0.85), "y": (0.00, 0.60), "color": (255, 0, 0)},
    "C": {"x": (0.333, 0.667), "y": (0.05, 0.35), "color": (0, 0, 255)}
}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="audit/fingerprint/")
    parser.add_argument("--species")
    parser.add_argument("--max-samples", type=int, default=300)
    parser.add_argument("--config", choices=["A", "B", "C"], default="A")
    parser.add_argument("--cols", type=int, default=5)
    parser.add_argument("--rows", type=int, default=6)
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cfg = CONFIGS[args.config]

    db_conn = get_db_connection()
    db_conn.row_factory = sqlite3.Row
    cursor = db_conn.cursor()

    query = "SELECT s.id, s.fish_id, sp.slug as species_slug, s.artifact_dir FROM fish_sightings s JOIN species sp ON s.species_id = sp.id WHERE s.artifact_dir IS NOT NULL"
    params = []
    if args.species:
        query += " AND sp.slug = ?"
        params.append(args.species)
    query += " ORDER BY RANDOM() LIMIT ?"
    params.append(args.max_samples)

    cursor.execute(query, params)
    sightings = cursor.fetchall()

    storage_base = Path(settings.server_data_dir) / 'storage'

    cell_w, cell_h = 200, 200
    sheet_w = cell_w * args.cols
    sheet_h = cell_h * args.rows

    crops = []

    for row in sightings:
        crop_path = storage_base / row["artifact_dir"] / "images" / "crop_00.jpg"
        if not crop_path.exists():
            continue

        img = cv2.imread(str(crop_path))
        if img is None:
            continue

        orig_h, orig_w = img.shape[:2]

        # Draw rectangle
        x1 = int(orig_w * cfg["x"][0])
        x2 = int(orig_w * cfg["x"][1])
        y1 = int(orig_h * cfg["y"][0])
        y2 = int(orig_h * cfg["y"][1])

        cv2.rectangle(img, (x1, y1), (x2, y2), cfg["color"], 2)

        # Resize
        img = cv2.resize(img, (cell_w, cell_h))

        # Overlay text
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.4
        thickness = 1
        text_color = (255, 255, 255)

        texts = [
            f"Sp: {row['species_slug']}",
            f"F: {row['fish_id']}",
            f"S: {row['id']}",
            f"{orig_w}x{orig_h}"
        ]

        for i, text in enumerate(texts):
            y = 15 + i * 15
            # Add a small shadow/border for readability
            cv2.putText(img, text, (6, y + 1), font, font_scale, (0, 0, 0), thickness + 1, cv2.LINE_AA)
            cv2.putText(img, text, (5, y), font, font_scale, text_color, thickness, cv2.LINE_AA)

        crops.append(img)

    # Arrange into contact sheets
    cells_per_page = args.cols * args.rows
    num_pages = math.ceil(len(crops) / cells_per_page)

    contact_sheets = []

    for page in range(num_pages):
        sheet = np.zeros((sheet_h, sheet_w, 3), dtype=np.uint8)
        start_idx = page * cells_per_page
        end_idx = min(start_idx + cells_per_page, len(crops))
        page_crops = crops[start_idx:end_idx]

        for i, crop in enumerate(page_crops):
            r = i // args.cols
            c = i % args.cols
            y1 = r * cell_h
            y2 = y1 + cell_h
            x1 = c * cell_w
            x2 = x1 + cell_w
            sheet[y1:y2, x1:x2] = crop

        out_path = out_dir / f"contact_sheet_{page+1:03d}.jpg"
        cv2.imwrite(str(out_path), sheet)
        contact_sheets.append(out_path.name)

    audit_data = {
        "dorsal_audit_passed": False,
        "samples_reviewed": len(crops),
        "reviewed_by": "<FILL IN>",
        "reviewed_at": "<FILL IN>",
        "notes": "<FILL IN>",
        "config": args.config,
        "fingerprint_bounds": {
            "x_start": cfg["x"][0],
            "x_end": cfg["x"][1],
            "y_start": cfg["y"][0],
            "y_end": cfg["y"][1]
        },
        "contact_sheets": contact_sheets,
        "total_samples": len(crops)
    }

    with open(out_dir / "audit.json", "w") as f:
        json.dump(audit_data, f, indent=2)

    logger.info(f"Generated {num_pages} contact sheets and audit.json in {out_dir}")

if __name__ == "__main__":
    main()
