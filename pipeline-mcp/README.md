# pipeline-mcp

NCP CPU 서버에서 동작하는 파이프라인 오케스트레이터(MCP 스타일 tool 서버)입니다.

## 제공 기능(핵심 흐름)
`MMseqs2(A3M) → 보존도 마스킹(30/50/70) → ligand 6Å 고정 → ProteinMPNN(soluble) → SoluProt(>=0.5) → AlphaFold2 → MMseqs2 novelty`

## 환경변수
### RunPod
- `RUNPOD_API_KEY` (필수)
- `MMSEQS_ENDPOINT_ID` (필수)
- `PROTEINMPNN_ENDPOINT_ID` (필수)
- `ALPHAFOLD2_ENDPOINT_ID` (선택, 설정 시 RunPod AF2 사용)
- TLS 옵션(선택): `RUNPOD_CA_BUNDLE`, `RUNPOD_SKIP_VERIFY=1`
- (선택) `PIPELINE_MMSEQS_USE_GPU=1`: 요청에 `mmseqs_use_gpu`를 명시하지 않으면 기본값을 GPU로 설정

### Optional services
- `SOLUPROT_URL` (선택, 미설정 시 filtering 단계 skip)
- `AF2_URL` (선택, `ALPHAFOLD2_ENDPOINT_ID` 미설정 시 HTTP AF2 사용)

### Local
- `PIPELINE_OUTPUT_ROOT` (기본: `outputs`)

## 권장: `.env`로 시크릿 관리
```bash
cd /opt/protein_pipeline/pipeline-mcp
cat > .env <<'EOF'
RUNPOD_API_KEY=...
MMSEQS_ENDPOINT_ID=...
PROTEINMPNN_ENDPOINT_ID=...
ALPHAFOLD2_ENDPOINT_ID=...
PIPELINE_MMSEQS_USE_GPU=1
SOLUPROT_URL=http://127.0.0.1:18081/score
PIPELINE_OUTPUT_ROOT=/opt/protein_pipeline/outputs
EOF
chmod 600 .env
```

## 로컬 실행(HTTP)
```bash
PYTHONPATH=pipeline-mcp/src \
RUNPOD_API_KEY=... MMSEQS_ENDPOINT_ID=... PROTEINMPNN_ENDPOINT_ID=... \
python3 -m pipeline_mcp.http_server --host 0.0.0.0 --port 8000
```

## Docker 실행(NCP)
```bash
docker build -t pipeline-mcp:cpu ./pipeline-mcp
docker run --rm -p 8000:8000 \
  -e RUNPOD_API_KEY=... \
  -e MMSEQS_ENDPOINT_ID=... \
  -e PROTEINMPNN_ENDPOINT_ID=... \
  -e PIPELINE_OUTPUT_ROOT=/app/outputs \
  -v /data/outputs:/app/outputs \
  pipeline-mcp:cpu
```

## API (간단 HTTP)
- `GET /healthz`
- `POST /tools/list`
- `POST /tools/call`

`tools/call`에서 `name="pipeline.run"`으로 실행합니다.

⚠️ `target_fasta`/`target_pdb`는 “파일 경로”가 아니라 “파일 내용(text)”을 JSON에 넣습니다.

추가 옵션:
- `run_id`: 지정 시 해당 ID로 결과 폴더를 생성/재사용합니다(단계별 디버깅/재실행에 유용).
- 입력은 `target_fasta` 또는 `target_pdb` 중 하나만 있어도 됩니다.
  - `target_pdb`만 주면, `ATOM` record에서 서열을 추출해 `MMseqs2`/보존도 계산에 사용합니다.
  - `target_pdb`가 없고 `stop_after!="msa"`면, `AlphaFold2`로 target 구조(`target.pdb`)를 먼저 만든 뒤 파이프라인을 실행합니다(필요: `ALPHAFOLD2_ENDPOINT_ID` 또는 `AF2_URL`).
