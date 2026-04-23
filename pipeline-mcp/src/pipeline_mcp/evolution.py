import os
import json
import shutil
import pickle
import time
import numpy as np
from pathlib import Path
from dataclasses import asdict, replace
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import pairwise_distances_argmin_min
import mlflow

try:
    import torch
    from transformers import AutoTokenizer, EsmModel
except ImportError:
    torch = None
    AutoTokenizer = None
    EsmModel = None

from .models import PipelineRequest, PipelineResult
from .storage import init_run, resolve_run_path, set_status, write_json
from .fasta import parse_fasta
from .s3 import ncp_storage

ESM_MODEL_NAME = "facebook/esm2_t6_8M_UR50D"

def get_esm_embeddings(sequences, device):
    if torch is None or AutoTokenizer is None or EsmModel is None:
        raise RuntimeError(
            "Evolution mode requires torch and transformers to be installed"
        )
    print(f"Loading ESM model {ESM_MODEL_NAME} for embedding extraction...")
    tokenizer = AutoTokenizer.from_pretrained(ESM_MODEL_NAME)
    model = EsmModel.from_pretrained(ESM_MODEL_NAME).to(device)
    model.eval()
    
    embeddings = []
    with torch.no_grad():
        for i in range(0, len(sequences), 16):
            batch_seqs = sequences[i:i+16]
            inputs = tokenizer(batch_seqs, return_tensors="pt", padding=True, truncation=True, max_length=1024)
            inputs = {k: v.to(device) for k, v in inputs.items()}
            outputs = model(**inputs)
            
            mask = inputs['attention_mask'].unsqueeze(-1).expand(outputs.last_hidden_state.size()).float()
            sum_emb = torch.sum(outputs.last_hidden_state * mask, dim=1)
            sum_mask = torch.clamp(mask.sum(dim=1), min=1e-9)
            mean_emb = sum_emb / sum_mask
            embeddings.append(mean_emb.cpu().numpy())
            
    return np.vstack(embeddings)

