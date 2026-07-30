#!/usr/bin/env python3
"""
preprocess.py - Preprocesamiento de imagenes para el modelo de identificacion de peces.

Realiza:
- Redimensionado a 224x224 (estandar para modelos de clasificacion)
- Normalizacion de valores de pixeles
- Aumento de datos (flip horizontal, rotacion, brillo, jitter de color)
- Division en conjuntos train/val/test (80/10/10)
- Generacion de metadata.json con mapeo de clases

Estructura de salida:
    data/processed/train/{fish_id}/image_xxx.jpg
    data/processed/val/{fish_id}/image_xxx.jpg
    data/processed/test/{fish_id}/image_xxx.jpg
    data/processed/metadata.json
"""

import os
import sys
import json
import argparse
import logging
import random
from pathlib import Path
from typing import Tuple, List, Dict

import cv2
import numpy as np

# --- Configuracion de logging ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# --- Constantes de preprocesamiento ---
TARGET_SIZE = (224, 224)  # Tamano estandar para ResNet/EfficientNet
TRAIN_RATIO = 0.80
VAL_RATIO = 0.10
TEST_RATIO = 0.10
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff"}


def load_image(path: Path) -> np.ndarray:
    """
    Carga una imagen desde disco usando OpenCV.
    Retorna la imagen en formato BGR (OpenCV default).
    """
    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"No se pudo cargar la imagen: {path}")
    return img


def resize_image(img: np.ndarray, size: Tuple[int, int] = TARGET_SIZE) -> np.ndarray:
    """
    Letterbox resize to preserve aspect ratio.
    """
    target_w, target_h = size
    h, w = img.shape[:2]

    scale = min(target_w / w, target_h / h)
    new_w = int(round(w * scale))
    new_h = int(round(h * scale))

    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

    pad_w = target_w - new_w
    pad_h = target_h - new_h

    pad_left = pad_w // 2
    pad_right = pad_w - pad_left
    pad_top = pad_h // 2
    pad_bottom = pad_h - pad_top

    padded = cv2.copyMakeBorder(
        resized,
        pad_top,
        pad_bottom,
        pad_left,
        pad_right,
        cv2.BORDER_CONSTANT,
        value=(114, 114, 114),
    )

    return padded


def normalize_image(img: np.ndarray) -> np.ndarray:
    """
    Normaliza los valores de pixeles al rango [0, 1].
    Esto es necesario para el entrenamiento del modelo.
    """
    return img.astype(np.float32) / 255.0


def denormalize_image(img: np.ndarray) -> np.ndarray:
    """Revierte la normalizacion para guardar como imagen."""
    return (img * 255.0).clip(0, 255).astype(np.uint8)


# --- Funciones de aumento de datos ---

def augment_horizontal_flip(img: np.ndarray) -> np.ndarray:
    """Aplica flip horizontal (espejo) a la imagen."""
    return cv2.flip(img, 1)


def augment_rotation(img: np.ndarray, max_angle: float = 15.0) -> np.ndarray:
    """
    Aplica una rotacion aleatoria dentro del rango [-max_angle, +max_angle].
    Rellena los bordes con negro.
    """
    angle = random.uniform(-max_angle, max_angle)
    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(img, matrix, (w, h), borderMode=cv2.BORDER_REFLECT_101)
    return rotated


def augment_brightness(img: np.ndarray, factor_range: Tuple[float, float] = (0.7, 1.3)) -> np.ndarray:
    """
    Varia el brillo de la imagen multiplicando por un factor aleatorio.
    factor < 1: mas oscuro, factor > 1: mas brillante
    """
    factor = random.uniform(*factor_range)
    adjusted = img.astype(np.float32) * factor
    return adjusted.clip(0, 255).astype(np.uint8)


