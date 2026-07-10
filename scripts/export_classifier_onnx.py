#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

import torch

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
AI_SERVER_DIR = PROJECT_ROOT / "ai-server"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(AI_SERVER_DIR))

from train import FishClassifier
from app.data.czech_species import find_species_by_name


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True, help="Path to trained .pt checkpoint")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "ai-server" / "models" / "classifier"),
        help="Output directory for ONNX and labels.json",
    )
    parser.add_argument("--opset", type=int, default=17)
    args = parser.parse_args()

    checkpoint_path = Path(args.checkpoint).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

    print(f"Loading checkpoint: {checkpoint_path}")
    ckpt = torch.load(checkpoint_path, map_location="cpu")

    required_keys = ["model_state_dict", "num_classes", "class_to_idx"]
    for key in required_keys:
        if key not in ckpt:
            raise KeyError(f"Checkpoint missing required key: {key}")

    num_classes = int(ckpt["num_classes"])
    class_to_idx = ckpt["class_to_idx"]

    print(f"Number of classes: {num_classes}")

    model = FishClassifier(
        num_classes=num_classes,
        pretrained=False,
        dropout=0.5,
    )

    model.load_state_dict(ckpt["model_state_dict"])
    model.eval()

    dummy_input = torch.randn(1, 3, 224, 224)

    onnx_path = output_dir / "fish_species_v1.onnx"

    print(f"Exporting ONNX to: {onnx_path}")

    torch.onnx.export(
        model,
        dummy_input,
        str(onnx_path),
        input_names=["input"],
        output_names=["logits"],
        dynamic_axes={
            "input": {0: "batch"},
            "logits": {0: "batch"},
        },
        opset_version=args.opset,
    )

    # Build labels.json as index -> canonical species slug
    labels = {}
    unmatched = []

    for class_name, class_idx in class_to_idx.items():
        species_info = find_species_by_name(class_name)

        if not species_info:
            unmatched.append(class_name)
            continue

        labels[str(class_idx)] = species_info["slug"]

    if unmatched:
        print("\nERROR: These training class names do not match the Czech species catalog:")
        for name in unmatched:
            print(f"  - {name}")
        print("\nFix your dataset class folder names or add mapping logic before exporting.")
        raise RuntimeError("Unmatched class names found")

    labels_path = output_dir / "labels.json"
    labels_path.write_text(
        json.dumps(labels, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\nExport completed successfully:")
    print(f"  ONNX:   {onnx_path}")
    print(f"  Labels: {labels_path}")
    print(f"  Classes exported: {len(labels)}")


if __name__ == "__main__":
    main()
