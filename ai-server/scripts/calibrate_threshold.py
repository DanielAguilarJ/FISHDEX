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

Uso:
    cd ai-server
    python scripts/calibrate_threshold.py

    # Con carpeta personalizada:
    python scripts/calibrate_threshold.py --data mi_carpeta/

    # Controlar cuantos frames se extraen de cada video:
    python scripts/calibrate_threshold.py --max-frames 20

    # Nueva calibracion por episodios:
    python scripts/calibrate_threshold.py \
      --manifest eval_data/manifest.json \
      [--config A|B|C] \
      [--model-version VERSION] \
      [--output-json calibration/VERSION.json] \
      [--use-rois | --run-detector] \
      [--far-target 0.001] \
      [--cal-split 0.7] \
      [--min-identities 10] \
      [--min-sessions 3]
"""
import argparse
import sys
import json
import datetime
from pathlib import Path
from collections import defaultdict
import random
from PIL import Image

import cv2
import numpy as np
import torch

# Asegurarse de que el path al paquete app este disponible
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.reid_embedding_service import get_reid_embedding_service
from app.services.fish_encoder_model import load_model_for_infer, build_eval_transform
from app.services.identity_scoring_service import score_candidates, SupportMetadata
from app.config import settings

# Extensiones soportadas
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp", ".temp"}

CONFIGS = {
    "A": {"x_start": 0.20, "x_end": 0.80, "y_start": 0.05, "y_end": 0.55},
    "B": {"x_start": 0.15, "x_end": 0.85, "y_start": 0.00, "y_end": 0.60},
    "C": {"x_start": 0.333, "x_end": 0.667, "y_start": 0.05, "y_end": 0.35},
}


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

def evaluate_episode(gallery_dict, support_meta_dict, queries_list):
    """
    Calculates results for known matches and known non-matches using production score_candidates().
    """
    same_scores, diff_scores = [], []
    same_margins, diff_margins = [], []
    same_agree, diff_agree = [], []
    
    for q_item in queries_list:
        q_emb = q_item["embedding"]
        if q_emb.ndim == 1:
            q_emb = q_emb[np.newaxis, :]
            
        res = score_candidates(
            query_embeddings=q_emb,
            candidate_gallery=gallery_dict,
            candidate_support_metadata=support_meta_dict,
        )
        
        if res.top1_fish_id is None:
            continue
            
        if res.top1_fish_id == q_item["fish_id"]:
            same_scores.append(res.top1_score)
            same_margins.append(res.margin)
            same_agree.append(res.agreement_ratio)
        else:
            diff_scores.append(res.top1_score)
            diff_margins.append(res.margin)
            diff_agree.append(res.agreement_ratio)
            
    return same_scores, same_margins, same_agree, diff_scores, diff_margins, diff_agree


def calibrate_episode_based(args):
    print("=" * 60)
    print("FishDex ReID -- Calibracion por episodios")
    print("=" * 60)
    
    if settings.reid_fingerprint_crop_enabled:
        if not args.use_rois and not args.run_detector:
            print("ERROR: Fingerprint está activado (reid_fingerprint_crop_enabled=True),")
            print("       debes especificar --use-rois o --run-detector.")
            sys.exit(1)
        if args.run_detector:
            print("ERROR: --run-detector no esta implementado todavia.")
            sys.exit(1)

    with open(args.manifest, 'r') as f:
        manifest = json.load(f)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = load_model_for_infer(
        model_path=settings.reid_model_path,
        model_name=settings.reid_model_name,
        out_dim=settings.reid_embedding_dim,
        device=device,
    )
    
    config_bounds = {}
    if args.config:
        config_bounds = CONFIGS[args.config]

    transform = build_eval_transform(
        img_size=settings.reid_img_size, 
        use_fingerprint_crop=settings.reid_fingerprint_crop_enabled, 
        **config_bounds
    )
    
    print("Cargando y procesando imagenes del manifest...")
    
    species_data = defaultdict(lambda: defaultdict(list))
    
    for item in manifest:
        species_slug = item.get("species_slug", "unknown")
        individual_id = item.get("fish_id") or item.get("individual_id")
        session_id = item.get("session_id")
        
        image_path = item.get("path") or item.get("image_path")
        full_path = Path(image_path)
        if not full_path.exists():
            print(f"File not found: {full_path}")
            continue
            
        img = cv2.imread(str(full_path))
        if img is None:
            continue
            
        img_pil = Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        tensor = transform(img_pil).unsqueeze(0).to(device)
        
        with torch.no_grad():
            emb = model.forward_embed_bn(tensor).cpu().numpy()[0]
        
        species_data[species_slug][individual_id].append({
            "session_id": session_id,
            "embedding": emb
        })

    json_output = {
        "schema_version": "1",
        "model_version": args.model_version or "unknown",
        "dataset_version": "unknown",
        "generated_at": datetime.datetime.now().isoformat(),
        "validated": False,
        "validation_far": args.far_target,
        "global": {
            "review_threshold": 0.6,
            "auto_match_threshold": 0.8,
            "single_candidate_threshold": 0.65,
            "min_margin": 0.05,
            "min_agreement": 0.5
        },
        "species": {},
        "dataset_stats": {
            "identities": 0,
            "avg_sessions": 0,
            "pairs_same": 0,
            "pairs_diff": 0,
            "calibration_far": 1.0,
            "test_far": 1.0,
            "calibration_recall": 0.0,
            "test_recall": 0.0
        }
    }

    total_identities = 0
    total_sessions = 0
    
    for species, individuals in species_data.items():
        valid_indivs = {k: v for k, v in individuals.items() if len(v) >= args.min_sessions}
        
        if len(valid_indivs) < args.min_identities:
            print(f"Skipping species {species}: only {len(valid_indivs)} valid individuals (needs {args.min_identities})")
            continue
            
        total_identities += len(valid_indivs)
        total_sessions += sum(len(v) for v in valid_indivs.values())
            
        indiv_ids = list(valid_indivs.keys())
        random.shuffle(indiv_ids)
        split_idx = int(len(indiv_ids) * args.cal_split)
        
        cal_ids = indiv_ids[:split_idx]
        test_ids = indiv_ids[split_idx:]
        
        def build_episodes(ids):
            gal_dict = {}
            gal_meta = {}
            queries = []
            for iid in ids:
                sessions = valid_indivs[iid]
                gal_embs = [sessions[0]["embedding"]]
                gal_dict[iid] = np.array(gal_embs)
                gal_meta[iid] = [SupportMetadata(sighting_id=sessions[0]["session_id"])]
                for s in sessions[1:]:
                    queries.append({
                        "fish_id": iid,
                        "session_id": s["session_id"],
                        "embedding": s["embedding"][np.newaxis, :] if s["embedding"].ndim == 1 else s["embedding"],
                    })
            return gal_dict, gal_meta, queries

        cal_gal_dict, cal_gal_meta, cal_queries = build_episodes(cal_ids)
        test_gal_dict, test_gal_meta, test_queries = build_episodes(test_ids)
        
        (cal_same_sc, cal_same_ma, cal_same_ag,
         cal_diff_sc, cal_diff_ma, cal_diff_ag) = evaluate_episode(cal_gal_dict, cal_gal_meta, cal_queries)
         
        (test_same_sc, test_same_ma, test_same_ag,
         test_diff_sc, test_diff_ma, test_diff_ag) = evaluate_episode(test_gal_dict, test_gal_meta, test_queries)
         
        json_output["dataset_stats"]["pairs_same"] += len(cal_same_sc) + len(test_same_sc)
        json_output["dataset_stats"]["pairs_diff"] += len(cal_diff_sc) + len(test_diff_sc)

        best_config = None
        best_recall = -1
        
        print(f"Grid searching for {species} (cal: {len(cal_ids)} indivs)")
        
        for review_thresh in np.arange(0.30, 0.80, 0.02):
            for auto_match_thresh in np.arange(review_thresh + 0.05, 0.95, 0.02):
                for single_thresh in np.arange(review_thresh, auto_match_thresh, 0.02):
                    for min_margin_val in np.arange(0.01, 0.15, 0.01):
                        for min_agree_val in np.arange(0.3, 0.9, 0.1):
                            
                            false_accepts = sum(1 for s, m, a in zip(cal_diff_sc, cal_diff_ma, cal_diff_ag) 
                                                if s >= review_thresh and m >= min_margin_val and a >= min_agree_val)
                            far = false_accepts / max(1, len(cal_diff_sc))
                            
                            if far <= args.far_target:
                                true_accepts = sum(1 for s, m, a in zip(cal_same_sc, cal_same_ma, cal_same_ag) 
                                                   if s >= review_thresh and m >= min_margin_val and a >= min_agree_val)
                                recall = true_accepts / max(1, len(cal_same_sc))
                                
                                if recall > best_recall:
                                    best_recall = recall
                                    best_config = {
                                        "review_threshold": round(float(review_thresh), 3),
                                        "auto_match_threshold": round(float(auto_match_thresh), 3),
                                        "single_candidate_threshold": round(float(single_thresh), 3),
                                        "min_margin": round(float(min_margin_val), 3),
                                        "min_agreement": round(float(min_agree_val), 3),
                                        "calibration_far": far,
                                        "calibration_recall": recall
                                    }

        if best_config:
            rt = best_config["review_threshold"]
            mm = best_config["min_margin"]
            ma = best_config["min_agreement"]
            
            test_fa = sum(1 for s, m, a in zip(test_diff_sc, test_diff_ma, test_diff_ag) 
                          if s >= rt and m >= mm and a >= ma)
            test_far = test_fa / max(1, len(test_diff_sc))
            
            test_ta = sum(1 for s, m, a in zip(test_same_sc, test_same_ma, test_same_ag) 
                          if s >= rt and m >= mm and a >= ma)
            test_recall = test_ta / max(1, len(test_same_sc))
            
            best_config["test_far"] = test_far
            best_config["test_recall"] = test_recall
            
            json_output["global"].update({k: best_config[k] for k in ["review_threshold", "auto_match_threshold", "single_candidate_threshold", "min_margin", "min_agreement"]})
            
            json_output["dataset_stats"]["calibration_far"] = best_config["calibration_far"]
            json_output["dataset_stats"]["test_far"] = test_far
            json_output["dataset_stats"]["calibration_recall"] = best_config["calibration_recall"]
            json_output["dataset_stats"]["test_recall"] = test_recall
            
            if test_far <= args.far_target:
                json_output["validated"] = True
                
            print(f"  Best config for {species}: FAR={test_far:.4f}, Recall={test_recall:.4f}")
        else:
            print(f"  Could not find valid config for {species} under FAR target.")
            json_output["validated"] = False

    if total_identities > 0:
        json_output["dataset_stats"]["identities"] = total_identities
        json_output["dataset_stats"]["avg_sessions"] = total_sessions / total_identities

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, 'w') as f:
            json.dump(json_output, f, indent=2)
        print(f"Saved calibration to {out_path}")


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
    # Nuevos argumentos:
    parser.add_argument("--manifest", type=str, help="Ruta al manifest JSON para calibracion basada en episodios")
    parser.add_argument("--config", type=str, choices=list(CONFIGS.keys()), help="Configuracion de crop A, B o C")
    parser.add_argument("--model-version", type=str, help="Version del modelo a guardar en el json")
    parser.add_argument("--output-json", type=str, help="Ruta de salida del JSON de calibracion")
    parser.add_argument("--use-rois", action="store_true", help="Las imagenes de entrada son ROIs pre-rectificadas")
    parser.add_argument("--run-detector", action="store_true", help="Ejecuta el detector primero (no implementado)")
    parser.add_argument("--far-target", type=float, default=0.001, help="Target False Acceptance Rate")
    parser.add_argument("--cal-split", type=float, default=0.7, help="Proporcion de individuos para calibracion")
    parser.add_argument("--min-identities", type=int, default=10, help="Minimo de individuos necesarios por especie")
    parser.add_argument("--min-sessions", type=int, default=3, help="Minimo de sesiones (tomas) por individuo")

    args = parser.parse_args()

    if args.manifest:
        calibrate_episode_based(args)
        return

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
