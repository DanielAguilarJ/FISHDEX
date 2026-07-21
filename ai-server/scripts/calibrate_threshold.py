"""
FishDex ReID -- Calibracion del threshold optimo
=================================================
Mide la similitud entre tomas del mismo pez y de peces distintos
para encontrar el threshold optimo de separacion.

Acepta IMAGENES y/o VIDEOS en cada carpeta de toma.
Si hay un video (mp4, mov, avi, mkv...) se extraen frames automaticamente.

Estructura de datos esperada (OPCION A - subcarpetas):
    calib_data/
        pez_01_toma_a/   <- carpeta con imagenes *.jpg o un video *.mp4
        pez_01_toma_b/   <- segunda toma del mismo pez
        pez_02_toma_a/
        pez_02_toma_b/
        ...

ATAJO (OPCION B - archivos sueltos directamente en calib_data/):
    calib_data/
        pez_01_toma_a.mp4
        pez_01_toma_b.mp4
        pez_02_toma_a.mp4
        pez_02_toma_b.mp4
        ...

Los nombres que empiezan con el mismo "pez_XX" se consideran
el MISMO individuo. Ajusta get_fish_id() si usas otra convencion.

Uso:
    cd ai-server
    python scripts/calibrate_threshold.py

    # Con carpeta personalizada:
    python scripts/calibrate_threshold.py --data mi_carpeta/

    # Controlar cuantos frames se extraen de cada video:
    python scripts/calibrate_threshold.py --max-frames 20
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

# Asegurarse de que el path al paquete app este disponible
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.reid_embedding_service import get_reid_embedding_service

# Extensiones soportadas
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp", ".temp"}



def get_fish_id(name: str) -> str:
    """
    Extrae el ID del individuo a partir del nombre de carpeta o archivo.
    Asume que el prefijo "pez_XX" identifica al individuo.

    Ejemplos:
        "pez_01_toma_a"  -> "pez_01"
        "fish_05_catch_2" -> "fish_05"
    """
    parts = name.split("_")
    if len(parts) >= 2:
        return "_".join(parts[:2])
    return name


def extract_frames_from_video(video_path: Path, max_frames: int = 15) -> list:
    """
    Extrae hasta max_frames frames distribuidos uniformemente de un video.
    Igual que hace la app al grabar un pez.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        print(f"    [WARN] No se pudo abrir el video: {video_path.name}")
        return []

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return []

    # Seleccionar indices uniformemente distribuidos
    n = min(max_frames, total)
    indices = sorted(set(
        int(round(i * (total - 1) / max(n - 1, 1)))
        for i in range(n)
    ))

    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if ret and frame is not None:
            frames.append(frame)

    cap.release()
    return frames


def load_from_folder(d: Path, max_frames: int = 15) -> list:
    """
    Carga frames de una subcarpeta.
    Prioriza videos; si no hay, carga imagenes.
    """
    frames = []

    video_files = sorted(p for p in d.iterdir() if p.suffix.lower() in VIDEO_EXTS)
    if video_files:
        for vf in video_files:
            vframes = extract_frames_from_video(vf, max_frames=max_frames)
            frames.extend(vframes)
            print(f"      video '{vf.name}' -> {len(vframes)} frames")
        return frames

    # Sin videos: buscar imagenes
    for p in sorted(d.iterdir()):
        if p.suffix.lower() in IMAGE_EXTS:
            img = cv2.imread(str(p))
            if img is not None:
                frames.append(img)
    return frames


def load_from_file(f: Path, max_frames: int = 15) -> list:
    """Carga frames de un archivo suelto (video o imagen)."""
    ext = f.suffix.lower()
    if ext in VIDEO_EXTS:
        return extract_frames_from_video(f, max_frames=max_frames)
    elif ext in IMAGE_EXTS:
        img = cv2.imread(str(f))
        return [img] if img is not None else []
    return []