def run_evolution(runner, request: PipelineRequest, run_id: str) -> PipelineResult:
    if torch is None:
        raise RuntimeError("Evolution mode requires torch to be installed")
    paths = init_run(runner.output_root, run_id)
    set_status(paths, stage="evolution", state="running", detail="Initializing Local Active Learning Evolution")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    # 1. Stage 1: Mass Generation (ProteinMPNN)
    target_pool_size = getattr(request, "evolution_pool_size", 1000)
    set_status(paths, stage="evolution", state="running", detail=f"Stage 1: Generating {target_pool_size} candidates")
    
    pool_run_id = f"{run_id}_pool"
    pool_request = replace(
        request,
        evolution_mode=False,
        stop_after="soluprot",
        num_seq_per_tier=max(100, target_pool_size // 5),
    )
    
    try:
        runner.run(pool_request, run_id=pool_run_id)
    except Exception as e:
        set_status(paths, stage="error", state="failed", detail=f"Pool generation failed: {e}")
        raise

    # Read and collect data from Stage 1
    pool_dir = resolve_run_path(runner.output_root, pool_run_id)
    all_seqs = {}
    soluprot_scores = {}
    soluprot_cutoff = getattr(request, "soluprot_cutoff", 0.5)

    for tier_dir in (pool_dir / "tiers").glob("*"):
        if not tier_dir.is_dir(): continue
        fasta_file = next(tier_dir.glob("designs*.fasta"), None)
        if fasta_file:
            for rec in parse_fasta(fasta_file.read_text()):
                all_seqs[rec.id] = rec.sequence
        
        solu_json = tier_dir / "soluprot.json"
        if solu_json.exists():
            try:
                data = json.loads(solu_json.read_text())
                for sid, s in data.get("scores", {}).items():
                    soluprot_scores[sid] = float(s)
            except: pass

    gated_seq_ids = [sid for sid, seq in all_seqs.items() if soluprot_scores.get(sid, 0.0) >= soluprot_cutoff]
    if not gated_seq_ids: gated_seq_ids = list(all_seqs.keys())[:200]

    # 2. Stage 2: K-Means Diversity Sampling
    set_status(paths, stage="evolution", state="running", detail="Stage 2: K-Means Diversity Sampling & Active Learning")
    
    seq_texts = [all_seqs[sid] for sid in gated_seq_ids]
    X_embeddings = get_esm_embeddings(seq_texts, device)
    
    # Active Learning Parameters
    N_TRAIN = 30 # Oracle budget for training
    TOP_K = getattr(request, "evolution_oracle_samples", 20) # Final selection budget
    
    if len(gated_seq_ids) <= N_TRAIN + TOP_K:
        # If pool is too small, just evaluate everything
        train_idx = np.arange(len(gated_seq_ids))
        pool_idx = []
    else:
        # K-Means Sampling
        kmeans = KMeans(n_clusters=N_TRAIN, random_state=42, n_init=10)
        kmeans.fit(X_embeddings)
        closest_idx, _ = pairwise_distances_argmin_min(kmeans.cluster_centers_, X_embeddings)
        train_idx = np.unique(closest_idx)
        
        if len(train_idx) < N_TRAIN:
            remaining = np.setdiff1d(np.arange(len(gated_seq_ids)), train_idx)
            padding = np.random.choice(remaining, N_TRAIN - len(train_idx), replace=False)
            train_idx = np.concatenate([train_idx, padding])
            
        pool_idx = np.setdiff1d(np.arange(len(gated_seq_ids)), train_idx)

    # 3. Stage 3a: Run Oracle (AF2) on Training Set
    from .tools import _run_af2_predict, _safe_id
    
    final_results = []
    evolution_dir = paths.root / "evolution"
    designs_dir = evolution_dir / "designs"
    designs_dir.mkdir(parents=True, exist_ok=True)
    
    plddt_actual = []
    
    set_status(paths, stage="evolution", state="running", detail=f"Stage 3a: Evaluating {len(train_idx)} diverse training samples")
    
    for idx in train_idx:
        sid = gated_seq_ids[idx]
        seq = all_seqs[sid]
        eval_run_id = f"{run_id}_train_{_safe_id(sid)}"
        try:
            res = _run_af2_predict(runner, {
                "run_id": eval_run_id,
                "target_fasta": f">{sid}\n{seq}\n",
                "target_pdb": request.target_pdb,
                "af2_provider": request.af2_provider,
            })
            af2_data = res.get("summary", {}).get("af2", {}).get(sid, {})
            plddt = af2_data.get("best_plddt", 0.0)
            
            # Run Relax
            relax_score = None
            eval_path = resolve_run_path(runner.output_root, eval_run_id)
            af2_pdb = list((eval_path / request.af2_provider).rglob("*.pdb"))
            if af2_pdb and runner.rosetta_relax:
                print(f"Executing Serverless Relax for {sid}...")
                relax_out_dir = eval_path / "relax"
                relax_res = runner.rosetta_relax.run(af2_pdb[0], relax_out_dir, nstruct=request.relax_nstruct)
                relax_score = relax_res.get("score_per_residue")
                if relax_res.get("best_pdb"):
                    shutil.copy2(relax_res["best_pdb"], designs_dir / f"{sid}_relaxed.pdb")

            if af2_pdb:
                shutil.copy2(af2_pdb[0], designs_dir / f"{sid}.pdb")

            plddt_actual.append(plddt)
            final_results.append({
                "id": sid, "plddt": plddt, "soluprot": soluprot_scores.get(sid, 0.0), "relax_score": relax_score, "phase": "train"
            })
        except Exception as e:
            print(f"Oracle error for training sample {sid}: {e}")
            plddt_actual.append(0.0)

    # 4. Stage 3b: Train Local Surrogate and Predict Pool
    if len(pool_idx) > 0:
        set_status(paths, stage="evolution", state="running", detail=f"Stage 3b: Training Surrogate & Predicting Pool")
        
        X_train = X_embeddings[train_idx]
        y_train = np.array(plddt_actual)
        
        rf = RandomForestRegressor(n_estimators=100, random_state=42)
        rf.fit(X_train, y_train)
        
        X_pool = X_embeddings[pool_idx]
        pred_plddt = rf.predict(X_pool)
        
        top_surrogate_idx = np.argsort(pred_plddt)[-TOP_K:]
        
        # 5. Stage 3c: Run Oracle on Top K Predictions
        set_status(paths, stage="evolution", state="running", detail=f"Stage 3c: Evaluating Top {TOP_K} Surrogate Predictions")
        for i in top_surrogate_idx:
            idx = pool_idx[i]
            sid = gated_seq_ids[idx]
            seq = all_seqs[sid]
            eval_run_id = f"{run_id}_topk_{_safe_id(sid)}"
            try:
                res = _run_af2_predict(runner, {
                    "run_id": eval_run_id,
                    "target_fasta": f">{sid}\n{seq}\n",
                    "target_pdb": request.target_pdb,
                    "af2_provider": request.af2_provider,
                })
                af2_data = res.get("summary", {}).get("af2", {}).get(sid, {})
                plddt = af2_data.get("best_plddt", 0.0)
                
                relax_score = None
                eval_path = resolve_run_path(runner.output_root, eval_run_id)
                af2_pdb = list((eval_path / request.af2_provider).rglob("*.pdb"))
                if af2_pdb and runner.rosetta_relax:
                    print(f"Executing Serverless Relax for {sid}...")
                    relax_out_dir = eval_path / "relax"
                    relax_res = runner.rosetta_relax.run(af2_pdb[0], relax_out_dir, nstruct=request.relax_nstruct)
                    relax_score = relax_res.get("score_per_residue")
                    if relax_res.get("best_pdb"):
                        shutil.copy2(relax_res["best_pdb"], designs_dir / f"{sid}_relaxed.pdb")

                if af2_pdb:
                    shutil.copy2(af2_pdb[0], designs_dir / f"{sid}.pdb")

                final_results.append({
                    "id": sid, "plddt": plddt, "soluprot": soluprot_scores.get(sid, 0.0), "relax_score": relax_score, "phase": "top_k"
                })
            except Exception as e:
                print(f"Oracle error for Top K sample {sid}: {e}")

    # 6. Finalize & Sync
    def composite_actual(r):
        s = r['plddt'] * 0.4 + r['soluprot'] * 30.0
        if r['relax_score'] is not None:
            s -= r['relax_score'] * 10.0
        return s

    best_res = max(final_results, key=composite_actual) if final_results else {"id": "none", "plddt": 0}
    
    summary = {
        "run_id": run_id,
        "evolution_mode": "local-active-learning-kmeans",
        "pool_statistics": {"initial": len(all_seqs), "gated": len(gated_seq_ids), "oracle_train": N_TRAIN, "oracle_top_k": TOP_K},
        "best_design": best_res,
        "evaluated_samples": final_results
    }
    
    write_json(paths.summary_json, summary)
    set_status(paths, stage="done", state="completed")
    
    # Global Flywheel: Sync to S3
    try:
        ncp_storage.sync_outputs(run_id)
    except: pass
    
    # MLflow Tracking
    try:
        mlflow.set_tracking_uri("http://127.0.0.1:18050")
        mlflow.set_experiment("Pipeline_Evolution_Runs")
        with mlflow.start_run(run_name=f"Evo_{run_id}"):
            mlflow.log_param("run_id", run_id)
            mlflow.log_param("pool_size", len(all_seqs))
            mlflow.log_param("train_size", N_TRAIN)
            mlflow.log_param("top_k", TOP_K)
            mlflow.log_metric("best_plddt", best_res.get("plddt", 0))
            if best_res.get("soluprot") is not None:
                mlflow.log_metric("best_soluprot", best_res.get("soluprot"))
            if best_res.get("relax_score") is not None:
                mlflow.log_metric("best_relax", best_res.get("relax_score"))
    except Exception: pass

    return PipelineResult(run_id=run_id, output_dir=str(paths.root), tiers=[])