- `af2_sequence_ids=["1"]`: AF2를 특정 design id들만 실행(전체 AF2가 너무 오래 걸릴 때 유용).
- `af2_model_preset="auto"`(기본): chain 개수(=design_chains)로 `monomer`/`multimer`를 자동 선택합니다. multi-chain design(`A/B/...`)은 AF2 입력을 multi-FASTA로 변환해 `/` 파싱 에러를 방지합니다.
  - `monomer` preset에서는 chain 전략을 일관되게 유지하기 위해 `design_chains`를 첫 체인 1개로 강제합니다(`chain_strategy.json`에 기록).
  - (고급) 멀티체인 서열을 monomer로 평가하면서 첫 체인만 쓰고 싶다면 `PIPELINE_AF2_MONOMER_FIRST_CHAIN=1`을 설정하세요(기본은 사전 차단).
- `force=true`: 기존 산출물이 있어도 해당 단계부터 다시 실행합니다.
- MSA 품질/필터:
  - `msa_min_coverage`: hit 서열의 non-gap coverage(0~1) 최소값. 설정 시 `msa/result.filtered.a3m`를 만들고 이후 보존도 계산은 filtered MSA를 사용합니다.
  - `msa_min_identity`: hit 서열의 query 일치율(0~1, matches/query_len) 최소값.
  - `msa/quality.json`에는 fragment 비율(coverage)과 depth(Neff 유사 지표)가 함께 저장되며, 너무 낮으면 `warnings`로 안내합니다.
- MMseqs2 실행(GPU/CPU):
  - `mmseqs_use_gpu=true|false`(기본은 `false`): GPU 사용 여부.
  - `pipeline-mcp`는 RunPod endpoint를 `MMSEQS_ENDPOINT_ID` 하나만 사용하며, GPU/CPU는 payload의 `mmseqs_use_gpu`로 분기합니다. 따라서 RunPod의 `Execution timeout`을 바꿨다면 **해당 endpoint**에 적용됐는지 확인하세요(다른 endpoint 설정을 바꿔도 영향 없음).
  - (주의) RunPod Serverless에서 CPU-only(`mmseqs_use_gpu=false`) + 대형 DB(`uniref90`)는 실행 시간이 길어 job timeout이 날 수 있습니다(필요 시 `mmseqs_max_seqs`를 줄이거나 더 작은 DB/전용 pod를 사용).
  - (주의) GPU 모드에서 “TSV의 UniRef ID가 엉뚱한 단백질로 보이는데 pident는 매우 높다” 같은 현상이 있으면 GPU padded DB에서 `convertalis/result2msa`를 잘못된 DB prefix로 돌려 **ID 매핑이 어긋난** 경우가 흔합니다. 이 경우 (1) `mmseqs_use_gpu=false`로 검증하거나, (2) `mmseqs-runpod` 이미지가 padded DB를 일관되게 사용하도록 업데이트되어 있는지 확인하세요(`mmseqs-runpod/README.md` 참고).
- FASTA↔PDB 일치성 체크:
  - `query_pdb_min_identity`(기본 0.9): PDB chain이 query와 얼마나 일치해야 하는지 (matches/query_len).
  - `query_pdb_policy`(기본 `error`): `error|warn|ignore`. 결과는 `query_pdb_alignment.json`에 저장됩니다.

기본 필터:
- SoluProt: `soluprot_cutoff=0.5`
- AlphaFold2: `af2_plddt_cutoff=85`, `af2_top_k=20`

## 알고리즘(보존도/ligand-mask/fixed_positions)

### 1) MSA(A3M) 정규화
- MMseqs2 결과 A3M에서 **첫 레코드가 query**입니다.
- A3M의 insertion 표기(소문자 `a-z`)는 제거(`strip`)한 뒤 계산합니다.
- 길이가 query와 다른 hit(정렬 길이 불일치)는 보존도/품질 계산에서 제외합니다.
- gap(`-`/`.`)은 해당 위치 통계에서 제외합니다.
- 산출물:
  - `msa/runpod_job.json`: RunPod `job_id` 및 요청 파라미터(재시도/재개용)
  - `msa/result.tsv`: MMseqs hit 요약
  - `msa/result.a3m`: MSA(A3M)
- 실행 중에는 `msa/runpod_job.json`만 존재할 수 있습니다. `result.tsv`/`result.a3m`은 RunPod job이 `COMPLETED`로 끝난 뒤에 생성됩니다.
- 재실행(resume):
  - 같은 `run_id`로 `force=false` 재실행 시, `msa/runpod_job.json`이 있고 파라미터(`mmseqs_target_db`, `mmseqs_max_seqs`, `mmseqs_threads`, `mmseqs_use_gpu`)가 동일하면 **새 RunPod job을 만들지 않고 기존 `job_id`를 재사용**해 완료까지 대기합니다.
  - 파라미터를 바꿔 재실행하려면 `force=true` 또는 새 `run_id` 사용을 권장합니다.
