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
disown || true
```

헬스체크:
```bash
# (서버 내부에서 확인)
curl -sS http://127.0.0.1:18080/healthz; echo
curl -sS -X POST http://127.0.0.1:18080/tools/list -H 'Content-Type: application/json' -d '{}' ; echo

# (원격에서 확인: 서버 IP/도메인으로 접근)
SERVER=http://<SERVER_IP>:18080
curl -sS "$SERVER/healthz"; echo
curl -sS -X POST "$SERVER/tools/list" -H 'Content-Type: application/json' -d '{}' ; echo
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

### MSA만 테스트(= RunPod MMseqs2 연동 확인)
`stop_after="msa"`인 경우 `target_pdb` 없이도 실행됩니다.

```bash
jq -n --rawfile fasta ./target.fasta \
  '{name:"pipeline.run", arguments:{target_fasta:$fasta, stop_after:"msa", mmseqs_max_seqs:50}}' \
| curl -sS -X POST http://<SERVER_IP>:18080/tools/call -H 'Content-Type: application/json' -d @- | jq .
```

### run_id 지정(재실행/폴링에 유용)
`run_id`를 지정하면 같은 폴더를 재사용하며(`force=false` 기본) 단계별로 `stop_after`를 바꿔 재실행할 수 있습니다.

```bash
RUN_ID=test_intein_001
jq -n --arg run_id "$RUN_ID" --rawfile fasta ./target.fasta --rawfile pdb ./target.pdb \
  '{name:"pipeline.run", arguments:{run_id:$run_id, target_fasta:$fasta, target_pdb:$pdb, stop_after:"design"}}' \
| curl -sS -X POST http://<SERVER_IP>:18080/tools/call -H 'Content-Type: application/json' -d @- | jq .
```

상태 확인:
```bash
RUN_ID=...
curl -sS -X POST http://<SERVER_IP>:18080/tools/call -H 'Content-Type: application/json' \
  -d "$(jq -n --arg run_id "$RUN_ID" '{name:"pipeline.status", arguments:{run_id:$run_id}}')" | jq .
```

결과물은 서버 내부의 `PIPELINE_OUTPUT_ROOT/<run_id>/`에 저장됩니다.

## 단계별 오케스트레이션(= protein-pipeline-stepper 방식)
Codex 스킬 `protein-pipeline-stepper`는 `pipeline.status`로 상태를 게이트한 뒤 `pipeline.run(stop_after=...)`를 단계별로 호출해 중복 job을 방지합니다.

- 재현 가능한 curl 명령어/폴링 루프/디버깅 포인트: `docs/stepper_orchestration.md`

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
disown || true

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

## UI + Nginx (Docker)
프론트엔드를 5173/443에 고정으로 올리고 `/api/`를 pipeline-mcp로 프록시합니다.

```bash
cd /opt/protein_pipeline/deploy/nginx
# TLS certs: certs/fullchain.pem + certs/privkey.pem
docker compose -f docker-compose.frontend.yml up -d
```

프론트엔드에서 API 베이스는 기본적으로 `/api`를 사용합니다.
