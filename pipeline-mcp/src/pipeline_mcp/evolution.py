import json
import time
import numpy as np
from pathlib import Path
import os
import shutil
import pickle
import torch
from dataclasses import replace
from transformers import AutoTokenizer, EsmModel

from .models import PipelineRequest, PipelineResult
from .storage import init_run, set_status, write_json, new_run_id, resolve_run_path
from .bio.fasta import parse_fasta
from .s3 import ncp_storage

# Configuration for Deep Meta-Surrogate
ESM_MODEL_NAME = "facebook/esm2_t6_8M_UR50D"
MODEL_DIR = Path("pipeline-mcp/models")
SOLUPROT_MODEL_PATH = MODEL_DIR / "global_soluprot_v1.pkl"
PLDDT_MODEL_PATH = MODEL_DIR / "global_plddt_v1.pkl"

def get_esm_embeddings(sequences, device):
    print(f"Loading ESM model {ESM_MODEL_NAME} for embedding extraction...")
    tokenizer = AutoTokenizer.from_pretrained(ESM_MODEL_NAME)
    model = EsmModel.from_pretrained(ESM_MODEL_NAME).to(device)
    model.eval()
    
    embeddings = []
    batch_size = 16
    with torch.no_grad():
        for i in range(0, len(sequences), batch_size):
            batch = sequences[i:i+batch_size]
            inputs = tokenizer(batch, return_tensors="pt", padding=True, truncation=True).to(device)
            outputs = model(**inputs)
            
            # Mean Pooling (excluding padding)
            mask = inputs['attention_mask'].unsqueeze(-1).expand(outputs.last_hidden_state.size()).float()
            sum_emb = torch.sum(outputs.last_hidden_state * mask, dim=1)
            sum_mask = torch.clamp(mask.sum(dim=1), min=1e-9)
            mean_emb = sum_emb / sum_mask
            embeddings.append(mean_emb.cpu().numpy())
            
    return np.vstack(embeddings)

def run_evolution(runner, request: PipelineRequest, run_id: str) -> PipelineResult:
    paths = init_run(runner.output_root, run_id)
    set_status(paths, stage="evolution", state="running", detail="Initializing 3-Stage Meta-Surrogate Evolution")

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    # 1. Stage 1: Mass Generation (Default 1,000 sequences)
    target_pool_size = getattr(request, "evolution_pool_size", 1000)
    set_status(paths, stage="evolution", state="running", detail=f"Stage 1: Generating pool of {target_pool_size} candidates")
    
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

    # Read sequences and SoluProt scores
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

    # Apply Gate 1: Solubility
    gated_seq_ids = [sid for sid, seq in all_seqs.items() if soluprot_scores.get(sid, 0.0) >= soluprot_cutoff]
    if not gated_seq_ids: gated_seq_ids = list(all_seqs.keys())[:200]

    # 2. Stage 2: Deep Meta-Surrogate Ranking
    set_status(paths, stage="evolution", state="running", detail="Stage 2: ESM-2 Ranking (Zero-Shot)")
    
    seq_texts = [all_seqs[sid] for sid in gated_seq_ids]
    X_embeddings = get_esm_embeddings(seq_texts, device)
    
    # Load Pre-trained Models
    mlp_solu, mlp_plddt = None, None
    try:
        if SOLUPROT_MODEL_PATH.exists():
            with open(SOLUPROT_MODEL_PATH, 'rb') as f: mlp_solu = pickle.load(f)
        if PLDDT_MODEL_PATH.exists():
            with open(PLDDT_MODEL_PATH, 'rb') as f: mlp_plddt = pickle.load(f)
    except Exception as e:
        print(f"Model load failed: {e}")

    # Ranking
    if mlp_plddt and mlp_solu:
        pred_plddt = mlp_plddt.predict(X_embeddings)
        pred_solu = mlp_solu.predict(X_embeddings)
        # Weighted Score: pLDDT (70%) + SoluProt (30%)
        # Note: SoluProt is 0-1, pLDDT is 0-100, so we scale SoluProt
        combined_scores = (pred_plddt * 0.7) + (pred_solu * 30.0)
    else:
        combined_scores = np.random.rand(len(gated_seq_ids))

    n_oracle = getattr(request, "evolution_oracle_samples", 20)
    top_indices = np.argsort(combined_scores)[::-1][:n_oracle]
    selected_ids = [gated_seq_ids[i] for i in top_indices]

    # 3. Stage 3: High-Fidelity AF2 Oracle
    set_status(paths, stage="evolution", state="running", detail=f"Stage 3: AF2 validation for Top {n_oracle}")
    
    final_results = []
    evolution_dir = paths.root / "evolution"
    designs_dir = evolution_dir / "designs"
    designs_dir.mkdir(parents=True, exist_ok=True)

    from .tools import _run_af2_predict, _safe_id
    for sid in selected_ids:
        seq = all_seqs[sid]
        eval_run_id = f"{run_id}_eval_{_safe_id(sid)}"
        try:
            res = _run_af2_predict(runner, {
                "run_id": eval_run_id,
                "target_fasta": f">{sid}\n{seq}\n",
                "target_pdb": request.target_pdb,
                "af2_provider": request.af2_provider,
            })
            plddt = res.get("summary", {}).get("af2", {}).get(sid, {}).get("best_plddt", 0.0)
            final_results.append({"id": sid, "plddt": plddt, "soluprot": soluprot_scores.get(sid, 0.0)})
            
            # Save best model to evolution/designs
            eval_path = resolve_run_path(runner.output_root, eval_run_id)
            pdb_files = list((eval_path / request.af2_provider).rglob("*.pdb"))
            if pdb_files:
                shutil.copy2(pdb_files[0], designs_dir / f"{sid}.pdb")
        except Exception as e:
            print(f"AF2 Failed for {sid}: {e}")

    # 4. Finalize
    best_res = max(final_results, key=lambda x: x['plddt']) if final_results else {"id": "none", "plddt": 0}
    summary = {
        "run_id": run_id,
        "evolution_mode": "meta-surrogate-v1",
        "pool_statistics": {"initial": len(all_seqs), "gated": len(gated_seq_ids), "oracle": len(final_results)},
        "best_design": best_res,
        "evaluated_samples": final_results
    }
    
    write_json(paths.summary_json, summary)
    set_status(paths, stage="done", state="completed")
    
    # Sync to NCP S3
    try:
        ncp_storage.sync_outputs(run_id)
    except: pass
    
    return PipelineResult(run_id=run_id, output_dir=str(paths.root), tiers=[])