- RunPod status API가 일시적으로 `429/502/503/504`를 반환하더라도, pipeline은 backoff 재시도로 복구를 시도합니다.

### 2) 보존도 점수(conservation score)
각 position `i`에 대해 hit들이 제공한 **비-gap 아미노산 빈도 중 최대값**을 보존도로 사용합니다.

- `totals[i] = (# of hit residues at i; gap 제외)`
- `counts[i][AA] = (# of that AA at i)`
- `score[i] = max_AA counts[i][AA] / totals[i]` (값 범위: `0.0~1.0`)

이 점수는 `conservation.json`에 `scores`로 저장됩니다.

### 3) 30/50/70 tier가 의미하는 것(conservation_tiers)
`conservation_tiers=[0.3, 0.5, 0.7]`는 **“고정할 residue 비율(quantile)”** 또는 **“고정할 최소 보존도(threshold)”**로 해석됩니다.

- `conservation_mode="quantile"`(기본): 길이 `L`인 서열에서 `k=floor(L*tier)`개를 **보존도 점수 상위부터** 고정합니다(동점이면 position 번호가 작은 쪽 우선).
  - 예: `L=221`, `tier=0.3` → `k=66`개 고정
- `conservation_mode="threshold"`: `score[i] >= tier`인 position을 모두 고정합니다(이때 `tier`는 “비율”이 아니라 “빈도 임계값” 의미).

> 실행 로그/산출물에서 `tiers/30`, `tiers/50`, `tiers/70`는 각각 `0.3`, `0.5`, `0.7` tier를 의미합니다.  
> tier는 보통 **30→50→70 순서로 진행**되며, 중간 실패/중단(stop_after)에 따라 `tiers/30`만 존재할 수도 있습니다.

### 4) ligand 6Å mask는 어떻게 “제외(고정)”되나? (ligand_mask_distance)
파이프라인의 ligand mask는 PDB에서 ligand로 간주되는 원자들 주변(`ligand_mask_distance`, 기본 `6.0Å`)의 residue를 찾아 **ProteinMPNN에서 변이 대상에서 제외(=fixed)**합니다.

- ligand 원자 수집:
  - `HETATM` 레코드만 사용
  - 물(`HOH/WAT/H2O`)은 제외
  - 수소/중수소(`H/D`)는 제외(heavy atom만 사용)
  - 옵션 `ligand_resnames=["ACE", ...]`를 주면 해당 resname만 ligand로 사용(미지정 시 “물 제외 모든 HETATM”)
- residue 판정:
  - 각 residue의 heavy atom과 ligand heavy atom의 거리 중 **하나라도** `<= 6Å`이면 해당 residue를 mask에 포함
- 주의(번호 체계):
  - `ligand_mask.json`/`fixed_positions.json`에 기록되는 position은 **PDB의 resseq가 아니라 “체인 내 1-based index(ATOM 레코드 기준 순서)”**입니다.

또한 현재 구현은 **`HETATM`만 ligand로 인식**합니다. 따라서 PDB에 결합 파트너(예: peptide substrate)가 `ATOM` 체인으로 들어있다면(1LVM의 chain C/D처럼) 그 체인은 ligand mask 대상이 아닙니다.

### 5) tier별 fixed_positions 생성(보존도 + ligand mask)
각 tier에서 최종적으로 ProteinMPNN에 전달되는 `fixed_positions.json`은 아래를 합집합으로 만듭니다.

- `conservation.json`에서 선택된 tier별 고정 position(FASTA 기준)
- `ligand_mask.json`에서 선택된 위치(체인 index 기준)

FASTA와 PDB가 둘 다 제공된 경우, 보존도 position은 **FASTA(query)→PDB 체인 서열 정렬을 통해 체인 index로 매핑**한 뒤 합칩니다(`query_pdb_alignment.json` 참고).

