import argparse
import json
import os
import glob
import random
import datetime
import math
import cv2
import numpy as np
import torch
import torch.nn.functional as F
from pathlib import Path
from collections import defaultdict
from PIL import Image
from typing import List, Dict, Optional, Tuple, Any

from app.services.fish_encoder_model import load_model_for_infer, build_eval_transform
from app.services.identity_scoring_service import score_candidates, SupportMetadata, ScoringResult
from app.config import settings

CONFIGS = {
    "A": {"x_start": 0.20, "x_end": 0.80, "y_start": 0.05, "y_end": 0.55, "id": "fp_x020_080_y005_055"},
    "B": {"x_start": 0.15, "x_end": 0.85, "y_start": 0.00, "y_end": 0.60, "id": "fp_x015_085_y000_060"},
    "C": {"x_start": 0.333, "x_end": 0.667, "y_start": 0.05, "y_end": 0.35, "id": "fp_x033_067_y005_035"}
}

def auto_discover_manifest(data_dir: str) -> List[Dict]:
    manifest = []
    base_path = Path(data_dir)
    # expected format: eval_data/<species_slug>/<fish_id>/<session_id>/roi_*.jpg
    for roi_file in base_path.rglob("roi_*.jpg"):
        rel_path = roi_file.relative_to(base_path)
        parts = rel_path.parts
        if len(parts) >= 4:
            species_slug = parts[0]
            fish_id = parts[1]
            session_id = parts[2]
            manifest.append({
                "path": str(roi_file),
                "species_slug": species_slug,
                "fish_id": fish_id,
                "session_id": session_id,
                "capture_id": session_id  # using session_id as capture_id if not present
            })
    return manifest

def extract_embeddings(manifest: List[Dict], config_name: str, config: Dict, model, device: torch.device) -> Dict[str, np.ndarray]:
    # Determine img_size from settings, default to (256, 128) if not found
    img_size = getattr(settings, 'reid_img_size', 128)
    
    transform = build_eval_transform(
        img_size=img_size,
        use_fingerprint_crop=True,
        x_start=config["x_start"],
        x_end=config["x_end"],
        y_start=config["y_start"],
        y_end=config["y_end"]
    )
    
    embeddings = {}
    model.eval()
    
    with torch.no_grad():
        for item in manifest:
            img_path = item["path"]
            if not os.path.exists(img_path):
                continue
                
            img_bgr = cv2.imread(img_path)
            if img_bgr is None:
                continue
                
            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(img_rgb)
            
            tensor = transform(pil_img).unsqueeze(0).to(device)
            
            emb = model.forward_embed_bn(tensor)
            tensor_flip = torch.flip(tensor, dims=[-1])
            emb_flip = model.forward_embed_bn(tensor_flip)
            
            emb_combined = F.normalize(emb + emb_flip, dim=-1)
            embeddings[img_path] = emb_combined.cpu().numpy()[0]
            
    return embeddings