def main():
    parser = argparse.ArgumentParser(description="Calibra el threshold ReID optimo")
    parser.add_argument(
        "--data",
        default="calib_data",
        help="Carpeta con subcarpetas o archivos pez_XX_toma_N (default: calib_data/)",
    )
    parser.add_argument(
        "--max-frames",
        type=int,
        default=15,
        help="Maximo de frames a extraer de cada video (default: 15)",
    )
    args = parser.parse_args()

    calib_dir = Path(args.data)
    if not calib_dir.exists():
        print(f"\nERROR: No existe la carpeta '{calib_dir.resolve()}'")
        print("Crea la carpeta con esta estructura:")
        print("  calib_data/")
        print("    pez_01_toma_a.mp4   <- video del pez 1, primera toma")
        print("    pez_01_toma_b.mp4   <- video del pez 1, segunda toma")
        print("    pez_02_toma_a.mp4")
        print("    ...")
        sys.exit(1)

    print("=" * 60)
    print("FishDex ReID -- Calibracion de Threshold")
    print("=" * 60)
    print(f"Carpeta de datos : {calib_dir.resolve()}")
    print(f"Max frames/video : {args.max_frames}")
    print("Cargando modelo ReID...")

    reid = get_reid_embedding_service()
    if not reid.is_loaded:
        print("\nERROR: ReIDEmbeddingService no pudo cargar el modelo.")
        print("Revisa los logs del servidor para mas detalles.")
        sys.exit(1)

    print("OK Modelo cargado\n")
    print(f"Escaneando '{calib_dir}'...\n")

    # Recopilar entradas: (nombre_toma, frames)
    entries: list[tuple[str, list]] = []

    children = sorted(calib_dir.iterdir())

    # A) Subcarpetas
    for d in children:
        if not d.is_dir():
            continue
        print(f"  [Carpeta] {d.name}")
        frames = load_from_folder(d, max_frames=args.max_frames)
        entries.append((d.name, frames))

    # B) Archivos sueltos directamente en calib_data/
    loose = [
        f for f in children
        if f.is_file() and f.suffix.lower() in (VIDEO_EXTS | IMAGE_EXTS)
    ]
    if loose:
        print(f"\n  Archivos sueltos en '{calib_dir.name}/':")
    for f in loose:
        stem = f.stem  # "pez_01_toma_a"
        print(f"  [Archivo] {f.name}")
        frames = load_from_file(f, max_frames=args.max_frames)
        entries.append((stem, frames))

    print()

    # Calcular prototipos
    protos: dict = {}
    folder_to_individual: dict = {}

    for name, frames in entries:
        if not frames:
            print(f"  [SKIP]  {name} -- sin frames validos")
            continue
        proto = reid.extract_prototype(frames)
        protos[name] = proto
        individual_id = get_fish_id(name)
        folder_to_individual[name] = individual_id
        print(f"  [OK]    {name} ({len(frames)} frames) -> individuo '{individual_id}'")

    if len(protos) < 2:
        print("\nERROR: Necesitas al menos 2 tomas para comparar.")
        sys.exit(1)

    names = list(protos.keys())
    same_scores: list = []
    diff_scores: list = []

    print(f"\n{'=' * 60}")
    print("MATRIZ DE SIMILITUD")
    print(f"{'=' * 60}")
    print(f"{'Par':62}  {'Score':6}  {'Tipo':8}")
    print("-" * 80)

    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            sim = float(np.dot(protos[names[i]], protos[names[j]]))
            same = folder_to_individual[names[i]] == folder_to_individual[names[j]]
            label = "MISMO" if same else "DISTINTO"
            pair_str = f"{names[i]} vs {names[j]}"
            print(f"  {pair_str[:60]:60}  {sim:.4f}  {label}")
            if same:
                same_scores.append(sim)
            else:
                diff_scores.append(sim)

    print(f"\n{'=' * 60}")
    print("RESUMEN")
    print(f"{'=' * 60}")

    if same_scores:
        print(
            f"  MISMO pez    -> min={min(same_scores):.4f}  "
            f"max={max(same_scores):.4f}  "
            f"media={np.mean(same_scores):.4f}  "
            f"(N={len(same_scores)} pares)"
        )
    else:
        print("  MISMO pez    -> sin pares (necesitas >=2 tomas del mismo individuo)")

    if diff_scores:
        print(
            f"  DISTINTO pez -> min={min(diff_scores):.4f}  "
            f"max={max(diff_scores):.4f}  "
            f"media={np.mean(diff_scores):.4f}  "
            f"(N={len(diff_scores)} pares)"
        )
    else:
        print("  DISTINTO pez -> sin pares (necesitas >=2 individuos distintos)")

    print()

    if same_scores and diff_scores:
        lo = min(same_scores)   # par 'mismo' mas dificil de separar
        hi = max(diff_scores)   # par 'distinto' mas confuso

        if lo > hi:
            optimo = round((lo + hi) / 2, 3)
            margen_seguridad = round((lo - hi) / 2, 3)
            print("OK SEPARACION LIMPIA")
            print(f"   mismo_min={lo:.4f} > distinto_max={hi:.4f}")
            print(f"   Margen de seguridad: {margen_seguridad:.4f}")
            print()
            print(f"   Threshold optimo sugerido: {optimo}")
            print(f"   -> Anade a .env:")
            print(f"     FISHDEX_REID_SIMILARITY_THRESHOLD={optimo}")
        else:
            gap = round(lo - hi, 4)
            print("AVISO: SOLAPAMIENTO DETECTADO")
            print(f"   mismo_min={lo:.4f} <= distinto_max={hi:.4f}  (gap={gap:.4f})")
            print()
            print("   El modelo NO separa bien estos individuos.")
            print("   Con solapamiento, ningun threshold garantiza resultados correctos.")
            print()
            print("   Causas mas probables (en orden):")
            print("   1. Calidad insuficiente de los datos de calibracion.")
            print("      -> Usa VIDEOS grabados con la app (15+ frames por toma).")
            print("      -> Asegurate de que el cuerpo del pez se vea completo.")
            print("   2. El modelo ReID se cargo parcialmente.")
            print("      Busca: 'FishEncoder loaded: X/Y keys | missing=Z shape_mismatch=W'")
            print("   3. Los peces son muy similares visualmente entre si.")
            print("   4. FISHDEX_REID_MODEL_NAME no coincide con el backbone de entrenamiento.")
    elif same_scores:
        print("INFO: Solo tienes pares del MISMO individuo.")
        print("   Anade videos/carpetas de otros peces para ver la separacion.")
    elif diff_scores:
        print("INFO: Solo tienes pares de individuos DISTINTOS.")
        print("   Anade >=2 tomas del mismo pez para ver la cohesion intra-clase.")


if __name__ == "__main__":
    main()