### Active-site fixed list vs (ligand mask + 보존도)의 차이
논문에서 말하는 “active-site residue list 고정”과 본 파이프라인의 “ligand mask + 보존도 고정”은 목적과 근거가 다릅니다.

- **Active-site fixed list(논문 방식)**: 사람이 지정한 기능성 residue(촉매/결합/특이성 관련)를 고정합니다. MSA나 ligand 존재 여부와 무관하게 “기능 유지”를 강하게 보장합니다.
- **보존도 fixed(파이프라인)**: MSA에서 **서열적으로 가장 보존된 위치**를 고정합니다. 구조 안정성에 중요한 residue가 잡히는 경향은 있지만, 기능성(active site)이 반드시 포함된다는 보장은 없습니다.
- **Ligand mask fixed(파이프라인)**: 구조에서 ligand(=HETATM) 주변을 고정합니다. 결합 상태가 PDB에 어떻게 들어있느냐에 영향을 크게 받습니다(위의 HETATM/ATOM 차이 포함).

즉, 논문처럼 “active-site + 30/50/70% 보존도”를 재현하려면, (1) 동일한 번호 체계/서열 범위를 맞추고(예: tag 포함 여부), (2) active-site 고정 리스트를 별도로 병합해야 합니다. 현재 `pipeline.run` API는 active-site 리스트를 직접 입력받아 자동 병합하는 옵션은 제공하지 않습니다.

#### 각 방식의 장단점(요약)
- **Active-site 리스트 고정**: 기능 핵심 잔기를 사람이 지정해 강하게 보호(재현성/해석 용이)하지만, 번호 체계(태그/삽입코드/체인) 정합이 필요하고 “리스트 밖”의 중요한 잔기(구조 안정/원거리 네트워크)를 놓칠 수 있습니다.
- **Ligand 6Å mask 고정**: PDB 구조 기반으로 결합부 주변을 자동 보호(자동화/구조-기반)하지만, `HETATM`에 의존하며(리간드가 `ATOM` 체인으로 들어오면 미검출), 6Å는 휴리스틱이라 결합부가 과소/과대 고정될 수 있습니다.
- **MSA 보존도 tier 고정(quantile 0.3/0.5/0.7)**: 데이터(진화적 제약)에 기반해 구조/기능에 중요한 위치를 넓게 보호(자동화/확장성)하지만, MSA 품질에 민감하며(잘못된 MSA면 fixed_positions도 왜곡), 고정 비율이 커질수록 설계 자유도가 줄어듭니다.
- **현재 파이프라인의 병합 방식**: tier별 고정보존 잔기와 ligand 6Å mask를 **합집합**으로 `fixed_positions.json`에 기록하고, ProteinMPNN은 이 위치들을 “변이 금지(=native 고정)”로 처리합니다.

## 단계별 실행(run_id로 이어서 실행)
`pipeline.run`은 기본적으로 동기(blocking)입니다. MMseqs/AF2는 오래 걸릴 수 있으니, 아래처럼 `stop_after`로 잘라서 같은 `run_id`로 이어서 실행하는 방식을 권장합니다.

```bash
SERVER=http://<SERVER_IP>:18080
RUN_ID=intein_test_001
```

### 1) MSA만 실행(MMseqs2)
`stop_after="msa"`인 경우 `target_pdb` 없이도 실행됩니다.

```bash
jq -n --arg run_id "$RUN_ID" --rawfile fasta ./target.fasta \
  '{name:"pipeline.run", arguments:{run_id:$run_id, target_fasta:$fasta, stop_after:"msa", mmseqs_target_db:"uniref90", mmseqs_max_seqs:3000}}' \
| curl -sS -X POST "$SERVER/tools/call" -H 'Content-Type: application/json' -d @- | jq .
```

### 2) design까지(ProteinMPNN)
```bash
jq -n --arg run_id "$RUN_ID" --rawfile fasta ./target.fasta --rawfile pdb ./target.pdb \
  '{name:"pipeline.run", arguments:{run_id:$run_id, target_fasta:$fasta, target_pdb:$pdb, stop_after:"design", conservation_tiers:[0.3,0.5,0.7], num_seq_per_tier:16}}' \
| curl -sS -X POST "$SERVER/tools/call" -H 'Content-Type: application/json' -d @- | jq .
```