def augment_color_jitter(
    img: np.ndarray,
    hue_shift: int = 10,
    sat_range: Tuple[float, float] = (0.8, 1.2),
    val_range: Tuple[float, float] = (0.8, 1.2),
) -> np.ndarray:
    """
    Aplica jitter de color modificando matiz, saturacion y valor en espacio HSV.
    Simula variaciones de iluminacion y color del agua.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)

    # Modificar matiz (Hue)
    hsv[:, :, 0] += random.randint(-hue_shift, hue_shift)
    hsv[:, :, 0] = np.clip(hsv[:, :, 0], 0, 179)

    # Modificar saturacion
    sat_factor = random.uniform(*sat_range)
    hsv[:, :, 1] *= sat_factor
    hsv[:, :, 1] = np.clip(hsv[:, :, 1], 0, 255)

    # Modificar valor (brillo)
    val_factor = random.uniform(*val_range)
    hsv[:, :, 2] *= val_factor
    hsv[:, :, 2] = np.clip(hsv[:, :, 2], 0, 255)

    result = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    return result


def apply_augmentations(img: np.ndarray, num_augmented: int = 3) -> List[np.ndarray]:
    """
    Genera multiples versiones aumentadas de una imagen.
    Cada version aplica un subconjunto aleatorio de transformaciones.
    """
    augmented_images = []

    for _ in range(num_augmented):
        aug_img = img.copy()

        # Aplicar cada transformacion con probabilidad 0.5
        if random.random() > 0.5:
            aug_img = augment_horizontal_flip(aug_img)

        if random.random() > 0.5:
            aug_img = augment_rotation(aug_img)

        if random.random() > 0.5:
            aug_img = augment_brightness(aug_img)

        if random.random() > 0.5:
            aug_img = augment_color_jitter(aug_img)

        augmented_images.append(aug_img)

    return augmented_images


def group_key_for(path: Path) -> str:
    """
    Derive the identity group a source image belongs to.

    Images of the same physical fish must never be split across train/val/test:
    the model would then be evaluated on an individual it memorised, inflating
    accuracy. Filenames in this dataset follow ``<clip>_kf_<frame>.<ext>`` (key
    frames extracted from one recording), so the portion before ``_kf_`` — or the
    stem when that marker is absent — identifies the source clip.

    Args:
        path: Source image path.

    Returns:
        A stable grouping key.
    """
    stem = path.stem
    marker = "_kf_"
    if marker in stem:
        return stem.split(marker, 1)[0]
    # Fall back to stripping a trailing frame index, e.g. "fish12_003" → "fish12".
    parts = stem.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return parts[0]
    return stem


def split_dataset(
    files: List[Path],
    train_ratio: float = TRAIN_RATIO,
    val_ratio: float = VAL_RATIO,
    group_by_identity: bool = True,
) -> Tuple[List[Path], List[Path], List[Path]]:
    """
    Split files into train/val/test sets.

    By default the split is **grouped**: every image sharing a
    :func:`group_key_for` key lands in the same set. A plain per-image shuffle
    leaks identity between splits, and the augmentation step amplifies it by
    placing derived copies of a validation image into training.

    Args:
        files: Source images for one class.
        train_ratio: Fraction of groups assigned to train.
        val_ratio: Fraction of groups assigned to validation.
        group_by_identity: Set False only for object-detection datasets, where
            the label is a box rather than an individual.

    Returns:
        Tuple of (train, val, test) file lists.
    """
    if not files:
        return [], [], []

    if not group_by_identity:
        shuffled = list(files)
        random.shuffle(shuffled)
        n = len(shuffled)
        train_end = int(n * train_ratio)
        val_end = int(n * (train_ratio + val_ratio))
        return shuffled[:train_end], shuffled[train_end:val_end], shuffled[val_end:]

    groups: dict[str, List[Path]] = {}
    for path in files:
        groups.setdefault(group_key_for(path), []).append(path)

    # Sort first so the shuffle is reproducible for a given seed regardless of
    # the order the filesystem returned the entries in.
    group_keys = sorted(groups)
    random.shuffle(group_keys)

    n_groups = len(group_keys)
    train_end = int(n_groups * train_ratio)
    val_end = int(n_groups * (train_ratio + val_ratio))

    # With very few groups, guarantee train is non-empty rather than silently
    # producing an empty training set.
    if n_groups >= 3:
        train_end = max(1, train_end)
        val_end = max(train_end + 1, val_end)

    def collect(keys: List[str]) -> List[Path]:
        return [path for key in keys for path in groups[key]]

    train_files = collect(group_keys[:train_end])
    val_files = collect(group_keys[train_end:val_end])
    test_files = collect(group_keys[val_end:])

    logger.info(
        "Grouped split: %d groups → train=%d val=%d test=%d images "
        "(no identity appears in more than one set)",
        n_groups,
        len(train_files),
        len(val_files),
        len(test_files),
    )
    return train_files, val_files, test_files


def get_image_files(directory: Path) -> List[Path]:
    """Obtiene todos los archivos de imagen validos en un directorio."""
    files = []
    for f in directory.iterdir():
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(f)
    return sorted(files)


def save_image(img: np.ndarray, path: Path, quality: int = 95) -> None:
    """Guarda una imagen en disco con la calidad especificada."""
    path.parent.mkdir(parents=True, exist_ok=True)
    params = [cv2.IMWRITE_JPEG_QUALITY, quality]
    cv2.imwrite(str(path), img, params)


def process_class(
    class_dir: Path,
    output_base: Path,
    class_name: str,
    augment: bool = True,
    num_augmented: int = 3,
) -> Dict[str, int]:
    """
    Procesa todas las imagenes de una clase (fish_id):
    1. Divide en train/val/test
    2. Redimensiona todas
    3. Aplica aumento de datos solo al conjunto train
    4. Guarda en la estructura de salida
    """
    image_files = get_image_files(class_dir)

    if not image_files:
        logger.warning("No se encontraron imagenes en: %s", class_dir)
        return {"train": 0, "val": 0, "test": 0}

    # Dividir en conjuntos
    train_files, val_files, test_files = split_dataset(image_files)

    stats = {"train": 0, "val": 0, "test": 0}

    # Procesar conjunto de entrenamiento (con aumento de datos)
    for i, file_path in enumerate(train_files):
        try:
            img = load_image(file_path)
            img = resize_image(img)

            # Guardar imagen original
            out_path = output_base / "train" / class_name / f"img_{i:04d}_orig.jpg"
            save_image(img, out_path)
            stats["train"] += 1

            # Generar versiones aumentadas (solo para train)
            if augment:
                aug_images = apply_augmentations(img, num_augmented)
                for j, aug_img in enumerate(aug_images):
                    aug_path = output_base / "train" / class_name / f"img_{i:04d}_aug{j:02d}.jpg"
                    save_image(aug_img, aug_path)
                    stats["train"] += 1

        except Exception as e:
            logger.warning("Error procesando %s: %s", file_path, e)

    # Procesar conjunto de validacion (sin aumento)
    for i, file_path in enumerate(val_files):
        try:
            img = load_image(file_path)
            img = resize_image(img)
            out_path = output_base / "val" / class_name / f"img_{i:04d}.jpg"
            save_image(img, out_path)
            stats["val"] += 1
        except Exception as e:
            logger.warning("Error procesando %s: %s", file_path, e)

    # Procesar conjunto de prueba (sin aumento)
    for i, file_path in enumerate(test_files):
        try:
            img = load_image(file_path)
            img = resize_image(img)
            out_path = output_base / "test" / class_name / f"img_{i:04d}.jpg"
            save_image(img, out_path)
            stats["test"] += 1
        except Exception as e:
            logger.warning("Error procesando %s: %s", file_path, e)

    return stats


def generate_metadata(
    output_base: Path,
    class_names: List[str],
    stats: Dict[str, Dict[str, int]],
) -> None:
    """
    Genera el archivo metadata.json con:
    - Mapeo de clases (fish_id -> indice numerico)
    - Estadisticas de cada conjunto
    - Parametros de preprocesamiento utilizados
    """
    # Crear mapeo de clases ordenado alfabeticamente
    sorted_classes = sorted(class_names)
    class_to_idx = {name: idx for idx, name in enumerate(sorted_classes)}
    idx_to_class = {idx: name for name, idx in class_to_idx.items()}

    metadata = {
        "num_classes": len(sorted_classes),
        "class_to_idx": class_to_idx,
        "idx_to_class": idx_to_class,
        "classes": sorted_classes,
        "image_size": list(TARGET_SIZE),
        "normalization": {
            "mean": [0.485, 0.456, 0.406],  # ImageNet mean (RGB)
            "std": [0.229, 0.224, 0.225],    # ImageNet std (RGB)
        },
        "split_ratios": {
            "train": TRAIN_RATIO,
            "val": VAL_RATIO,
            "test": TEST_RATIO,
        },
        "stats_per_class": stats,
        "total_images": {
            "train": sum(s["train"] for s in stats.values()),
            "val": sum(s["val"] for s in stats.values()),
            "test": sum(s["test"] for s in stats.values()),
        },
    }

    metadata_path = output_base / "metadata.json"
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    logger.info("Metadata guardado en: %s", metadata_path)


def preprocess_dataset(
    input_dir: Path,
    output_dir: Path,
    augment: bool = True,
    num_augmented: int = 3,
    seed: int = 42,
) -> None:
    """
    Pipeline principal de preprocesamiento.
    Procesa todas las clases encontradas en el directorio de entrada.
    """
    # Fijar semilla para reproducibilidad
    random.seed(seed)
    np.random.seed(seed)

    # Verificar que el directorio de entrada existe
    if not input_dir.exists():
        logger.error("Directorio de entrada no existe: %s", input_dir)
        sys.exit(1)

    # Encontrar todas las clases (subdirectorios)
    class_dirs = sorted([d for d in input_dir.iterdir() if d.is_dir()])

    if not class_dirs:
        logger.error("No se encontraron subdirectorios (clases) en: %s", input_dir)
        sys.exit(1)

    logger.info("Clases encontradas: %d", len(class_dirs))
    for d in class_dirs:
        logger.info("  - %s (%d imagenes)", d.name, len(get_image_files(d)))

    # Limpiar directorio de salida
    if output_dir.exists():
        logger.warning("El directorio de salida ya existe. Se sobreescribiran los datos.")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Procesar cada clase
    all_stats = {}
    class_names = []

    for class_dir in class_dirs:
        class_name = class_dir.name
        class_names.append(class_name)
        logger.info("Procesando clase: %s", class_name)

        stats = process_class(
            class_dir=class_dir,
            output_base=output_dir,
            class_name=class_name,
            augment=augment,
            num_augmented=num_augmented,
        )
        all_stats[class_name] = stats
        logger.info(
            "  -> train: %d, val: %d, test: %d",
            stats["train"], stats["val"], stats["test"]
        )

    # Generar metadata
    generate_metadata(output_dir, class_names, all_stats)

    # Resumen final
    total_train = sum(s["train"] for s in all_stats.values())
    total_val = sum(s["val"] for s in all_stats.values())
    total_test = sum(s["test"] for s in all_stats.values())

    logger.info("=" * 50)
    logger.info("RESUMEN DE PREPROCESAMIENTO")
    logger.info("=" * 50)
    logger.info("  Clases:              %d", len(class_names))
    logger.info("  Imagenes train:      %d", total_train)
    logger.info("  Imagenes validacion: %d", total_val)
    logger.info("  Imagenes test:       %d", total_test)
    logger.info("  Total:               %d", total_train + total_val + total_test)
    logger.info("  Tamano de imagen:    %dx%d", TARGET_SIZE[0], TARGET_SIZE[1])
    logger.info("  Aumento de datos:    %s", "Si" if augment else "No")
    logger.info("=" * 50)


def parse_args() -> argparse.Namespace:
    """Parsea los argumentos de linea de comandos."""
    parser = argparse.ArgumentParser(
        description="Preprocesa imagenes de peces para entrenamiento del modelo.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplo de uso:
  python preprocess.py --input-dir data/raw --output-dir data/processed
  python preprocess.py --input-dir data/raw --output-dir data/processed --no-augment
  python preprocess.py --input-dir data/raw --output-dir data/processed --num-augmented 5
        """,
    )
    parser.add_argument(
        "--input-dir",
        type=str,
        default="data/raw",
        help="Directorio con imagenes crudas organizadas por clase (default: data/raw)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/processed",
        help="Directorio de salida para datos procesados (default: data/processed)",
    )
    parser.add_argument(
        "--no-augment",
        action="store_true",
        help="Deshabilitar aumento de datos",
    )
    parser.add_argument(
        "--num-augmented",
        type=int,
        default=3,
        help="Numero de versiones aumentadas por imagen (default: 3)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Semilla aleatoria para reproducibilidad (default: 42)",
    )
    parser.add_argument(
        "--image-size",
        type=int,
        default=224,
        help="Tamano de imagen de salida en pixeles (default: 224)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Habilitar logging detallado (DEBUG)",
    )
    return parser.parse_args()


def main() -> None:
    """Punto de entrada principal del script."""
    args = parse_args()

    # Configurar nivel de logging
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Actualizar tamano de imagen si se especifico
    global TARGET_SIZE
    TARGET_SIZE = (args.image_size, args.image_size)

    logger.info("Iniciando preprocesamiento de datos de FishDex")
    logger.info("  Entrada:       %s", args.input_dir)
    logger.info("  Salida:        %s", args.output_dir)
    logger.info("  Tamano imagen: %dx%d", TARGET_SIZE[0], TARGET_SIZE[1])
    logger.info("  Aumento datos: %s", "No" if args.no_augment else f"Si ({args.num_augmented} por imagen)")
    logger.info("  Semilla:       %d", args.seed)

    # Ejecutar preprocesamiento
    preprocess_dataset(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        augment=not args.no_augment,
        num_augmented=args.num_augmented,
        seed=args.seed,
    )

    logger.info("Preprocesamiento completado.")


if __name__ == "__main__":
    main()
