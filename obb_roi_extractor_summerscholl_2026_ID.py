"""
OBB ROI extractor for the summer-2026 identification dataset.

Runs a YOLOv8 oriented-bounding-box detector over an image tree and writes
perspective-corrected (deskewed) fish crops, logging every image it could not
qualify.

The deskew geometry here is the reference implementation that
``ai-server/app/services/obb_roi_service.py`` mirrors. Keep the two in sync:
if the crop geometry diverges, embeddings produced offline stop being comparable
with the ones the server computes at inference time.

Usage:
    python obb_roi_extractor_summerscholl_2026_ID.py \\
        --model-path weights/best.pt \\
        --input-dir  data/identification_summer2026 \\
        --output-dir data/identification_summer2026_ROIS
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from tqdm import tqdm
from ultralytics import YOLO

logger = logging.getLogger(__name__)

# Every image extension the dataset may contain. The original only matched
# "*.png" and "*.JPG", silently skipping the far more common lowercase ".jpg".
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")


class OBBRoiExtractor:
    """Extracts deskewed ROIs from images using a YOLOv8 OBB detector."""

    def __init__(
        self,
        model_path: str,
        input_dir: str,
        output_dir: str,
        conf_thresh: float = 0.3,
        visualize: bool = True,
    ) -> None:
        """
        Initialise the extractor.

        Args:
            model_path: Path to the YOLO OBB checkpoint (.pt).
            input_dir: Directory tree containing input images.
            output_dir: Destination for crops, logs and optional visualisations.
            conf_thresh: Minimum detection confidence.
            visualize: Whether to also write annotated images with drawn OBBs.
        """
        self.model = YOLO(model_path)
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.unqualified_dir = self.output_dir / "unqualified"
        self.unqualified_dir.mkdir(parents=True, exist_ok=True)

        self.csv_log_path = self.output_dir / "unqualified_images.csv"
        # Opened lazily in process_dataset() so the handle's lifetime is bounded
        # by a context manager. Holding it open from __init__ leaked the
        # descriptor whenever processing raised.
        self.csv_file = None
        self.csv_writer = None

        self.conf_thresh = conf_thresh
        self.visualize = visualize
        self.total_images = 0
        self.qualified_images = 0

    def _discover_images(self) -> list[Path]:
        """
        Collect every supported image under the input directory.

        Returns:
            Sorted, de-duplicated list of image paths.
        """
        found: set[Path] = set()
        for path in self.input_dir.rglob("*"):
            if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES:
                found.add(path)
        return sorted(found)

    def process_dataset(self) -> None:
        """
        Run ROI extraction across the whole input tree.

        The CSV log is written inside a ``with`` block so the file is flushed and
        closed even if an image raises.
        """
        all_images = self._discover_images()
        if not all_images:
            logger.warning("No images found under %s", self.input_dir)
            return

        logger.info("Processing %d images from %s", len(all_images), self.input_dir)

        with open(self.csv_log_path, mode="w", newline="", encoding="utf-8") as handle:
            self.csv_file = handle
            self.csv_writer = csv.writer(handle)
            self.csv_writer.writerow(
                ["image_name", "reason", "original_path", "saved_to"]
            )

            with tqdm(total=len(all_images), desc="Processing images") as pbar:
                for img_path in all_images:
                    try:
                        self.process_image(img_path)
                    except Exception as exc:  # noqa: BLE001 — one bad file must not abort the run
                        logger.error("Failed on %s: %s", img_path, exc, exc_info=True)
                    pbar.update(1)

        self.csv_file = None
        self.csv_writer = None

        unqualified = self.total_images - self.qualified_images
        logger.info(
            "Completed. total=%d qualified=%d unqualified=%d",
            self.total_images,
            self.qualified_images,
            unqualified,
        )

    def process_image(self, image_path):
        """Detect, crop, and (optionally) visualize oriented boxes."""
        self.total_images += 1
        img = cv2.imread(str(image_path))
        if img is None:
            self._log_unqualified(image_path, "failed to read")
            return

        # Run YOLOv8-OBB inference
        results = self.model(img, verbose=False, conf=self.conf_thresh, task="obb")[0]

        # Validate OBB detections
        if not hasattr(results, "obb") or results.obb is None or len(results.obb.xyxyxyxy) == 0:
            self._log_unqualified(image_path, "no detection")
            return

        polys = results.obb.xyxyxyxy.cpu().numpy()
        confs = results.obb.conf.cpu().numpy()

        # Logic: only one object is qualified
        if len(polys) != 1:
            reason = f"{len(polys)} detections"
            self._log_unqualified(image_path, reason)
            return

        # Get the single detection polygon
        best_poly = polys[0].reshape((4, 2))
        conf = confs[0]
        cls_id = int(results.obb.cls[0])

        # Draw visualization (optional)
        vis_img = img.copy()
        if self.visualize:
            cv2.polylines(vis_img, [best_poly.astype(int)], isClosed=True, color=(0, 255, 0), thickness=2)
            label = f"{results.names[cls_id]} {conf:.2f}"
            tl = tuple(best_poly[0].astype(int))
            cv2.putText(vis_img, label, tl, cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA)

        # Deskew crop
        roi = self._deskew_crop(img, best_poly)
        if roi is None or roi.size == 0:
            self._log_unqualified(image_path, "empty ROI after crop")
            return

        # Save output
        relative_path = image_path.relative_to(self.input_dir)
        out_dir = self.output_dir / relative_path.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        base_name = Path(image_path.name).stem

        roi_path = out_dir / f"{base_name}_roi.png"
        cv2.imwrite(str(roi_path), roi)

        if self.visualize:
            vis_path = out_dir / f"{base_name}_vis.jpg"
            cv2.imwrite(str(vis_path), vis_img)

        self.qualified_images += 1
        print(f"[{self.total_images}] Qualified | {self.qualified_images}/{self.total_images}")

    def _deskew_crop(self, img, pts):
        """Rectify rotated OBB crop horizontally."""
        pts = np.array(pts, dtype=np.float32)
        rect = self._order_points_clockwise(pts)
        (tl, tr, br, bl) = rect

        widthA = np.linalg.norm(br - bl)
        widthB = np.linalg.norm(tr - tl)
        heightA = np.linalg.norm(tr - br)
        heightB = np.linalg.norm(tl - bl)
        maxWidth = int(max(widthA, widthB))
        maxHeight = int(max(heightA, heightB))

        if maxWidth <= 0 or maxHeight <= 0:
            return None

        dst = np.array([
            [0, 0],
            [maxWidth - 1, 0],
            [maxWidth - 1, maxHeight - 1],
            [0, maxHeight - 1]], dtype=np.float32)

        M = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(img, M, (maxWidth, maxHeight))
        return warped

    @staticmethod
    def _order_points_clockwise(pts):
        """Ensure consistent ordering of OBB points."""
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]  # top-left
        rect[2] = pts[np.argmax(s)]  # bottom-right
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]  # top-right
        rect[3] = pts[np.argmax(diff)]  # bottom-left
        return rect

    def _log_unqualified(self, image_path, reason):
        """Save and log unqualified images."""
        relative_path = image_path.relative_to(self.input_dir)
        dest_path = self.unqualified_dir / relative_path
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        img = cv2.imread(str(image_path))
        if img is not None:
            cv2.imwrite(str(dest_path), img)
        self.csv_writer.writerow([image_path.name, reason, str(image_path), str(dest_path)])
        logger.debug("[%d] Unqualified (%s)", self.total_images, reason)


def _build_arg_parser() -> "argparse.ArgumentParser":
    """
    Build the command-line interface.

    Returns:
        Configured parser. Paths were previously hardcoded to
        ``/home/dev/Desktop/Madi/...``, which made the script unrunnable on any
        other machine; they are now required arguments with environment-variable
        fallbacks.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Extract deskewed oriented-bounding-box ROIs from a fish image dataset."
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--model-path",
        default=os.environ.get("FISHDEX_OBB_MODEL_PATH"),
        help="YOLO OBB .pt checkpoint (env: FISHDEX_OBB_MODEL_PATH)",
    )
    parser.add_argument(
        "--input-dir",
        default=os.environ.get("FISHDEX_OBB_INPUT_DIR"),
        help="Directory tree containing source images (env: FISHDEX_OBB_INPUT_DIR)",
    )
    parser.add_argument(
        "--output-dir",
        default=os.environ.get("FISHDEX_OBB_OUTPUT_DIR"),
        help="Destination for extracted ROIs (env: FISHDEX_OBB_OUTPUT_DIR)",
    )
    parser.add_argument(
        "--conf-thresh",
        type=float,
        default=float(os.environ.get("FISHDEX_OBB_CONF_THRESHOLD", "0.2")),
        help="Minimum detection confidence",
    )
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="Write annotated debug images alongside the ROIs",
    )
    return parser


def main() -> int:
    """
    Parse arguments and run the extractor.

    Returns:
        Process exit status: 0 on success, 2 on a usage error.
    """
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(message)s"
    )
    parser = _build_arg_parser()
    args = parser.parse_args()

    missing = [
        name
        for name, value in (
            ("--model-path", args.model_path),
            ("--input-dir", args.input_dir),
            ("--output-dir", args.output_dir),
        )
        if not value
    ]
    if missing:
        parser.error(f"missing required argument(s): {', '.join(missing)}")

    if not Path(args.model_path).is_file():
        parser.error(f"model checkpoint not found: {args.model_path}")
    if not Path(args.input_dir).is_dir():
        parser.error(f"input directory not found: {args.input_dir}")

    extractor = OBBRoiExtractor(
        model_path=args.model_path,
        input_dir=args.input_dir,
        output_dir=args.output_dir,
        conf_thresh=args.conf_thresh,
        visualize=args.visualize,
    )
    extractor.process_dataset()
    return 0


if __name__ == "__main__":
    sys.exit(main())
