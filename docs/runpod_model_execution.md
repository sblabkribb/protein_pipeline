# RunPod 모델 실행 방식 (로컬 커맨드 관점)

이 문서는 `docs/stepper_orchestration.md`(stepper → `pipeline.run`/`pipeline.status` 오케스트레이션)와 별개로, **RunPod endpoint 컨테이너 내부에서 실제로 실행되는 커맨드**를 “로컬에서 직접 치는 것처럼” 정리합니다.

> 핵심: 오케스트레이터는 RunPod에 “커맨드 문자열”을 보내는 게 아니라 **payload(JSON)** 를 보냅니다. 실제 커맨드는 각 endpoint 이미지의 `handler.py`가 `subprocess`로 실행합니다.

---

## 0) 전체 호출 흐름 (요약)

1. Stepper(Codex skill) → `pipeline.run`/`pipeline.status` 호출
2. `pipeline-mcp`가 RunPod API로 job 제출 (`pipeline-mcp/src/pipeline_mcp/clients/runpod.py`)
3. RunPod Serverless endpoint가 컨테이너를 띄우고 `handler.py` 실행
4. `handler.py`가 컨테이너 내부에서 로컬 커맨드를 실행하고 결과(JSON)를 반환
5. `pipeline-mcp`가 결과를 `outputs/<run_id>/`에 파일로 저장

---

## 1) MMseqs2 (MSA/novelty) — `mmseqs-runpod`

관련 코드: `mmseqs-runpod/handler.py`의 `_handle_search()`

### 1.1 입력(payload) → 로컬 실행으로 매핑

`pipeline-mcp`는 RunPod endpoint에 대략 아래 형태의 payload를 보냅니다 (`pipeline-mcp/src/pipeline_mcp/clients/mmseqs.py`).

- `task: "search"`
- `query_fasta: "<FASTA text>"`
- `target_db: "uniref90"` (기본)
- `threads`, `use_gpu`
- `max_seqs` (선택)
- `return_a3m: true/false`

### 1.2 컨테이너 내부에서 실제로 도는 커맨드 (중요)

아래는 `mmseqs-runpod/handler.py`가 실행하는 커맨드를 “로컬 재현 형태”로 풀어쓴 것입니다(경로는 job마다 달라서 placeholder로 표기).

```bash
# (1) query를 DB로 변환 (job 임시 디렉토리)
mmseqs createdb <work_dir>/query.fasta <work_dir>/query_db --threads <threads>

# (2) (GPU 사용 시) query DB를 padded DB로 변환
mmseqs makepaddedseqdb <work_dir>/query_db <work_dir>/query_db_pad --threads <threads>

# (3) target DB 준비
#  - 보통은 PV에 "persistent DB"로 존재: <db_root>/<target_db>
#  - GPU 사용 시 padded 버전: <db_root>/<target_db>_pad
#
# (4) 검색 (result_db는 job 임시 디렉토리에 생성)
mmseqs search <query_db_or_pad> <target_db_or_pad> <work_dir>/result_db <tmp_dir> \
  --threads <threads> --gpu <0|1> [--max-seqs <max_seqs>]

# (5) result_db → TSV 텍스트 변환 (이게 result.tsv의 정체)
mmseqs convertalis <work_dir>/query_db <target_db_prefix> <work_dir>/result_db <work_dir>/result.tsv \
  --format-output "query,target,evalue,pident,alnlen" --threads <threads>

# (6) (MSA가 필요할 때만) A3M 생성
mmseqs result2msa <work_dir>/query_db <target_db_prefix> <work_dir>/result_db <work_dir>/result.a3m \
  --threads <threads> --msa-format-mode 1
```

### 1.3 `outputs/<run_id>/msa/result.tsv`가 “search에서 나온 게 아닌 것 같다”는 느낌의 원인

`pipeline-mcp`가 저장하는 `msa/result.tsv`는 **`mmseqs search`의 바이너리 resultDB가 아니라**, 그 resultDB를 `mmseqs convertalis`로 텍스트로 변환한 결과입니다.

- 기본 컬럼: `query,target,evalue,pident,alnlen` (5개)
- 그래서 기대한 TSV 포맷(예: 더 많은 필드/원하는 columns)과 다르게 보일 수 있습니다.

### 1.4 `target.db`가 안 보이는 이유(정상일 수 있음)

`mmseqs-runpod`는 job마다 아래 파일/DB를 **임시 디렉토리**에 만들고 job 종료 시 정리합니다.

- `query_db`, `result_db`, (필요하면) `query_db_pad`, `target_db_pad`(inline target일 때)

영속적으로 남길 수 있는 건 **target DB(예: uniref90)** 뿐이고, 이건 PV 아래에 “prefix 형태”로 존재해야 합니다.

### 1.5 persistent DB의 위치/ready marker

`mmseqs-runpod`가 persistent DB를 찾는 위치(우선순위)는 대략 아래입니다.