def evaluate_species(species_slug: str, species_manifest: List[Dict], embeddings: Dict[str, np.ndarray], open_set_fraction: float) -> Dict:
    # Group data: fish_id -> session_id -> list of image paths
    fish_data = defaultdict(lambda: defaultdict(list))
    for item in species_manifest:
        if item["path"] in embeddings:
            fish_data[item["fish_id"]][item["session_id"]].append(item["path"])
            
    # Filter fish with >= 2 sessions
    valid_fish_ids = [fid for fid, sessions in fish_data.items() if len(sessions) >= 2]
    
    if len(valid_fish_ids) < 2:
        return {"error": "Not enough fish with >= 2 sessions"}
        
    random.shuffle(valid_fish_ids)
    num_unknown = max(1, int(len(valid_fish_ids) * open_set_fraction)) if len(valid_fish_ids) >= 4 else 0
    if len(valid_fish_ids) - num_unknown < 2:
        num_unknown = 0 # Fallback if too few
        
    unknown_fish_ids = set(valid_fish_ids[:num_unknown])
    known_fish_ids = set(valid_fish_ids[num_unknown:])
    
    same_scores = []
    same_margins = []
    same_agreements = []
    
    diff_scores = []
    
    correct_id = 0
    wrong_id = 0
    
    false_accepts_count = 0
    total_unknown_queries = 0
    
    # Evaluate closed-set (Known fish)
    for q_fish in known_fish_ids:
        for q_session, q_paths in fish_data[q_fish].items():
            query_embs = np.array([embeddings[p] for p in q_paths])
            
            # Build gallery
            gallery = {}
            support_meta = {}
            for gal_fish in known_fish_ids:
                gal_embs = []
                gal_metas = []
                for g_session, g_paths in fish_data[gal_fish].items():
                    if gal_fish == q_fish and g_session == q_session:
                        continue # leave-one-session-out
                    
                    for p in g_paths:
                        gal_embs.append(embeddings[p])
                        gal_metas.append(SupportMetadata(
                            capture_id=g_session, # Using session_id as capture_id for support
                            frame_index=0,
                            bbox=[0,0,0,0],
                            quality_score=1.0
                        ))
                if gal_embs:
                    gallery[gal_fish] = np.array(gal_embs)
                    support_meta[gal_fish] = gal_metas
                    
            if not gallery or q_fish not in gallery:
                continue # Cannot evaluate this query
                
            res = score_candidates(
                query_embeddings=query_embs,
                candidate_gallery=gallery,
                candidate_support_metadata=support_meta,
                max_support_per_identity=8
            )
            
            if res.top1_fish_id == q_fish:
                correct_id += 1
                same_scores.append(res.top1_score)
                same_margins.append(res.margin)
                same_agreements.append(res.agreement_ratio)
            else:
                wrong_id += 1
                # The top match was someone else
                diff_scores.append(res.top1_score)

    # Evaluate open-set (Unknown fish)
    for q_fish in unknown_fish_ids:
        for q_session, q_paths in fish_data[q_fish].items():
            query_embs = np.array([embeddings[p] for p in q_paths])
            
            # Build gallery (all known fish)
            gallery = {}
            support_meta = {}
            for gal_fish in known_fish_ids:
                gal_embs = []
                gal_metas = []
                for g_session, g_paths in fish_data[gal_fish].items():
                    for p in g_paths:
                        gal_embs.append(embeddings[p])
                        gal_metas.append(SupportMetadata(
                            capture_id=g_session,
                            frame_index=0,
                            bbox=[0,0,0,0],
                            quality_score=1.0
                        ))
                if gal_embs:
                    gallery[gal_fish] = np.array(gal_embs)
                    support_meta[gal_fish] = gal_metas
                    
            if not gallery:
                continue
                
            res = score_candidates(
                query_embeddings=query_embs,
                candidate_gallery=gallery,
                candidate_support_metadata=support_meta,
                max_support_per_identity=8
            )
            
            total_unknown_queries += 1
            diff_scores.append(res.top1_score)
            
            # If threshold is not fixed, we just record distributions
            # We will compute FAR later using a suggested threshold
    
    total_closed = correct_id + wrong_id
    accuracy = correct_id / total_closed if total_closed > 0 else 0.0
    
    def get_percentiles(arr):
        if not arr:
            return {"10": 0, "25": 0, "50": 0, "75": 0, "90": 0}
        return {
            "10": float(np.percentile(arr, 10)),
            "25": float(np.percentile(arr, 25)),
            "50": float(np.percentile(arr, 50)),
            "75": float(np.percentile(arr, 75)),
            "90": float(np.percentile(arr, 90))
        }
        
    same_scores_p = get_percentiles(same_scores)
    margin_p = get_percentiles(same_margins)
    agreement_p = get_percentiles(same_agreements)
    
    min_same = min(same_scores) if same_scores else 0.0
    max_diff = max(diff_scores) if diff_scores else 0.0
    
    clean_separation = min_same > max_diff
    
    # Suggest threshold: halfway between max_diff and min_same if clean, 
    # or the 95th percentile of diff_scores if not clean
    if clean_separation:
        suggested_threshold = (min_same + max_diff) / 2
    else:
        suggested_threshold = float(np.percentile(diff_scores, 95)) if diff_scores else 0.5
        
    # Recalculate FAR/FRR based on suggested threshold
    far = sum(1 for s in diff_scores if s >= suggested_threshold) / len(diff_scores) if diff_scores else 0.0
    frr = sum(1 for s in same_scores if s < suggested_threshold) / len(same_scores) if same_scores else 0.0
    
    recall = 1.0 - frr
    correct_rejection = 1.0 - far
    
    std_top1_score = float(np.std(same_scores)) if same_scores else 0.0
    
    return {
        "valid": True,
        "metrics": {
            "accuracy": accuracy,
            "far": far,
            "frr": frr,
            "recall": recall,
            "correct_rejection_open_set": correct_rejection,
            "clean_separation": bool(clean_separation),
            "suggested_threshold": suggested_threshold,
            "min_same_score": float(min_same),
            "max_diff_score": float(max_diff),
            "std_top1_score": std_top1_score
        },
        "distributions": {
            "top1_score": same_scores_p,
            "margin": margin_p,
            "agreement_ratio": agreement_p
        },
        "counts": {
            "known_fish": len(known_fish_ids),
            "unknown_fish": len(unknown_fish_ids),
            "total_closed_queries": total_closed,
            "total_unknown_queries": total_unknown_queries
        }
    }

