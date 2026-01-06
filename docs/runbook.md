# Protein Pipeline 운영 가이드 (NCP)

이 저장소의 `pipeline-mcp`는 파이프라인 오케스트레이터(HTTP tool server)이며, 실제 연산은 주로 RunPod 엔드포인트(MMseqs2/ProteinMPNN/AF2)를 호출합니다.

## 권장 포트
- `18080`: `pipeline-mcp` HTTP 서버(외부 호출 필요 시에만 공개)
- `18081`: SoluProt 점수 서버(권장: `127.0.0.1` 바인드로 내부에서만 사용)
- `18082`: (선택) AF2 HTTP 서버(직접 운영 시)

## 환경변수
필수:
- `RUNPOD_API_KEY`
- `MMSEQS_ENDPOINT_ID`
- `PROTEINMPNN_ENDPOINT_ID`

선택:
- `ALPHAFOLD2_ENDPOINT_ID` (RunPod AF2 사용 시)
- `AF2_URL` (RunPod AF2 미사용 시, 별도 AF2 HTTP 서버)
- `SOLUPROT_URL` (SoluProt HTTP 서버; 미설정 시 soluprot 단계 자동 스킵)
- `PIPELINE_OUTPUT_ROOT` (기본: `outputs`)

## `pipeline-mcp` 실행/중지 (nohup)
```bash
cd /opt/protein_pipeline/pipeline-mcp
mkdir -p /opt/protein_pipeline/logs /opt/protein_pipeline/outputs

# (권장) 환경변수는 파일로 관리(시크릿 보호)
cat > .env <<'EOF'
RUNPOD_API_KEY=...
MMSEQS_ENDPOINT_ID=...
PROTEINMPNN_ENDPOINT_ID=...
ALPHAFOLD2_ENDPOINT_ID=...
SOLUPROT_URL=http://127.0.0.1:18081/score
PIPELINE_OUTPUT_ROOT=/opt/protein_pipeline/outputs
EOF
chmod 600 .env

PORT=18080
set -a; source .env; set +a
PYTHONPATH=src nohup python3 -m pipeline_mcp.http_server --host 0.0.0.0 --port "$PORT" \
  > "/opt/protein_pipeline/logs/pipeline-mcp_${PORT}.log" 2>&1 & \
  echo $! > "/opt/protein_pipeline/logs/pipeline-mcp_${PORT}.pid"
```

헬스체크:
```bash
curl -sS http://127.0.0.1:18080/healthz; echo
curl -sS -X POST http://127.0.0.1:18080/tools/list -H 'Content-Type: application/json' -d '{}' ; echo
```

중지:
```bash
kill "$(cat /opt/protein_pipeline/logs/pipeline-mcp_18080.pid)" 2>/dev/null || true
rm -f /opt/protein_pipeline/logs/pipeline-mcp_18080.pid
```

## 파이프라인 호출(원격에서)
`target_fasta`/`target_pdb`는 “파일 경로”가 아니라 “파일 내용(text)”을 JSON에 넣어 호출합니다.

```bash
jq -n --rawfile fasta ./target.fasta --rawfile pdb ./target.pdb \
  '{name:"pipeline.run", arguments:{target_fasta:$fasta, target_pdb:$pdb, stop_after:"design"}}' \
| curl -sS -X POST http://<SERVER_IP>:18080/tools/call -H 'Content-Type: application/json' -d @- | jq .
```

상태 확인:
```bash
RUN_ID=...
curl -sS -X POST http://<SERVER_IP>:18080/tools/call -H 'Content-Type: application/json' \
  -d "$(jq -n --arg run_id "$RUN_ID" '{name:"pipeline.status", arguments:{run_id:$run_id}}')" | jq .
```

결과물은 서버 내부의 `PIPELINE_OUTPUT_ROOT/<run_id>/`에 저장됩니다.

## SoluProt 서버(선택)
SoluProt은 점수만 계산해 필터링하므로 RunPod가 필수는 아닙니다. 이 서버(NCP)에 HTTP로 띄우고 `SOLUPROT_URL`만 설정하면 됩니다.

`pipeline-mcp`가 기대하는 API 형식:
- 요청: `POST $SOLUPROT_URL` `{"sequences":[{"id":"...","sequence":"..."}]}`
- 응답: `{"results":[{"id":"...","score":0.73}, ...]}`

권장 운영:
- 포트 `18081`
- 바인드 `127.0.0.1`(외부 공개 불필요)

### 이 저장소에 포함된 간이 SoluProt 서버 실행(권장, 18081)
이 저장소에는 `pipeline_mcp.soluprot_server`(간이 점수 서버)가 포함되어 있습니다.

```bash
cd /opt/protein_pipeline/pipeline-mcp
mkdir -p /opt/protein_pipeline/logs

PORT=18081
PYTHONPATH=src nohup python3 -m pipeline_mcp.soluprot_server --host 127.0.0.1 --port "$PORT" \
  > "/opt/protein_pipeline/logs/soluprot_${PORT}.log" 2>&1 & \
  echo $! > "/opt/protein_pipeline/logs/soluprot_${PORT}.pid"

curl -sS http://127.0.0.1:18081/healthz; echo
curl -sS -X POST http://127.0.0.1:18081/score -H 'Content-Type: application/json' \
  -d '{"sequences":[{"id":"s1","sequence":"ACDEFGHIK"}]}' ; echo
```

중지:
```bash
kill "$(cat /opt/protein_pipeline/logs/soluprot_18081.pid)" 2>/dev/null || true
rm -f /opt/protein_pipeline/logs/soluprot_18081.pid
```

## 보안 권장사항
`pipeline-mcp`는 기본적으로 인증이 없습니다. `0.0.0.0:18080`을 외부에 공개하면 누구나 `/tools/call`로 실행(과금/리소스 사용)할 수 있습니다.
- 가능하면 `--host 127.0.0.1`로 실행하고 SSH 터널/리버스 프록시(인증)로만 접근
- 또는 방화벽으로 접근 IP 제한
