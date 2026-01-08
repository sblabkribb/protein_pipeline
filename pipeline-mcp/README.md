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
- `stop_after="msa"` 또는 `dry_run=true`인 경우 `target_pdb` 없이도 실행 가능합니다.
- `force=true`: 기존 산출물이 있어도 해당 단계부터 다시 실행합니다.

기본 필터:
- SoluProt: `soluprot_cutoff=0.5`
- AlphaFold2: `af2_plddt_cutoff=85`, `af2_top_k=20`

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

## MCP 사용(VS Code Copilot / Codex CLI)
Copilot/Codex의 MCP 기능은 “stdio(JSON-RPC)” 서버를 실행해 붙는 방식이 가장 안정적입니다. 이 레포에는 stdio MCP 서버가 포함되어 있습니다:

```bash
cd /opt/protein_pipeline/pipeline-mcp
set -a && source .env && set +a
PYTHONPATH=src python3 -m pipeline_mcp.mcp_stdio_server
```

⚠️ `pipeline.run`은 동기(blocking)라서 MMseqs/AF2가 오래 걸릴 수 있습니다. Copilot/Codex에서도 `stop_after` + `run_id`로 단계별 실행을 권장합니다.

### VS Code (Copilot Chat)
VS Code를 NCP 서버에 Remote SSH로 붙여서(서버에서 명령 실행) 설정하는 방식을 권장합니다.

`.vscode/mcp.json` 예시:
```json
{
  "servers": {
    "protein-pipeline": {
      "command": "bash",
      "args": [
        "-lc",
        "cd /opt/protein_pipeline/pipeline-mcp && set -a && source .env && set +a && PYTHONPATH=src python3 -m pipeline_mcp.mcp_stdio_server"
      ]
    }
  }
}
```

Copilot Chat에서 사용 예:
- “`pipeline.run`을 `run_id=intein_test_001`, `stop_after=msa`로 실행해줘.”
- “`pipeline.status`로 `run_id=...` 상태 보여줘.”

### Codex CLI
Codex에 MCP 서버를 등록:
```bash
codex mcp add protein-pipeline -- bash -lc 'cd /opt/protein_pipeline/pipeline-mcp && set -a && source .env && set +a && PYTHONPATH=src python3 -m pipeline_mcp.mcp_stdio_server'
codex mcp list
```

## 산출물 위치
기본적으로 `PIPELINE_OUTPUT_ROOT/<run_id>/`에 저장됩니다.
- `request.json`, `status.json`, `summary.json`
- `msa/result.tsv`, `msa/result.a3m`
- `conservation.json`, `ligand_mask.json`
- `tiers/<tier>/fixed_positions.json`, `tiers/<tier>/designs.fasta`, `tiers/<tier>/proteinmpnn.json`
- `tiers/<tier>/soluprot.json`, `tiers/<tier>/designs_filtered.fasta`
- `tiers/<tier>/af2_scores.json`, `tiers/<tier>/af2_selected.fasta`, `tiers/<tier>/af2/<seq_id>/*`
