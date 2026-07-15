#!/usr/bin/env python3
"""
evaluate.py - Script de evaluacion del modelo de identificacion de peces.

Carga el modelo entrenado, ejecuta inferencia en el conjunto de test y calcula:
- Accuracy general
- Precision, Recall, F1 por clase
- Matriz de confusion
- Comparacion con version anterior del modelo (si existe)
- Genera reporte JSON con resultados
- Retorna exit code 0 si pasa el umbral minimo, 1 si no

Uso:
  python evaluate.py --model-path models/fish_model_v1.pt --data-dir data/processed
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple
from datetime import datetime

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
from torchvision import transforms
from PIL import Image
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    classification_report,
)

# --- Configuracion de logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# --- Reutilizar clases del script de entrenamiento ---
# En produccion esto seria un modulo compartido; aqui lo redefinimos para independencia

class FishDataset(torch.utils.data.Dataset):
    """Dataset para cargar imagenes de test."""

    def __init__(self, root_dir: Path, metadata: dict, transform=None):
        self.root_dir = root_dir
        self.transform = transform
        self.class_to_idx = metadata["class_to_idx"]
        self.samples = []

        for class_name, class_idx in self.class_to_idx.items():
            class_dir = root_dir / class_name
            if not class_dir.exists():
                continue
            for img_path in class_dir.iterdir():
                if img_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                    self.samples.append((img_path, class_idx))

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        img_path, label = self.samples[idx]
        image = Image.open(img_path).convert("RGB")
        if self.transform:
            image = self.transform(image)
        return image, label


class FishClassifier(nn.Module):
    """Modelo de clasificacion (debe coincidir con la arquitectura de train.py)."""

    def __init__(self, num_classes: int, dropout: float = 0.5):
        super().__init__()
        from torchvision import models
        self.backbone = models.resnet50(weights=None)
        num_features = self.backbone.fc.in_features
        self.backbone.fc = nn.Identity()
        self.classifier = nn.Sequential(
            nn.Linear(num_features, 512),
            nn.ReLU(inplace=True),
            nn.Dropout(p=dropout),
            nn.Linear(512, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(p=dropout / 2),
            nn.Linear(256, num_classes),
        )

    def forward(self, x):
        features = self.backbone(x)
        return self.classifier(features)


def get_eval_transforms() -> transforms.Compose:
    """Transformaciones para evaluacion (sin aumento de datos)."""
    return transforms.Compose([
        transforms.Resize((224, 224)),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=[0.485, 0.456, 0.406],
            std=[0.229, 0.224, 0.225],
        ),
    ])


def load_model(model_path: Path, device: torch.device) -> Tuple[nn.Module, dict]:
    """
    Carga el modelo entrenado desde un checkpoint.
    Retorna el modelo y la informacion del checkpoint.
    """
    if not model_path.exists():
        logger.error("Modelo no encontrado: %s", model_path)
        sys.exit(1)

    logger.info("Cargando modelo desde: %s", model_path)
    checkpoint = torch.load(model_path, map_location=device, weights_only=False)

    num_classes = checkpoint["num_classes"]
    model = FishClassifier(num_classes=num_classes)
    model.load_state_dict(checkpoint["model_state_dict"])
    model = model.to(device)
    model.eval()

    logger.info("  Version: v%d", checkpoint.get("version", 0))
    logger.info("  Epoch de entrenamiento: %d", checkpoint.get("epoch", 0))
    logger.info("  Val accuracy (train): %.2f%%", checkpoint.get("val_accuracy", 0))
    logger.info("  Num clases: %d", num_classes)

    return model, checkpoint


@torch.no_grad()
def run_inference(
    model: nn.Module,
    dataloader: DataLoader,
    device: torch.device,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Ejecuta inferencia en todo el dataset de test.
    Retorna predicciones, etiquetas reales y probabilidades.
    """
    all_preds = []
    all_labels = []
    all_probs = []

    for images, labels in dataloader:
        images = images.to(device)
        outputs = model(images)
        probs = torch.softmax(outputs, dim=1)

        _, preds = outputs.max(1)
        all_preds.extend(preds.cpu().numpy())
        all_labels.extend(labels.numpy())
        all_probs.extend(probs.cpu().numpy())

    return (
        np.array(all_preds),
        np.array(all_labels),
        np.array(all_probs),
    )


