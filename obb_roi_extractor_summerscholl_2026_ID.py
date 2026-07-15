import os
import cv2
import csv
import numpy as np
from ultralytics import YOLO
from pathlib import Path
from tqdm import tqdm


class OBBRoiExtractor:
    def __init__(self, model_path, input_dir, output_dir,
                 conf_thresh=0.3, visualize=True):
        """
        ROI extractor for YOLOv8 OBB models with optional visualization.

        Args:
            model_path (str): Path to YOLO OBB model (.pt)
            input_dir (str): Directory containing input images
            output_dir (str): Directory to save cropped ROIs and logs
            conf_thresh (float): Minimum confidence threshold
            visualize (bool): Whether to save visualization images with drawn OBBs
        """
        self.model = YOLO(model_path)
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.unqualified_dir = self.output_dir / "unqualified"
        self.unqualified_dir.mkdir(parents=True, exist_ok=True)

        self.csv_log_path = self.output_dir / "unqualified_images.csv"
        self.csv_file = open(self.csv_log_path, mode="w", newline="")
        self.csv_writer = csv.writer(self.csv_file)
        self.csv_writer.writerow(["image_name", "reason", "original_path", "saved_to"])

        self.conf_thresh = conf_thresh
        self.visualize = visualize
        self.total_images = 0
        self.qualified_images = 0

    def process_dataset(self):
        """Run ROI extraction for all images."""
        all_images = list(self.input_dir.rglob("*.png")) + list(self.input_dir.rglob("*.JPG"))
        with tqdm(total=len(all_images), desc="Processing images") as pbar:
            for img_path in all_images:
                self.process_image(img_path)
                pbar.update(1)

        self.csv_file.close()
        print("\nCompleted.")
        print(f"Total images: {self.total_images}")
        print(f"Qualified: {self.qualified_images}")
        print(f"Unqualified: {self.total_images - self.qualified_images}")

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
        print(f"[{self.total_images}] Unqualified ({reason})")


if __name__ == "__main__":
    # extractor = OBBRoiExtractor(
    #     model_path="/home/dev/Desktop/Madi/id-data/FIN_FISH_EYE_OBB/train6/weights/best.pt",
    #     input_dir="/home/dev/Desktop/Madi/id-data/tags_reformed_cropped_FISH_ONLY_black_ex/",
    #     output_dir="/home/dev/Desktop/Madi/id-data/OBB_ROI_EXTRACTED_plus_corrected00/",
    #     conf_thresh=0.2,
    #     visualize=False
    # )
    # extractor.process_dataset()
    # extractor = OBBRoiExtractor(
    #     model_path="/home/dev/Desktop/Madi/id-data/jacob_OBB_DETECTOR/train3/weights/best.pt",
    #     input_dir="/home/dev/Desktop/Madi/id-data/fish_identification_Jacob/arranged_CROPPED/S01/",
    #     output_dir="/home/dev/Desktop/Madi/id-data/fish_identification_Jacob/arranged_CROPPED_corrected00/S01",
    #     conf_thresh=0.2,
    #     visualize=False
    # )

    extractor = OBBRoiExtractor(
        model_path="/home/dev/Desktop/Madi/id-data/FIN_FISH_EYE_OBB/train6/weights/best.pt",
        input_dir="/home/dev/Desktop/Madi/identification_summer2026/",
        output_dir="/home/dev/Desktop/Madi/identification_summer2026_ROIS/",
        conf_thresh=0.2,
        visualize=False
    )
    extractor.process_dataset()
