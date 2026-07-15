#!/usr/bin/env python3
"""
train.py - Script de entrenamiento del modelo de identificacion de peces.

Utiliza PyTorch con una arquitectura ResNet50 como backbone y una cabeza
de clasificacion personalizada. Implementa:
- Fine-tuning progresivo (congelar backbone, luego descongelar)
- Learning rate scheduler (CosineAnnealingLR)
- Early stopping
- Model checkpointing (guardar mejor modelo)
- TensorBoard logging
- Metricas: accuracy, top-5 accuracy, F1 por clase
"""

import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Tuple, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset
from torch.optim.lr_scheduler import CosineAnnealingLR
from torch.utils.tensorboard import SummaryWriter
from torchvision import transforms, models
from PIL import Image
from sklearn.metrics import f1_score, accuracy_score

# --- Configuracion de logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# --- Dataset personalizado para imagenes de peces ---

class FishDataset(Dataset):
    """
    Dataset de PyTorch para cargar imagenes preprocesadas de peces.
    Lee la estructura de directorios donde cada subdirectorio es una clase.
    """

    def __init__(self, root_dir: Path, metadata: dict, transform=None):
        """
        Args:
            root_dir: Directorio raiz (train/, val/, o test/)
            metadata: Diccionario con mapeo de clases
            transform: Transformaciones de torchvision a aplicar
        """
        self.root_dir = root_dir
        self.transform = transform
        self.class_to_idx = metadata["class_to_idx"]
        self.samples = []

        # Recopilar todas las imagenes con sus etiquetas
        for class_name, class_idx in self.class_to_idx.items():
            class_dir = root_dir / class_name
            if not class_dir.exists():
                continue
            for img_path in class_dir.iterdir():
                if img_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
                    self.samples.append((img_path, class_idx))

        logger.info(
            "Dataset cargado: %d imagenes, %d clases desde %s",
            len(self.samples), len(self.class_to_idx), root_dir
        )

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Tuple[torch.Tensor, int]:
        img_path, label = self.samples[idx]

        # Cargar imagen con PIL (RGB)
        image = Image.open(img_path).convert("RGB")

        if self.transform:
            image = self.transform(image)

        return image, label


# --- Modelo de clasificacion de peces ---

