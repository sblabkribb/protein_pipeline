# Purpose
- Natural-language to pipeline agent for protein design: `MMseqs2 conservation (30/50/70%) → ligand 6Å mask → ProteinMPNN (soluble) → SoluProt filter ≥0.5 → AlphaFold2 → novelty search`.
- Must be tolerant to model swaps (MMseqs2/ProteinMPNN/AF2 variants) and reruns; keep data handoff consistent so downstream steps stay stable.

# Preconditions & Config
- Secrets: `RUNPOD_API_KEY`, endpoint ids for `mmseqs-runpod` and `proteinmpnn-runpod`, SoluProt/AF2 access tokens if required.
- Inputs expected from the user prompt or files: target FASTA, optional PDB (for ligand masking; if absent, AF2 prediction from the target is allowed as the mask source), ligand identifiers or “all non-water hetero atoms”.
- Working dir: create `outputs/<run_id>/` for intermediates (`msa/`, `designs/`, `af2/`, `search/`).

# Tools (MCP adapters)
- **MMseqs2 (RunPod)**: task `search` returning TSV + optional A3M (`return_a3m=true`); defaults to `uniref90`. Use for (a) conservation MSA, (b) final novelty search vs `uniref90`/`uniref50`.
- **ProteinMPNN (RunPod)**: requires PDB (plain or base64). Use `use_soluble_model=true`; pass chain mask and fixed positions (see masking step).
- **SoluProt**: batch HTTP client; return probability per sequence. Keep only `score >= 0.5`.
- **AlphaFold2**: local/remote runner; accept FASTA; return `pLDDT`, `PTM`, `PAE`. Cache by sequence hash + template settings.
- **AlphaFold2 (RunPod)**: 결과 archive에서 `ranking_debug.json`을 파싱해 평균 `pLDDT`를 추출하고, `pLDDT>=85` + 상위 `20`개만 다음 단계로 전달.
- All tool calls should stream logs where possible and capture raw JSON/TSV artifacts in the run folder.

# Pipeline (default)
1) **Ingest**: parse user request; normalize FASTA headers; assign `run_id`; persist request context.
2) **MSA & conservation** (MMseqs2): run `search` with `return_a3m=true`, `max_seqs` tuned for depth (e.g., 3k). Compute per-position conservation; build three masks for ≥30/≥50/≥70% identity to consensus.
3) **Ligand 6Å mask**: from provided or predicted structure, mark residues with any heavy-atom distance ≤6 Å to non-water ligands/hetero atoms; force these residues to stay native during design.
4) **Mask merge**: for each conservation tier, allowed-to-mutate set = residues not in tier mask AND not in ligand mask. Emit per-tier residue lists for ProteinMPNN (`fixed_residues`).
5) **ProteinMPNN (soluble)**: run once per tier; inputs: PDB, `pdb_path_chains`, `use_soluble_model=true`, `num_seq_per_target`/`batch_size`, `sampling_temp`, `seed`, `fixed_positions` from mask. Save JSON + FASTA.
6) **SoluProt filter**: score all sequences; drop `<0.5`. Annotate surviving FASTA/JSON with `soluprot_score`.
7) **AlphaFold2**: surviving sequences에 대해 AF2 실행 → `pLDDT>=85`만 통과 → `pLDDT` 내림차순 상위 20개만 유지.
8) **Novelty search**: (선택) AF2 통과(top 20) 서열만 MMseqs2 `search`로 novelty 체크.
9) **Summarize**: produce `summary.json` per run with per-tier counts, thresholds used, file pointers, and any failures. Return paths in agent reply.

# NL Router Rules
- Default: run full pipeline above. If user says “stop after X”, truncate at that node. If they change models (e.g., new AF2 params), swap config but keep the same data schema.
- Knobs exposed: conservation cutoffs, ligand mask toggle, chains, num designs, temps/seeds, soluprot cutoff, AF2 model/preset, novelty DB.
- Safety: reject ambiguous inputs (no sequence, unusable PDB) with a clarifying question.

# Error handling & resume
- Each node writes status + artifacts to `outputs/<run_id>/<node>.{json,log}`. If rerun, skip completed nodes unless user requests `force`.
- On tool failure, capture stderr/log tail and return concise reason; allow rerun with adjusted parameters.

# Responses
- Keep replies short: where the run folder is, what completed, what failed. Provide key files (TSV/FASTA/JSON) per tier, not full contents.
