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

기본 필터:
- SoluProt: `soluprot_cutoff=0.5`
- AlphaFold2: `af2_plddt_cutoff=85`, `af2_top_k=20`