class FishClassifier(nn.Module):
    """
    Clasificador de peces basado en ResNet50 con cabeza personalizada.
    Soporta fine-tuning progresivo: primero entrenar solo la cabeza,
    luego descongelar el backbone para ajuste fino.
    """

    def __init__(self, num_classes: int, pretrained: bool = True, dropout: float = 0.5):
        super().__init__()

        # Cargar ResNet50 preentrenado en ImageNet
        weights = models.ResNet50_Weights.IMAGENET1K_V2 if pretrained else None
        self.backbone = models.resnet50(weights=weights)

        # Obtener el tamano de features del backbone
        num_features = self.backbone.fc.in_features

        # Reemplazar la cabeza de clasificacion con una personalizada
        self.backbone.fc = nn.Identity()  # Remover la FC original

        # Cabeza de clasificacion con dropout y capas adicionales
        self.classifier = nn.Sequential(
            nn.Linear(num_features, 512),
            nn.ReLU(inplace=True),
            nn.Dropout(p=dropout),
            nn.Linear(512, 256),
            nn.ReLU(inplace=True),
            nn.Dropout(p=dropout / 2),
            nn.Linear(256, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        features = self.backbone(x)
        output = self.classifier(features)
        return output

    def freeze_backbone(self) -> None:
        """Congela los parametros del backbone (no se actualizan durante entrenamiento)."""
        for param in self.backbone.parameters():
            param.requires_grad = False
        logger.info("Backbone congelado - solo se entrena la cabeza de clasificacion")

    def unfreeze_backbone(self) -> None:
        """Descongela el backbone para fine-tuning completo."""
        for param in self.backbone.parameters():
            param.requires_grad = True
        logger.info("Backbone descongelado - fine-tuning completo activado")


# --- Early Stopping ---

class EarlyStopping:
    """
    Implementacion de Early Stopping para detener el entrenamiento
    cuando la metrica de validacion deja de mejorar.
    """

    def __init__(self, patience: int = 10, min_delta: float = 0.001):
        self.patience = patience
        self.min_delta = min_delta
        self.counter = 0
        self.best_score = None
        self.should_stop = False

    def __call__(self, val_score: float) -> bool:
        """
        Verifica si debemos detener el entrenamiento.
        Retorna True si debe detenerse.
        """
        if self.best_score is None:
            self.best_score = val_score
            return False

        if val_score > self.best_score + self.min_delta:
            # Mejora detectada
            self.best_score = val_score
            self.counter = 0
        else:
            # Sin mejora
            self.counter += 1
            if self.counter >= self.patience:
                self.should_stop = True
                logger.info(
                    "Early stopping activado despues de %d epocas sin mejora",
                    self.patience
                )
                return True

        return False


# --- Funciones de entrenamiento ---

def compute_topk_accuracy(output: torch.Tensor, target: torch.Tensor, topk: Tuple[int, ...] = (1, 5)) -> list:
    """
    Calcula la precision top-k para los valores especificados de k.
    Util para ver si el modelo tiene la clase correcta entre sus top predicciones.
    """
    maxk = min(max(topk), output.size(1))
    batch_size = target.size(0)

    _, pred = output.topk(maxk, 1, True, True)
    pred = pred.t()
    correct = pred.eq(target.view(1, -1).expand_as(pred))

    results = []
    for k in topk:
        k_actual = min(k, output.size(1))
        correct_k = correct[:k_actual].reshape(-1).float().sum(0, keepdim=True)
        results.append(correct_k.mul_(100.0 / batch_size).item())

    return results


def train_one_epoch(
    model: nn.Module,
    dataloader: DataLoader,
    criterion: nn.Module,
    optimizer: optim.Optimizer,
    device: torch.device,
    epoch: int,
) -> Dict[str, float]:
    """
    Ejecuta una epoca de entrenamiento.
    Retorna metricas de la epoca.
    """
    model.train()
    running_loss = 0.0
    all_preds = []
    all_labels = []

    for batch_idx, (images, labels) in enumerate(dataloader):
        images = images.to(device)
        labels = labels.to(device)

        # Forward pass
        optimizer.zero_grad()
        outputs = model(images)
        loss = criterion(outputs, labels)

        # Backward pass
        loss.backward()
        optimizer.step()

        # Acumular metricas
        running_loss += loss.item() * images.size(0)
        _, preds = outputs.max(1)
        all_preds.extend(preds.cpu().numpy())
        all_labels.extend(labels.cpu().numpy())

        # Log cada N batches
        if (batch_idx + 1) % 10 == 0:
            logger.debug(
                "  Epoch %d, Batch %d/%d, Loss: %.4f",
                epoch, batch_idx + 1, len(dataloader), loss.item()
            )

    # Calcular metricas de la epoca
    epoch_loss = running_loss / len(dataloader.dataset)
    epoch_acc = accuracy_score(all_labels, all_preds) * 100
    epoch_f1 = f1_score(all_labels, all_preds, average="macro", zero_division=0) * 100

    return {
        "loss": epoch_loss,
        "accuracy": epoch_acc,
        "f1_macro": epoch_f1,
    }


@torch.no_grad()
def validate(
    model: nn.Module,
    dataloader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    num_classes: int,
) -> Dict[str, float]:
    """
    Evalua el modelo en el conjunto de validacion.
    Calcula loss, accuracy, top-5 accuracy y F1.
    """
    model.eval()
    running_loss = 0.0
    all_preds = []
    all_labels = []
    top5_correct = 0
    total_samples = 0

    for images, labels in dataloader:
        images = images.to(device)
        labels = labels.to(device)

        outputs = model(images)
        loss = criterion(outputs, labels)

        running_loss += loss.item() * images.size(0)
        _, preds = outputs.max(1)
        all_preds.extend(preds.cpu().numpy())
        all_labels.extend(labels.cpu().numpy())

        # Top-5 accuracy
        topk = compute_topk_accuracy(outputs, labels, topk=(1, 5))
        top5_correct += topk[1] * images.size(0) / 100
        total_samples += images.size(0)

    # Calcular metricas
    val_loss = running_loss / len(dataloader.dataset)
    val_acc = accuracy_score(all_labels, all_preds) * 100
    val_top5 = (top5_correct / total_samples) * 100 if total_samples > 0 else 0
    val_f1 = f1_score(all_labels, all_preds, average="macro", zero_division=0) * 100

    # F1 por clase
    f1_per_class = f1_score(all_labels, all_preds, average=None, zero_division=0)

    return {
        "loss": val_loss,
        "accuracy": val_acc,
        "top5_accuracy": val_top5,
        "f1_macro": val_f1,
        "f1_per_class": f1_per_class.tolist(),
    }


def get_transforms(is_training: bool = True) -> transforms.Compose:
    """
    Retorna las transformaciones apropiadas para train o val/test.
    Usa normalizacion de ImageNet ya que el backbone fue preentrenado ahi.
    """
    # Normalizacion de ImageNet
    normalize = transforms.Normalize(
        mean=[0.485, 0.456, 0.406],
        std=[0.229, 0.224, 0.225],
    )

    if is_training:
        return transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.RandomHorizontalFlip(),
            transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2, hue=0.05),
            transforms.ToTensor(),
            normalize,
        ])
    else:
        return transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            normalize,
        ])