- `$MMSEQS_DB_ROOT/<db_key>`
- `$RUNPOD_VOLUME_PATH/mmseqsdb/<db_key>` 또는 `/runpod-volume/mmseqsdb/<db_key>`
- (fallback) `/opt/mmseqs/data/mmseqsdb/<db_key>`

DB가 “준비됨”으로 인식되려면 `"<prefix>.ready"`가 있거나, `"<prefix>.dbtype"`이 있고 writer lock 디렉토리가 없어야 합니다.

---

## 2) ProteinMPNN (design) — `ProteinMPNN-runpod`

관련 코드: `ProteinMPNN-runpod/handler.py`

### 2.1 입력(payload)

`pipeline-mcp`는 ProteinMPNN endpoint에 아래와 유사한 payload를 보냅니다 (`pipeline-mcp/src/pipeline_mcp/clients/proteinmpnn.py`).

- `pdb_base64` (PDB 텍스트 base64)
- `pdb_name` (기본 `"input"`)
- `pdb_path_chains` (선택; 예: `["A"]`)
- `fixed_positions` (선택; `{ "A": [1,2,3], ... }`)
- `use_soluble_model: true`
- `model_name: "v_48_020"`
- `num_seq_per_target`, `batch_size`, `sampling_temp`, `seed`

### 2.2 컨테이너 내부 커맨드 (로컬 재현)

`ProteinMPNN-runpod/handler.py`는 payload를 받아 `/tmp/proteinmpnn_<job_id>/` 아래에 입력 파일을 만든 다음 아래 커맨드를 실행합니다.

```bash
python /opt/ProteinMPNN/protein_mpnn_run.py \
  --pdb_path /tmp/proteinmpnn_<job_id>/<pdb_name>.pdb \
  --out_folder /tmp/proteinmpnn_<job_id>/out \
  --num_seq_per_target <N> \
  --batch_size <B> \
  --sampling_temp "<temp>" \
  --seed <seed> \
  --model_name v_48_020 \
  --backbone_noise 0.0 \
  --suppress_print 1 \
  --use_soluble_model \
  [--pdb_path_chains "A B"] \
  [--fixed_positions_jsonl /tmp/proteinmpnn_<job_id>/fixed_positions.jsonl]
```

참고:
- 이 파이프라인은 질문에서 언급한 `--jsonl_path / --chain_id_jsonl` 배치 모드가 아니라, `--pdb_path` 단일 PDB 모드로 호출합니다.
- `fixed_positions_jsonl` 파일은 handler가 job 디렉토리에 자동 생성합니다.

---

## 3) AlphaFold2 (AF2) — “RunPod endpoint 또는 HTTP 서비스”

관련 코드:
- RunPod endpoint 방식: `pipeline-mcp/src/pipeline_mcp/clients/alphafold2_runpod.py`
- HTTP 서비스 방식: `pipeline-mcp/src/pipeline_mcp/clients/alphafold2.py`

### 3.1 RunPod AF2 endpoint에 보내는 payload(컨테이너 내부 커맨드 대신 “계약(Contract)”)

이 repo에는 **AF2 RunPod endpoint의 `handler.py`/Dockerfile이 포함되어 있지 않아서**, 컨테이너 내부에서 어떤 커맨드를 실행하는지는 이미지 구현에 따라 달라집니다.

대신 `pipeline-mcp`가 기대하는 최소 계약은 다음과 같습니다.

- 입력: `{sequence, model_preset, db_preset, max_template_date, alphafold_extra_flags}`
- 출력: tar.gz(또는 archives 배열) 안에 최소한 아래 파일이 포함되어야 함
  - `ranking_debug.json` (pLDDT 추출용)
  - `ranked_0.pdb` (구조 저장용)

`pipeline-mcp`는 `ranking_debug.json`에서 best pLDDT를 계산하고, 결과를 `outputs/<run_id>/tiers/<tier>/af2/<seq_id>/` 아래로 풀어 저장합니다.

---

## 4) “진짜로 실행된 커맨드”를 확인하는 방법 (가장 확실)

오케스트레이터가 RunPod에 “커맨드 문자열”을 직접 보내는 구조가 아니기 때문에, **RunPod job 로그(stdout/stderr)** 가 정답입니다.

파이프라인 산출물에 RunPod job id가 저장됩니다.

- MMseqs2: `outputs/<run_id>/msa/runpod_job.json`
- ProteinMPNN: `outputs/<run_id>/tiers/<tier>/runpod_job.json`
- AF2: `outputs/<run_id>/tiers/<tier>/af2/runpod_jobs.json`

특히 `mmseqs-runpod`는 로그에 `$ mmseqs ...` 형태로 커맨드를 그대로 출력하도록 구현되어 있어(`mmseqs-runpod/handler.py`의 `_run()`), job 로그만 보면 실행 커맨드를 1:1로 확인할 수 있습니다.
