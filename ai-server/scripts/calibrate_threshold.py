"""
FishDex ReID -- Calibracion del threshold optimo
=================================================
Mide la similitud entre tomas del mismo pez y de peces distintos
para encontrar el threshold optimo de separacion.

Estructura de datos esperada:
    calib_data/
        pez_01_toma_a/ *.jpg   (frames del pez 1, primera toma)
        pez_01_toma_b/ *.jpg   (frames del pez 1, segunda toma)
        pez_02_toma_a/ *.jpg
        pez_02_toma_b/ *.jpg
        ...

Los nombres de carpeta que empiezan con el mismo "pez_XX" se consideran
el MISMO individuo. Ajusta get_fish_id() si usas otra convencion de nombres.

Uso:
    cd ai-server
    python scripts/calibrate_threshold.py

    # Con carpeta personalizada:
    python scripts/calibrate_threshold.py --data mi_carpeta/
"""
import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

# Asegurarse de que el path al paquete app este disponible
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.reid_embedding_service import get_reid_embedding_service


def get_fish_id(folder_name: str) -> str:
    """
    Extrae el ID del individuo a partir del nombre de carpeta.
    Asume que el prefijo "pez_XX" identifica al individuo.

    Ejemplos:
        "pez_01_toma_a" -> "pez_01"
        "fish_05_catch_2" -> "fish_05"
    """
    parts = folder_name.split("_")
    if len(parts) >= 2:
        return "_".join(parts[:2])
    return folder_name


def load_frames(d: Path) -> list:
    """Cargar todos los frames de una carpeta (jpg, png, bmp)."""
    frames = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp"):
        for p in sorted(d.glob(ext)):
            img = cv2.imread(str(p))
            if img is not None:
                frames.append(img)
    return frames


def main():
    parser = argparse.ArgumentParser(description="Calibra el threshold ReID optimo")
    parser.add_argument(
        "--data",
        default="calib_data",
        help="Carpeta con subcarpetas pez_XX_toma_N/ (default: calib_data/)",
    )
    args = parser.parse_args()

    calib_dir = Path(args.data)
    if not calib_dir.exists():
        print(f"\nERROR: No existe la carpeta '{calib_dir.resolve()}'")
        print("Crea la carpeta con esta estructura:")
        print("  calib_data/")
        print("    pez_01_toma_a/  *.jpg  (frames del pez 1, toma 1)")
        print("    pez_01_toma_b/  *.jpg  (frames del pez 1, toma 2)")
        print("    pez_02_toma_a/  *.jpg")
        print("    ...")
        sys.exit(1)

    print("=" * 60)
    print("FishDex ReID -- Calibracion de Threshold")
    print("=" * 60)
    print("Cargando modelo ReID...")

    reid = get_reid_embedding_service()
    if not reid.is_loaded:
        print("\nERROR: ReIDEmbeddingService no pudo cargar el modelo.")
        print("Revisa los logs del servidor para mas detalles.")
        sys.exit(1)

    print("OK Modelo cargado\n")
    print(f"Escaneando '{calib_dir}'...")

    protos: dict = {}
    folder_to_individual: dict = {}

    for d in sorted(calib_dir.iterdir()):
        if not d.is_dir():
            continue
        frames = load_frames(d)
        if not frames:
            print(f"  [SKIP]  {d.name} -- sin frames validos")
            continue
        proto = reid.extract_prototype(frames)
        protos[d.name] = proto
        individual_id = get_fish_id(d.name)
        folder_to_individual[d.name] = individual_id
        print(f"  [OK]    {d.name} ({len(frames)} frames) -> individuo '{individual_id}'")

    if len(protos) < 2:
        print("\nERROR: Necesitas al menos 2 carpetas con frames para comparar.")
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
            print("   El modelo NO separa bien estos individuos con los parametros actuales.")
            print("   Con solapamiento, ningun threshold garantiza resultados correctos.")
            print()
            print("   Causas mas probables (en orden):")
            print("   1. El modelo ReID se cargo parcialmente (revisa el log del servidor).")
            print("      Busca: 'FishEncoder loaded: X/Y keys | missing=Z shape_mismatch=W'")
            print("   2. Los ROIs de calibracion son inconsistentes (angulos muy distintos).")
            print("   3. FISHDEX_REID_MODEL_NAME no coincide con el backbone de entrenamiento.")
    elif same_scores:
        print("INFO: Solo tienes pares del MISMO individuo.")
        print("   Anade carpetas de otros peces para ver la separacion.")
    elif diff_scores:
        print("INFO: Solo tienes pares de individuos DISTINTOS.")
        print("   Anade >=2 tomas del mismo pez para ver la cohesion intra-clase.")


if __name__ == "__main__":
    main()
