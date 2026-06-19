# Corrected-chain CATH refresh — full surrogate benchmark inputs

This is the 77-target corrected-chain CATH refresh dataset that all 77-target
surrogate analyses in the manuscript are based on (Supplementary Notes 2-7 and
14; abstract 9,206 paired SoluProt/pLDDT records).

- `cath_pilot_dataset.csv` — per-design records: target, run_id, tier, seq_id,
  sequence, plddt, soluprot (9,206 rows / 77 targets).
- `cath_pilot_emb_320d.npy` — mean-pooled ESM-2 8M (esm2_t6_8M_UR50D) embeddings,
  row-aligned to the CSV (9,206 x 320).
- `cath_pilot_emb_640d.npy` — mean-pooled ESM-2 150M (esm2_t30_150M_UR50D)
  embeddings for the embedding-size ablation (9,206 x 640).

Reproduce: place these at `data/benchmark/` (the path the benchmark scripts under
`scripts/benchmark/` expect) and run `02_model_comparison.py`,
`03_sample_size_ablation.py`, `04_esm_size_ablation.py`, etc. The 8M arm
reproduces the Note 4 Random Forest baseline exactly. Embeddings can also be
regenerated with `01_compute_embeddings.py --model {8M,150M}`.

(The top-level `public_data/cath_curated/` and `public_data/cath_73/` directories
are the earlier PRE-refresh subsets and are not the final benchmark.)