def compute_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    y_probs: np.ndarray,
    class_names: list,
) -> Dict:
    """
    Calcula todas las metricas de evaluacion.
    Retorna un diccionario con los resultados.
    """
    # Metricas generales
    accuracy = accuracy_score(y_true, y_pred) * 100
    precision_macro = precision_score(y_true, y_pred, average="macro", zero_division=0) * 100
    recall_macro = recall_score(y_true, y_pred, average="macro", zero_division=0) * 100
    f1_macro = f1_score(y_true, y_pred, average="macro", zero_division=0) * 100
    f1_weighted = f1_score(y_true, y_pred, average="weighted", zero_division=0) * 100

    # Top-5 accuracy
    num_classes = y_probs.shape[1]
    k = min(5, num_classes)
    top5_preds = np.argsort(y_probs, axis=1)[:, -k:]
    top5_correct = sum(1 for i, label in enumerate(y_true) if label in top5_preds[i])
    top5_accuracy = (top5_correct / len(y_true)) * 100

    # Metricas por clase
    precision_per_class = precision_score(y_true, y_pred, average=None, zero_division=0)
    recall_per_class = recall_score(y_true, y_pred, average=None, zero_division=0)
    f1_per_class = f1_score(y_true, y_pred, average=None, zero_division=0)

    per_class_metrics = {}
    for i, class_name in enumerate(class_names):
        if i < len(precision_per_class):
            per_class_metrics[class_name] = {
                "precision": float(precision_per_class[i] * 100),
                "recall": float(recall_per_class[i] * 100),
                "f1": float(f1_per_class[i] * 100),
                "support": int(np.sum(y_true == i)),
            }

    # Matriz de confusion
    cm = confusion_matrix(y_true, y_pred)

    return {
        "accuracy": float(accuracy),
        "top5_accuracy": float(top5_accuracy),
        "precision_macro": float(precision_macro),
        "recall_macro": float(recall_macro),
        "f1_macro": float(f1_macro),
        "f1_weighted": float(f1_weighted),
        "per_class": per_class_metrics,
        "confusion_matrix": cm.tolist(),
        "total_samples": int(len(y_true)),
        "correct_predictions": int(np.sum(y_true == y_pred)),
    }


def load_previous_report(models_dir: Path) -> Optional[Dict]:
    """
    Busca y carga el reporte de evaluacion de la version anterior.
    Util para comparar rendimiento entre versiones.
    """
    reports = sorted(models_dir.glob("eval_report_v*.json"))
    if not reports:
        return None

    # Cargar el mas reciente
    latest_report = reports[-1]
    logger.info("Reporte anterior encontrado: %s", latest_report)

    with open(latest_report, "r", encoding="utf-8") as f:
        return json.load(f)


def compare_with_previous(
    current_metrics: Dict,
    previous_report: Optional[Dict],
) -> Dict:
    """
    Compara metricas actuales con la version anterior.
    Retorna un diccionario con las diferencias.
    """
    if previous_report is None:
        return {"previous_version": None, "comparison": "No hay version anterior para comparar"}

    prev_metrics = previous_report.get("metrics", {})
    comparison = {
        "previous_version": previous_report.get("version"),
        "accuracy_delta": current_metrics["accuracy"] - prev_metrics.get("accuracy", 0),
        "f1_delta": current_metrics["f1_macro"] - prev_metrics.get("f1_macro", 0),
        "top5_delta": current_metrics["top5_accuracy"] - prev_metrics.get("top5_accuracy", 0),
        "improved": current_metrics["accuracy"] > prev_metrics.get("accuracy", 0),
    }

    return comparison