(PDB만 있는 경우)
```bash
jq -n --arg run_id "$RUN_ID" --rawfile pdb ./target.pdb \
  '{name:"pipeline.run", arguments:{run_id:$run_id, target_pdb:$pdb, stop_after:"design", conservation_tiers:[0.3,0.5,0.7], num_seq_per_tier:16}}' \
| curl -sS -X POST "$SERVER/tools/call" -H 'Content-Type: application/json' -d @- | jq .
```

### 3) soluprot까지
```bash
jq -n --arg run_id "$RUN_ID" --rawfile fasta ./target.fasta --rawfile pdb ./target.pdb \
  '{name:"pipeline.run", arguments:{run_id:$run_id, target_fasta:$fasta, target_pdb:$pdb, stop_after:"soluprot", soluprot_cutoff:0.5}}' \
| curl -sS -X POST "$SERVER/tools/call" -H 'Content-Type: application/json' -d @- | jq .
```

### 4) af2까지
```bash
jq -n --arg run_id "$RUN_ID" --rawfile fasta ./target.fasta --rawfile pdb ./target.pdb \
  '{name:"pipeline.run", arguments:{run_id:$run_id, target_fasta:$fasta, target_pdb:$pdb, stop_after:"af2", af2_plddt_cutoff:85, af2_top_k:20}}' \
| curl -sS -X POST "$SERVER/tools/call" -H 'Content-Type: application/json' -d @- | jq .
```

### 진행상태 확인(폴링)
```bash
curl -sS -X POST "$SERVER/tools/call" -H 'Content-Type: application/json' \
  -d "$(jq -n --arg run_id "$RUN_ID" '{name:\"pipeline.status\", arguments:{run_id:$run_id}}')" | jq .
```

### Windows PowerShell에서 `/tools/call` 호출하기(HTTP 400 방지)
PowerShell에서 `ConvertTo-Json`을 2번 하거나, `-Body`에 JSON이 아닌 문자열이 섞이면 서버가 **“JSON object”**로 못 읽어서 HTTP 400이 납니다.

- `-Body`에는 **JSON 문자열만** 넣고,
- 출력 prettify는 `Invoke-RestMethod` 뒤에 `| ConvertTo-Json -Depth 50`로 하세요.
- `Get-Content -Raw` 결과는 `[string]`으로 캐스팅해서 JSON에 넣는 것을 권장합니다.
- (curl로 `-d @file`을 쓰는 경우) Windows PowerShell 5.1의 `Set-Content -Encoding utf8`는 BOM(UTF-8 with BOM)이 붙을 수 있어 JSON 파싱 에러가 날 수 있습니다. 이런 경우 `[IO.File]::WriteAllText($path, $json, [Text.UTF8Encoding]::new($false))`로 **no-BOM** UTF-8로 쓰세요.

예시: status
```powershell
$server='http://<SERVER_IP>:18080/tools/call'
$run_id='intein_test_001'
$body=@{name='pipeline.status'; arguments=@{run_id=$run_id}} | ConvertTo-Json -Depth 10
Invoke-RestMethod -Uri $server -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 50
```

예시: MSA만 실행(CPU 강제)
```powershell
$server='http://<SERVER_IP>:18080/tools/call'
$run_id='intein_msa_001'
$fasta=[string](Get-Content -Raw -Encoding utf8 'C:\path\to\target.fasta')

$body=@{name='pipeline.run'; arguments=@{
  run_id=$run_id
  target_fasta=$fasta
  stop_after='msa'
  mmseqs_target_db='uniref90'
  mmseqs_max_seqs=300
  mmseqs_threads=8
  mmseqs_use_gpu=$false
}} | ConvertTo-Json -Depth 10

Invoke-RestMethod -Uri $server -Method Post -ContentType 'application/json' -Body $body | ConvertTo-Json -Depth 50
```

## MCP 사용(VS Code Copilot / Codex CLI)
Copilot/Codex의 MCP 기능은 “stdio(JSON-RPC)” 서버를 실행해 붙는 방식이 가장 안정적입니다. 이 레포에는 stdio MCP 서버가 포함되어 있습니다:

```bash
# repo root에서 (권장: 크로스플랫폼, `.env` 자동 로드)
python pipeline-mcp/scripts/mcp_stdio_server.py

# 또는 pipeline-mcp/ 폴더에서
python scripts/mcp_stdio_server.py
```