def get_next_version(models_dir: Path) -> int:
    """Determina la siguiente version del modelo basandose en archivos existentes."""
    existing = list(models_dir.glob("fish_model_v*.pt"))
    if not existing:
        return 1
    versions = []
    for p in existing:
        try:
            v = int(p.stem.split("_v")[-1])
            versions.append(v)
        except ValueError:
            continue
    return max(versions) + 1 if versions else 1


def train_model(args: argparse.Namespace) -> None:
    """
    Funcion principal de entrenamiento.
    Implementa el pipeline completo: carga datos, entrena, valida, guarda modelo.
    """
    # --- Configuracion del dispositivo ---
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Dispositivo de entrenamiento: %s", device)

    if device.type == "cuda":
        logger.info("  GPU: %s", torch.cuda.get_device_name(0))
        logger.info("  Memoria: %.1f GB", torch.cuda.get_device_properties(0).total_memory / 1e9)

    # --- Cargar metadata ---
    data_dir = Path(args.data_dir)
    metadata_path = data_dir / "metadata.json"

    if not metadata_path.exists():
        logger.error("No se encontro metadata.json en: %s", data_dir)
        logger.error("Ejecuta preprocess.py primero.")
        sys.exit(1)

    with open(metadata_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    num_classes = metadata["num_classes"]
    logger.info("Numero de clases: %d", num_classes)
    logger.info("Clases: %s", ", ".join(metadata["classes"][:10]))
    if num_classes > 10:
        logger.info("  ... y %d mas", num_classes - 10)

    # --- Crear datasets y dataloaders ---
    train_transform = get_transforms(is_training=True)
    val_transform = get_transforms(is_training=False)

    train_dataset = FishDataset(data_dir / "train", metadata, transform=train_transform)
    val_dataset = FishDataset(data_dir / "val", metadata, transform=val_transform)

    if len(train_dataset) == 0:
        logger.error("El dataset de entrenamiento esta vacio.")
        sys.exit(1)

    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
        pin_memory=True,
        drop_last=True,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
        pin_memory=True,
    )

    logger.info("Tamano de train dataset: %d", len(train_dataset))
    logger.info("Tamano de val dataset:   %d", len(val_dataset))

    # --- Crear modelo ---
    model = FishClassifier(
        num_classes=num_classes,
        pretrained=True,
        dropout=args.dropout,
    )
    model = model.to(device)

    # --- Configurar optimizador y scheduler ---
    criterion = nn.CrossEntropyLoss(label_smoothing=0.1)

    # Fase 1: Entrenar solo la cabeza (backbone congelado)
    if args.freeze_epochs > 0:
        model.freeze_backbone()
        optimizer = optim.AdamW(
            filter(lambda p: p.requires_grad, model.parameters()),
            lr=args.lr * 10,  # LR mas alto para la cabeza
            weight_decay=args.weight_decay,
        )
    else:
        optimizer = optim.AdamW(
            model.parameters(),
            lr=args.lr,
            weight_decay=args.weight_decay,
        )

    scheduler = CosineAnnealingLR(optimizer, T_max=args.epochs, eta_min=args.lr * 0.01)
    early_stopping = EarlyStopping(patience=args.patience)

    # --- TensorBoard ---
    log_dir = Path(args.log_dir) / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    writer = SummaryWriter(log_dir=str(log_dir))
    logger.info("TensorBoard logs en: %s", log_dir)

    # --- Preparar directorio de modelos ---
    models_dir = Path(args.models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)
    version = get_next_version(models_dir)
    best_model_path = models_dir / f"fish_model_v{version}.pt"
    logger.info("Version del modelo: v%d", version)

    # --- Loop de entrenamiento ---
    best_val_acc = 0.0
    training_log = {
        "version": version,
        "start_time": datetime.now().isoformat(),
        "hyperparameters": {
            "learning_rate": args.lr,
            "batch_size": args.batch_size,
            "epochs": args.epochs,
            "freeze_epochs": args.freeze_epochs,
            "dropout": args.dropout,
            "weight_decay": args.weight_decay,
            "patience": args.patience,
        },
        "num_classes": num_classes,
        "classes": metadata["classes"],
        "device": str(device),
        "epochs_completed": 0,
        "history": [],
    }

    logger.info("=" * 60)
    logger.info("INICIANDO ENTRENAMIENTO")
    logger.info("=" * 60)
    logger.info("  Epochs totales:    %d", args.epochs)
    logger.info("  Epochs congelados: %d", args.freeze_epochs)
    logger.info("  Batch size:        %d", args.batch_size)
    logger.info("  Learning rate:     %f", args.lr)
    logger.info("  Weight decay:      %f", args.weight_decay)
    logger.info("  Dropout:           %f", args.dropout)
    logger.info("=" * 60)

    start_time = time.time()

    for epoch in range(1, args.epochs + 1):
        epoch_start = time.time()

        # --- Fase de descongelamiento del backbone ---
        if epoch == args.freeze_epochs + 1 and args.freeze_epochs > 0:
            logger.info("=" * 40)
            logger.info("DESCONGELANDO BACKBONE - Epoch %d", epoch)
            logger.info("=" * 40)
            model.unfreeze_backbone()

            # Reiniciar optimizador con LR completo para fine-tuning
            optimizer = optim.AdamW(
                [
                    {"params": model.backbone.parameters(), "lr": args.lr * 0.1},
                    {"params": model.classifier.parameters(), "lr": args.lr},
                ],
                weight_decay=args.weight_decay,
            )
            scheduler = CosineAnnealingLR(
                optimizer,
                T_max=args.epochs - args.freeze_epochs,
                eta_min=args.lr * 0.01,
            )

        # --- Entrenar una epoca ---
        train_metrics = train_one_epoch(
            model, train_loader, criterion, optimizer, device, epoch
        )

        # --- Validar ---
        val_metrics = validate(model, val_loader, criterion, device, num_classes)

        # --- Actualizar scheduler ---
        scheduler.step()
        current_lr = optimizer.param_groups[0]["lr"]

        epoch_time = time.time() - epoch_start

        # --- Logging ---
        logger.info(
            "Epoch %d/%d [%.1fs] | Train Loss: %.4f Acc: %.2f%% | "
            "Val Loss: %.4f Acc: %.2f%% Top5: %.2f%% F1: %.2f%% | LR: %.6f",
            epoch, args.epochs, epoch_time,
            train_metrics["loss"], train_metrics["accuracy"],
            val_metrics["loss"], val_metrics["accuracy"],
            val_metrics["top5_accuracy"], val_metrics["f1_macro"],
            current_lr,
        )

        # TensorBoard
        writer.add_scalar("Loss/train", train_metrics["loss"], epoch)
        writer.add_scalar("Loss/val", val_metrics["loss"], epoch)
        writer.add_scalar("Accuracy/train", train_metrics["accuracy"], epoch)
        writer.add_scalar("Accuracy/val", val_metrics["accuracy"], epoch)
        writer.add_scalar("Accuracy/val_top5", val_metrics["top5_accuracy"], epoch)
        writer.add_scalar("F1/train", train_metrics["f1_macro"], epoch)
        writer.add_scalar("F1/val", val_metrics["f1_macro"], epoch)
        writer.add_scalar("LearningRate", current_lr, epoch)

        # Guardar historial
        epoch_record = {
            "epoch": epoch,
            "train_loss": train_metrics["loss"],
            "train_accuracy": train_metrics["accuracy"],
            "val_loss": val_metrics["loss"],
            "val_accuracy": val_metrics["accuracy"],
            "val_top5_accuracy": val_metrics["top5_accuracy"],
            "val_f1_macro": val_metrics["f1_macro"],
            "learning_rate": current_lr,
            "epoch_time_seconds": epoch_time,
        }
        training_log["history"].append(epoch_record)

        # --- Model checkpointing (guardar mejor modelo) ---
        if val_metrics["accuracy"] > best_val_acc:
            best_val_acc = val_metrics["accuracy"]
            checkpoint = {
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "optimizer_state_dict": optimizer.state_dict(),
                "val_accuracy": best_val_acc,
                "val_f1": val_metrics["f1_macro"],
                "num_classes": num_classes,
                "class_to_idx": metadata["class_to_idx"],
                "version": version,
            }
            torch.save(checkpoint, best_model_path)
            logger.info("  -> Nuevo mejor modelo guardado: %.2f%% (epoch %d)", best_val_acc, epoch)

        # --- Early stopping ---
        if early_stopping(val_metrics["accuracy"]):
            logger.info("Deteniendo entrenamiento por early stopping en epoch %d", epoch)
            break

        training_log["epochs_completed"] = epoch

    # --- Fin del entrenamiento ---
    total_time = time.time() - start_time
    training_log["end_time"] = datetime.now().isoformat()
    training_log["total_time_seconds"] = total_time
    training_log["best_val_accuracy"] = best_val_acc
    training_log["model_path"] = str(best_model_path)

    # Guardar log de entrenamiento
    log_path = models_dir / "training_log.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(training_log, f, indent=2, ensure_ascii=False)

    writer.close()

    # Resumen final
    logger.info("=" * 60)
    logger.info("ENTRENAMIENTO COMPLETADO")
    logger.info("=" * 60)
    logger.info("  Tiempo total:        %.1f minutos", total_time / 60)
    logger.info("  Epochs completados:  %d", training_log["epochs_completed"])
    logger.info("  Mejor val accuracy:  %.2f%%", best_val_acc)
    logger.info("  Modelo guardado en:  %s", best_model_path)
    logger.info("  Log guardado en:     %s", log_path)
    logger.info("  TensorBoard:         tensorboard --logdir %s", args.log_dir)
    logger.info("=" * 60)