def main():
    parser = argparse.ArgumentParser(description="A/B/C evaluation for fingerprint crops")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--manifest", type=str, help="Path to manifest.json")
    group.add_argument("--data-dir", type=str, help="Path to evaluation data directory for auto-discovery")
    
    parser.add_argument("--output-dir", type=str, required=True, help="Directory to save evaluation results")
    parser.add_argument("--configs", type=str, default="A,B,C", help="Comma separated list of configs to evaluate")
    parser.add_argument("--open-set-fraction", type=float, default=0.25, help="Fraction of individuals to reserve for open-set evaluation")
    
    args = parser.parse_args()
    
    random.seed(42)
    np.random.seed(42)
    torch.manual_seed(42)
    
    os.makedirs(args.output_dir, exist_ok=True)
    
    if args.manifest:
        with open(args.manifest, 'r') as f:
            manifest = json.load(f)
    else:
        manifest = auto_discover_manifest(args.data_dir)
        
    print(f"Loaded {len(manifest)} items in manifest.")
    
    # Group by species
    species_to_manifest = defaultdict(list)
    for item in manifest:
        species_to_manifest[item["species_slug"]].append(item)
        
    configs_to_eval = [c.strip() for c in args.configs.split(",")]
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    
    # Load model
    model_name = getattr(settings, "REID_MODEL_NAME", "resnet50")
    model_path = getattr(settings, "REID_MODEL_PATH", "models/reid_model.pth")
    out_dim = getattr(settings, "REID_EMBEDDING_DIM", 512)
    
    try:
        model = load_model_for_infer(model_path=model_path, model_name=model_name, out_dim=out_dim, device=device)
        print("Model loaded successfully.")
    except Exception as e:
        print(f"Error loading model: {e}")
        return
        
    all_results = {}
    
    for cfg_name in configs_to_eval:
        if cfg_name not in CONFIGS:
            print(f"Warning: Config {cfg_name} not found. Skipping.")
            continue
            
        print(f"\n--- Evaluating Config {cfg_name} ---")
        cfg_results = {}
        
        # Extract embeddings for all data using this config's transform
        print(f"Extracting embeddings...")
        embeddings = extract_embeddings(manifest, cfg_name, CONFIGS[cfg_name], model, device)
        
        for species_slug, sp_manifest in species_to_manifest.items():
            print(f"  Evaluating species: {species_slug}")
            res = evaluate_species(species_slug, sp_manifest, embeddings, args.open_set_fraction)
            cfg_results[species_slug] = res
            
        all_results[cfg_name] = cfg_results

    # Analyze results to find the winner
    # Criteria: 1. Lowest FAR, 2. Best rejection of unknowns, 3. Stability, 4. Recall
    # We will average the metrics across valid species
    
    summary = []
    config_scores = {}
    
    for cfg_name, cfg_results in all_results.items():
        valid_species = [s for s, r in cfg_results.items() if r.get("valid")]
        if not valid_species:
            continue
            
        avg_far = np.mean([cfg_results[s]["metrics"]["far"] for s in valid_species])
        avg_cr = np.mean([cfg_results[s]["metrics"]["correct_rejection_open_set"] for s in valid_species])
        avg_std = np.mean([cfg_results[s]["metrics"]["std_top1_score"] for s in valid_species])
        avg_recall = np.mean([cfg_results[s]["metrics"]["recall"] for s in valid_species])
        avg_acc = np.mean([cfg_results[s]["metrics"]["accuracy"] for s in valid_species])
        
        config_scores[cfg_name] = {
            "avg_far": avg_far,
            "avg_cr": avg_cr,
            "avg_std": avg_std,
            "avg_recall": avg_recall,
            "avg_acc": avg_acc
        }
        
        summary.append(f"Config {cfg_name}:")
        summary.append(f"  Accuracy (closed-set): {avg_acc:.4f}")
        summary.append(f"  FAR: {avg_far:.4f}")
        summary.append(f"  FRR: {1.0 - avg_recall:.4f}")
        summary.append(f"  Recall: {avg_recall:.4f}")
        summary.append(f"  Correct Rejection (Open-set): {avg_cr:.4f}")
        summary.append(f"  Stability (std top1): {avg_std:.4f}")
        summary.append("")
        
    # Select winner
    winner = None
    reason = ""
    if config_scores:
        # Sort by: FAR (asc), Correct Rejection (desc), Stability (asc), Recall (desc)
        sorted_configs = sorted(
            config_scores.keys(),
            key=lambda k: (
                config_scores[k]["avg_far"],
                -config_scores[k]["avg_cr"],
                config_scores[k]["avg_std"],
                -config_scores[k]["avg_recall"]
            )
        )
        winner = sorted_configs[0]
        reason = "Selected based on lowest FAR, highest correct rejection, and lowest score dispersion."

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 1. Complete results JSON
    results_path = os.path.join(args.output_dir, f"{timestamp}_ab_results.json")
    with open(results_path, 'w') as f:
        json.dump(all_results, f, indent=2)
        
    # 2. Summary text
    summary_path = os.path.join(args.output_dir, f"{timestamp}_summary.txt")
    with open(summary_path, 'w') as f:
        f.write("\n".join(summary))
        
    # 3. Selection JSON
    selection_path = os.path.join(args.output_dir, f"{timestamp}_selection.json")
    with open(selection_path, 'w') as f:
        json.dump({
            "winner_config": winner,
            "winner_id": CONFIGS[winner]["id"] if winner else None,
            "reason": reason,
            "validated": True,
            "metrics": config_scores.get(winner, {})
        }, f, indent=2)
        
    print(f"Evaluation complete. Results saved to {args.output_dir}")
    print(f"Winner: {winner}")

if __name__ == "__main__":
    main()