TIP: `pipeline-mcp/scripts/mcp_stdio_server.py`는 `pipeline-mcp/.env`를 자동 로드하고 `PYTHONPATH`도 내부에서 설정합니다.

(처음 1회) 의존성: `python -m pip install -r pipeline-mcp/requirements.txt`

⚠️ `pipeline.run`은 동기(blocking)라서 MMseqs/AF2가 오래 걸릴 수 있습니다. Copilot/Codex에서도 `stop_after` + `run_id`로 단계별 실행을 권장합니다.

### 이미 실행 중인 HTTP 서버에 붙이기(프록시)
NCP 등에 `pipeline_mcp.http_server`를 띄워두고(예: `http://<SERVER_IP>:18080`) 로컬에서 MCP로 붙고 싶다면, stdio MCP 프록시를 사용하세요:

```bash
python pipeline-mcp/scripts/mcp_http_proxy_server.py --base-url http://<SERVER_IP>:18080
```

### VS Code (Copilot Chat)
VS Code를 NCP 서버에 Remote SSH로 붙여서(서버에서 명령 실행) 설정하는 방식을 권장합니다.

`.vscode/mcp.json` 예시(워크스페이스 루트 기준 경로):
```json
{
  "servers": {
    "protein-pipeline": {
      "command": "python",
      "args": ["pipeline-mcp/scripts/mcp_stdio_server.py"]
    }
  }
}
```

이미 실행 중인 HTTP 서버에 붙일 땐 `args`를 아래로 교체하세요:
`["pipeline-mcp/scripts/mcp_http_proxy_server.py", "--base-url", "http://<SERVER_IP>:18080"]`

리눅스 Remote SSH 환경에서 `python`이 없거나 `python3`만 있는 경우 `command`를 `python3`로 바꾸세요.

워크스페이스를 repo root가 아니라 `pipeline-mcp/` 폴더로 열었다면 `args`를 `["scripts/mcp_stdio_server.py"]`로 바꾸세요.

Copilot Chat에서 사용 예:
- “`pipeline.run`을 `run_id=intein_test_001`, `stop_after=msa`로 실행해줘.”
- “`pipeline.status`로 `run_id=...` 상태 보여줘.”

### Codex CLI
Codex에 MCP 서버를 등록:
```bash
codex mcp add protein-pipeline -- python <ABS_PATH_TO_REPO>/pipeline-mcp/scripts/mcp_stdio_server.py
# (HTTP 프록시) codex mcp add protein-pipeline -- python <ABS_PATH_TO_REPO>/pipeline-mcp/scripts/mcp_http_proxy_server.py --base-url http://<SERVER_IP>:18080
codex mcp list
```

주의: Codex CLI는 상대경로를 쓰면 실행 위치에 따라 실패할 수 있어, 스크립트 경로는 절대경로를 권장합니다.

## 산출물 위치
기본적으로 `PIPELINE_OUTPUT_ROOT/<run_id>/`에 저장됩니다.
- `request.json`, `status.json`, `events.jsonl`, `summary.json`
- `target.fasta`, `target.pdb`
- `chain_strategy.json`
- `msa/result.tsv`, `msa/result.a3m`
- `msa/quality.json`, `msa/result.filtered.a3m`(옵션)
- `conservation.json`, `ligand_mask.json`
- `query_pdb_alignment.json`
- `tiers/<tier>/fixed_positions.json`, `tiers/<tier>/fixed_positions_check.json`, `tiers/<tier>/designs.fasta`, `tiers/<tier>/proteinmpnn.json`
- `tiers/<tier>/soluprot.json`, `tiers/<tier>/designs_filtered.fasta`
- `tiers/<tier>/af2_scores.json`, `tiers/<tier>/af2_selected.fasta`, `tiers/<tier>/af2/<seq_id>/*`

### ProteinMPNN fixed_positions check
- 기본적으로 `tiers/<tier>/fixed_positions_check.json`를 저장하고, fixed_positions 위반이 감지되면 run을 실패 처리합니다.
- 필요 시 `PIPELINE_SKIP_FIXED_POSITIONS_CHECK=1` 로 비활성화할 수 있습니다.