def evaluate_model(args: argparse.Namespace) -> bool:
    """
    Pipeline principal de evaluacion.
    Retorna True si el modelo pasa el umbral minimo, False en caso contrario.
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Dispositivo de evaluacion: %s", device)

    # --- Cargar metadata ---
    data_dir = Path(args.data_dir)
    metadata_path = data_dir / "metadata.json"

    if not metadata_path.exists():
        logger.error("No se encontro metadata.json en: %s", data_dir)
        sys.exit(1)

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    class_names = metadata["classes"]
    logger.info("Clases en el dataset: %d", len(class_names))

    # --- Cargar modelo ---
    model_path = Path(args.model_path)
    model, checkpoint = load_model(model_path, device)
    version = checkpoint.get("version", 0)

    # --- Preparar dataset de test ---
    test_dir = data_dir / "test"
    if not test_dir.exists():
        logger.error("Directorio de test no encontrado: %s", test_dir)
        sys.exit(1)

    test_transform = get_eval_transforms()
    test_dataset = FishDataset(test_dir, metadata, transform=test_transform)

    if len(test_dataset) == 0:
        logger.error("El dataset de test esta vacio.")
        sys.exit(1)

    test_loader = DataLoader(
        test_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=True,
    )

    logger.info("Imagenes de test: %d", len(test_dataset))

    # --- Ejecutar inferencia ---
    logger.info("Ejecutando inferencia en conjunto de test...")
    y_pred, y_true, y_probs = run_inference(model, test_loader, device)

    # --- Calcular metricas ---
    logger.info("Calculando metricas...")
    metrics = compute_metrics(y_true, y_pred, y_probs, class_names)

    # --- Comparar con version anterior ---
    models_dir = Path(args.models_dir)
    previous_report = load_previous_report(models_dir)
    comparison = compare_with_previous(metrics, previous_report)

    # --- Determinar si pasa el umbral ---
    passes_threshold = metrics["accuracy"] >= args.min_accuracy
    status = "APROBADO" if passes_threshold else "RECHAZADO"

    # --- Generar reporte ---
    report = {
        "version": version,
        "model_path": str(model_path),
        "evaluation_date": datetime.now().isoformat(),
        "dataset": {
            "test_dir": str(test_dir),
            "num_samples": metrics["total_samples"],
            "num_classes": len(class_names),
        },
        "metrics": metrics,
        "comparison": comparison,
        "threshold": {
            "min_accuracy": args.min_accuracy,
            "actual_accuracy": metrics["accuracy"],
            "passes": passes_threshold,
            "status": status,
        },
        "device": str(device),
    }

    # Guardar reporte
    report_path = models_dir / f"eval_report_v{version}.json"
    models_dir.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # --- Imprimir resultados ---
    logger.info("=" * 60)
    logger.info("RESULTADOS DE EVALUACION - Modelo v%d", version)
    logger.info("=" * 60)
    logger.info("  Accuracy:          %.2f%%", metrics["accuracy"])
    logger.info("  Top-5 Accuracy:    %.2f%%", metrics["top5_accuracy"])
    logger.info("  Precision (macro): %.2f%%", metrics["precision_macro"])
    logger.info("  Recall (macro):    %.2f%%", metrics["recall_macro"])
    logger.info("  F1 (macro):        %.2f%%", metrics["f1_macro"])
    logger.info("  F1 (weighted):     %.2f%%", metrics["f1_weighted"])
    logger.info("-" * 60)
    logger.info("  Muestras totales:    %d", metrics["total_samples"])
    logger.info("  Predicciones correctas: %d", metrics["correct_predictions"])
    logger.info("-" * 60)

    # Metricas por clase (top 10 y bottom 10)
    logger.info("  METRICAS POR CLASE:")
    sorted_classes = sorted(
        metrics["per_class"].items(),
        key=lambda x: x[1]["f1"],
        reverse=True,
    )

    logger.info("  Mejores clases:")
    for name, m in sorted_classes[:10]:
        logger.info("    %-20s P:%.1f%% R:%.1f%% F1:%.1f%% (n=%d)",
                    name, m["precision"], m["recall"], m["f1"], m["support"])

    if len(sorted_classes) > 10:
        logger.info("  Peores clases:")
        for name, m in sorted_classes[-5:]:
            logger.info("    %-20s P:%.1f%% R:%.1f%% F1:%.1f%% (n=%d)",
                        name, m["precision"], m["recall"], m["f1"], m["support"])

    logger.info("-" * 60)

    # Comparacion con version anterior
    if comparison.get("previous_version") is not None:
        logger.info("  COMPARACION CON VERSION ANTERIOR (v%d):", comparison["previous_version"])
        logger.info("    Accuracy:  %+.2f%%", comparison["accuracy_delta"])
        logger.info("    F1:        %+.2f%%", comparison["f1_delta"])
        logger.info("    Top-5:     %+.2f%%", comparison["top5_delta"])
        logger.info("    Mejorado:  %s", "Si" if comparison["improved"] else "No")
        logger.info("-" * 60)

    # Veredicto final
    logger.info("")
    logger.info("  UMBRAL MINIMO: %.1f%%", args.min_accuracy)
    logger.info("  ACCURACY REAL: %.2f%%", metrics["accuracy"])
    logger.info("")
    if passes_threshold:
        logger.info("  *** RESULTADO: APROBADO ***")
        logger.info("  El modelo cumple con el umbral minimo de accuracy.")
    else:
        logger.info("  *** RESULTADO: RECHAZADO ***")
        logger.info("  El modelo NO cumple con el umbral minimo de accuracy.")
        logger.info("  Se requiere re-entrenamiento o mas datos.")

    logger.info("")
    logger.info("  Reporte guardado en: %s", report_path)
    logger.info("=" * 60)

    return passes_threshold


def parse_args() -> argparse.Namespace:
    """Parsea los argumentos de linea de comandos."""
    parser = argparse.ArgumentParser(
        description="Evalua el modelo de identificacion de peces en el conjunto de test.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplo de uso:
  python evaluate.py --model-path models/fish_model_v1.pt --data-dir data/processed
  python evaluate.py --model-path models/fish_model_v1.pt --min-accuracy 90

Codigos de salida:
  0 - El modelo pasa el umbral de accuracy
  1 - El modelo NO pasa el umbral
        """,
    )
    parser.add_argument("--model-path", type=str, required=True,
                        help="Ruta al archivo del modelo (.pt)")
    parser.add_argument("--data-dir", type=str, default="data/processed",
                        help="Directorio con datos preprocesados (default: data/processed)")
    parser.add_argument("--models-dir", type=str, default="models",
                        help="Directorio de modelos para reportes (default: models)")
    parser.add_argument("--min-accuracy", type=float, default=85.0,
                        help="Umbral minimo de accuracy en porcentaje (default: 85.0)")
    parser.add_argument("--batch-size", type=int, default=32,
                        help="Tamano de batch para inferencia (default: 32)")
    parser.add_argument("--num-workers", type=int, default=4,
                        help="Workers para DataLoader (default: 4)")
    parser.add_argument("--verbose", action="store_true",
                        help="Logging detallado")
    return parser.parse_args()


def main() -> None:
    """Punto de entrada principal."""
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    logger.info("FishDex - Evaluacion del modelo de clasificacion")

    # Ejecutar evaluacion
    passes = evaluate_model(args)

    # Retornar codigo de salida apropiado
    if passes:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
