import json
import time
import numpy as np
from pathlib import Path
import os
import shutil
from dataclasses import replace

try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import OrdinalEncoder
except ImportError:
    RandomForestRegressor = None
    OrdinalEncoder = None

from .models import PipelineRequest, PipelineResult
from .storage import init_run, set_status, write_json, new_run_id, resolve_run_path
from .bio.fasta import parse_fasta

def encode_sequences(seq_list):
    chars = [list(s) for s in seq_list]
    encoder = OrdinalEncoder(handle_unknown='use_encoded_value', unknown_value=-1)
    return encoder.fit_transform(chars), encoder

def calculate_acquisition(mean_pred, std_pred, kappa=2.0):
    return mean_pred + kappa * std_pred

def run_evolution(runner, request: PipelineRequest, run_id: str) -> PipelineResult:
    if RandomForestRegressor is None:
        raise RuntimeError("scikit-learn is required for evolution mode. Please install it.")

    paths = init_run(runner.output_root, run_id)
    set_status(paths, stage="evolution", state="running", detail="Initializing BO pool")

    # 1. Generate sequence pool
    pool_run_id = f"{run_id}_pool"
    pool_request = replace(
        request,
        evolution_mode=False,
        stop_after="soluprot",
        num_seq_per_tier=max(50, request.num_seq_per_tier * 5), # Generate more for pool
    )
    
    try:
        pool_result = runner.run(pool_request, run_id=pool_run_id)
    except Exception as e:
        set_status(paths, stage="error", state="failed", detail=f"Pool generation failed: {e}")
        raise

    # Read generated sequences
    pool_dir = resolve_run_path(runner.output_root, pool_run_id)
    seqs = {}
    for tier_dir in (pool_dir / "tiers").glob("*"):
        if not tier_dir.is_dir():
            continue
        fasta_file = tier_dir / "designs_filtered.fasta"
        if not fasta_file.exists():
            fasta_file = tier_dir / "designs.fasta"
        if fasta_file.exists():
            records = parse_fasta(fasta_file.read_text())
            for rec in records:
                seqs[rec.id] = rec.sequence

    if len(seqs) < request.evolution_initial_samples:
        set_status(paths, stage="error", state="failed", detail="Not enough sequences generated for BO pool")
        raise RuntimeError(f"Generated {len(seqs)} sequences, need at least {request.evolution_initial_samples}")

    seq_ids = list(seqs.keys())
    seq_texts = [seqs[sid] for sid in seq_ids]
    
    X_encoded, encoder = encode_sequences(seq_texts)
    
    # 2. Initial Evaluation
    set_status(paths, stage="evolution", state="running", detail="Initial evaluation")
    np.random.seed(42)
    evaluated_indices = list(np.random.choice(len(seq_texts), min(request.evolution_initial_samples, len(seq_texts)), replace=False))
    untested_indices = list(set(range(len(seq_texts))) - set(evaluated_indices))
    
    y_true = []
    
    def evaluate_af2(indices):
        scores = []
        evolution_dir = paths.root / "evolution"
        evolution_dir.mkdir(parents=True, exist_ok=True)
        designs_dir = evolution_dir / "designs"
        designs_dir.mkdir(parents=True, exist_ok=True)

        for idx in indices:
            sid = seq_ids[idx]
            seq = seq_texts[idx]
            
            eval_run_id = f"{run_id}_eval_{sid.replace(':', '_')}"
            fasta_payload = f">{sid}\n{seq}\n"
            
            try:
                from .tools import _run_af2_predict
                res = _run_af2_predict(runner, {
                    "run_id": eval_run_id,
                    "target_fasta": fasta_payload,
                    "target_pdb": request.target_pdb,
                    "af2_provider": request.af2_provider,
                    "af2_model_preset": request.af2_model_preset,
                })
                
                summary = res.get("summary", {})
                af2_res = summary.get("af2", {}).get(sid, {})
                plddt = af2_res.get("best_plddt", 0.0)
                scores.append(plddt)
                
                # Copy the best model to the evolution/designs directory
                eval_run_path = resolve_run_path(runner.output_root, eval_run_id)
                af2_out_dir = eval_run_path / request.af2_provider
                best_pdb_path = None
                
                # Af2 prediction usually creates a file like ranked_0.pdb
                if (af2_out_dir / sid / "ranked_0.pdb").exists():
                    best_pdb_path = af2_out_dir / sid / "ranked_0.pdb"
                elif (af2_out_dir / f"{sid}_unrelaxed_rank_001_alphafold2_ptm_model_1_seed_000.pdb").exists():
                    # For ColabFold standard output without folder
                    best_pdb_path = next(af2_out_dir.glob(f"{sid}_unrelaxed_rank_001_*.pdb"), None)

                # Fallback to recursively finding the best model by looking at af2_res or just searching
                if not best_pdb_path:
                    # Let's just find any pdb file in that directory
                    pdb_files = list(af2_out_dir.rglob("*.pdb"))
                    if pdb_files:
                        best_pdb_path = pdb_files[0]
                        for p in pdb_files:
                            if "ranked_0" in p.name or "rank_001" in p.name:
                                best_pdb_path = p
                                break

                if best_pdb_path:
                    dest_path = designs_dir / f"{sid}.pdb"
                    shutil.copy2(best_pdb_path, dest_path)
            except Exception as e:
                print(f"Evaluation failed for {sid}: {e}")
                scores.append(0.0)
        return np.array(scores)

    initial_scores = evaluate_af2(evaluated_indices)
    y_true.extend(initial_scores)

    # 3. BO Loop
    rounds = request.evolution_rounds
    samples_per_round = request.evolution_samples_per_round

    for r in range(rounds):
        if not untested_indices:
            break
            
        set_status(paths, stage="evolution", state="running", detail=f"BO Round {r+1}/{rounds}")
        
        X_train = X_encoded[evaluated_indices]
        y_train = np.array(y_true)
        
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        
        X_untested = X_encoded[untested_indices]
        preds = np.array([tree.predict(X_untested) for tree in model.estimators_])
        mean_pred = preds.mean(axis=0)
        std_pred = preds.std(axis=0)
        
        acq_scores = calculate_acquisition(mean_pred, std_pred, kappa=1.5)
        
        best_local_indices = np.argsort(acq_scores)[::-1][:samples_per_round]
        selected_global_indices = [untested_indices[i] for i in best_local_indices]
        
        new_scores = evaluate_af2(selected_global_indices)
        
        evaluated_indices.extend(selected_global_indices)
        y_true.extend(new_scores)
        
        for i in sorted(best_local_indices, reverse=True):
            untested_indices.pop(i)

    # 4. Finalize
    best_idx_in_eval = np.argmax(y_true)
    best_global_idx = evaluated_indices[best_idx_in_eval]
    best_sid = seq_ids[best_global_idx]
    best_seq = seq_texts[best_global_idx]
    best_score = y_true[best_idx_in_eval]

    summary = {
        "run_id": run_id,
        "evolution_mode": True,
        "total_evaluated": len(evaluated_indices),
        "best_sequence_id": best_sid,
        "best_sequence": best_seq,
        "best_score": best_score,
        "evaluated_samples": [
            {"id": seq_ids[idx], "score": score}
            for idx, score in zip(evaluated_indices, y_true)
        ]
    }
    
    write_json(paths.summary_json, summary)
    set_status(paths, stage="done", state="completed")
    
    return PipelineResult(
        run_id=run_id,
        output_dir=str(paths.root),
        msa_a3m_path=None,
        msa_filtered_a3m_path=None,
        msa_tsv_path=None,
        conservation_path=None,
        ligand_mask_path=None,
        surface_mask_path=None,
        tiers=[],
        errors=[],
    )