def parse_args() -> argparse.Namespace:
    """Parsea los hiperparametros y configuracion desde la linea de comandos."""
    parser = argparse.ArgumentParser(
        description="Entrena el modelo de identificacion de peces (ResNet50).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplo de uso:
  python train.py --data-dir data/processed --epochs 50 --batch-size 32
  python train.py --data-dir data/processed --lr 0.0001 --freeze-epochs 5
  python train.py --data-dir data/processed --epochs 100 --patience 15

Para monitorear con TensorBoard:
  tensorboard --logdir runs/
        """,
    )

    # Datos y directorios
    parser.add_argument("--data-dir", type=str, default="data/processed",
                        help="Directorio con datos preprocesados (default: data/processed)")
    parser.add_argument("--models-dir", type=str, default="models",
                        help="Directorio para guardar modelos (default: models)")
    parser.add_argument("--log-dir", type=str, default="runs",
                        help="Directorio para logs de TensorBoard (default: runs)")

    # Hiperparametros de entrenamiento
    parser.add_argument("--epochs", type=int, default=50,
                        help="Numero maximo de epocas (default: 50)")
    parser.add_argument("--batch-size", type=int, default=32,
                        help="Tamano del batch (default: 32)")
    parser.add_argument("--lr", type=float, default=0.001,
                        help="Learning rate inicial (default: 0.001)")
    parser.add_argument("--weight-decay", type=float, default=0.01,
                        help="Weight decay para regularizacion (default: 0.01)")
    parser.add_argument("--dropout", type=float, default=0.5,
                        help="Probabilidad de dropout en la cabeza (default: 0.5)")

    # Fine-tuning
    parser.add_argument("--freeze-epochs", type=int, default=5,
                        help="Epocas con backbone congelado (default: 5)")

    # Early stopping
    parser.add_argument("--patience", type=int, default=10,
                        help="Epocas sin mejora antes de detener (default: 10)")

    # Sistema
    parser.add_argument("--num-workers", type=int, default=4,
                        help="Workers para DataLoader (default: 4)")
    parser.add_argument("--seed", type=int, default=42,
                        help="Semilla aleatoria (default: 42)")
    parser.add_argument("--verbose", action="store_true",
                        help="Logging detallado")

    return parser.parse_args()


def main() -> None:
    """Punto de entrada principal."""
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Fijar semillas para reproducibilidad
    torch.manual_seed(args.seed)
    np.random.seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False

    logger.info("FishDex - Entrenamiento del modelo de clasificacion")
    logger.info("PyTorch version: %s", torch.__version__)
    logger.info("CUDA disponible: %s", torch.cuda.is_available())

    train_model(args)


if __name__ == "__main__":
    main()
