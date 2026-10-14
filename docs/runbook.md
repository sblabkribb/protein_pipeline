# Protein Pipeline 운영 가이드 (NCP)

이 저장소의 `pipeline-mcp`는 파이프라인 오케스트레이터(HTTP tool server)이며, 실제 연산은 주로 RunPod 엔드포인트(MMseqs2/ProteinMPNN/AF2)를 호출합니다. ProteinMPNN만 NCP GPU 서버로 옮길 때는 `docs/gpu_proteinmpnn_worker.md`를 따릅니다.

## 권장 포트
- `18080`: `pipeline-mcp` HTTP 서버(Caddy가 `https://pipeline.k-biofoundrycopilot.duckdns.org/mcp`와 `/api/*`로 프록시)
- `18081`: SoluProt 점수 서버(권장: `127.0.0.1` 바인드로 내부에서만 사용)
- `18082`: (선택) AF2 HTTP 서버(직접 운영 시)

## 환경변수
필수:
- `RUNPOD_API_KEY`
- `MMSEQS_ENDPOINT_ID`
- `PROTEINMPNN_ENDPOINT_ID` (`PROTEINMPNN_PROVIDER=runpod`일 때)

선택:
- `PROTEINMPNN_PROVIDER=gpu_http` (ProteinMPNN을 자체 GPU worker로 실행)
- `PROTEINMPNN_GPU_URL` (`PROTEINMPNN_PROVIDER=gpu_http`일 때 필수)
- `PROTEINMPNN_GPU_TOKEN` (GPU worker bearer token)
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

# (원격에서 확인: 공용 도메인은 Caddy/SSO 뒤로만 접근)
SERVER=https://pipeline.k-biofoundrycopilot.duckdns.org
TOKEN=<KBF_SSO_ACCESS_TOKEN>
curl -ksS "$SERVER/healthz"; echo
curl -ksS -X POST "$SERVER/mcp" \
  -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | jq .
```

중지:
```bash
kill "$(cat /opt/protein_pipeline/logs/pipeline-mcp_18080.pid)" 2>/dev/null || true
rm -f /opt/protein_pipeline/logs/pipeline-mcp_18080.pid
```

## 파이프라인 호출(원격에서)
원격 MCP 클라이언트는 `https://pipeline.k-biofoundrycopilot.duckdns.org/mcp`에 붙습니다. 아래 `curl` 예시는 운영/디버깅용 direct HTTP tool API 예시입니다.

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
`run_id`를 지정하면 같은 폴더를 재사용할 수 있지만, 현재 기준으로는 “같은 request를 뒤 단계까지 이어서 실행”할 때만 같은 `run_id` 재사용을 권장합니다.

- 안전한 경우:
  - 같은 `target_fasta`/`target_pdb`
  - 같은 backbone 입력(RFD3/BioEmu 관련 설정 포함)
  - 같은 `design_chains`/`fixed_positions_extra`
  - orchestration 목적의 변경만 있음 (`stop_after`, `start_from`, 일부 downstream 설정)
- 안전하지 않은 경우:
  - target/chain/backbone 입력을 바꿨는데 late stage만 다시 돌리는 경우
  - 이때는 새 `run_id`를 쓰거나 `start_from="msa"`로 다시 시작해야 합니다.
- backend는 unsafe partial rerun을 거부하며, UI도 기본값을 새 run fork로 둡니다.

```bash
RUN_ID=test_intein_001
jq -n --arg run_id "$RUN_ID" --rawfile fasta ./target.fasta --rawfile pdb ./target.pdb \
  '{name:"pipeline.run", arguments:{run_id:$run_id, target_fasta:$fasta, target_pdb:$pdb, stop_after:"design"}}' \
| curl -sS -X POST http://<SERVER_IP>:18080/tools/call -H 'Content-Type: application/json' -d @- | jq .
```

예를 들어 같은 request로 AF2 이후만 다시 돌리고 싶다면 `start_from`을 명시해 같은 run을 이어갈 수 있습니다.

```bash
RUN_ID=test_intein_001
jq -n --arg run_id "$RUN_ID" --rawfile fasta ./target.fasta --rawfile pdb ./target.pdb \
  '{name:"pipeline.run", arguments:{run_id:$run_id, target_fasta:$fasta, target_pdb:$pdb, start_from:"af2", stop_after:"novelty"}}' \
| curl -sS -X POST http://<SERVER_IP>:18080/tools/call -H 'Content-Type: application/json' -d @- | jq .
```

상태 확인:
```bash
RUN_ID=...
curl -sS -X POST http://<SERVER_IP>:18080/tools/call -H 'Content-Type: application/json' \
  -d "$(jq -n --arg run_id "$RUN_ID" '{name:"pipeline.status", arguments:{run_id:$run_id}}')" | jq .
```

결과물은 서버 내부의 `PIPELINE_OUTPUT_ROOT/<run_id>/`에 저장됩니다. 비교/분석용 요약은 `summary.json`, `comparisons.json`, `report.md`, `report_ko.md` 등을 보면 됩니다.

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

### SoluProt 채점 서버 실행(18081)

`pipeline_mcp.soluprot_server` 는 정품 SoluProt 1.0.1.0(Hon et al. 2021)을 호출하는
HTTP 서버입니다. SoluProt 자체는 Python 3.7 과 scikit-learn 0.20.1 을 요구하므로 별도
환경에 설치하고, 서버는 그 환경의 인터프리터를 하위 프로세스로 실행합니다. TMHMM 은
별도 학술 등록이 필요하므로 저자가 함께 배포하는 TMHMM 비의존 모델
`grad_clf_v1_tc_notmhmm` 을 사용합니다.

설치 위치는 환경 변수로 지정합니다.

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `SOLUPROT_DIR` | `/opt/soluprot_dl/extracted/soluprot-1.0.1.0` | `soluprot.py` 가 있는 디렉터리 |
| `SOLUPROT_PYTHON` | `/opt/soluprot_env/mamba/envs/soluprot/bin/python` | SoluProt 전용 환경의 인터프리터 |
| `SOLUPROT_USEARCH` | `/opt/soluprot_env/tools/usearch11` | 서열 동일성 특징에 쓰는 USEARCH |
| `SOLUPROT_CACHE` | `/opt/soluprot_env/cache/scores.sqlite3` | 서열별 점수 캐시 |
| `SOLUPROT_PROCS` | `2` | SoluProt 에 넘기는 작업 프로세스 수 |
| `SOLUPROT_CHUNK` | `256` | 하위 프로세스 한 번에 넘기는 서열 수 |
| `SOLUPROT_TIMEOUT` | `1800` | 하위 프로세스 하나에 허용하는 시간(초) |

운영에서는 `protein-soluprot.service` 가 위 변수를 지정해 이 서버를 띄웁니다.

```bash
systemctl restart protein-soluprot.service
curl -sS http://127.0.0.1:18081/healthz; echo
curl -sS -X POST http://127.0.0.1:18081/score -H 'Content-Type: application/json' \
  -d '{"sequences":[{"id":"s1","sequence":"MKVLAAGIVLGSTQWRDPLLNKACFGHIYE"}]}' ; echo
```

동작상 알아 둘 점이 두 가지 있습니다. 첫째, 20 잔기 미만 서열은 SoluProt 의 적용
범위를 벗어나므로 점수 대신 `score: null` 과 사유를 돌려줍니다. 짧은 서열이 하나라도
섞이면 SoluProt 이 배치 전체를 거부하기 때문에 서버가 미리 걸러냅니다. 둘째, 채점에
실패하면 추정값을 만들어 내지 않고 503 과 오류 내용을 돌려줍니다.

설치가 갖추어지지 않으면 서버는 기동하지 않고 종료 코드 2 로 끝나며, `/healthz` 는
설치 문제 목록을 함께 보고합니다.

## 보안 권장사항
운영에서는 raw port를 외부에 직접 열지 않는 것을 권장합니다.
- `pipeline-mcp`는 `127.0.0.1:18080` 또는 내부망에만 두고, 공용 접근은 Caddy + OIDC가 붙은 `https://pipeline.k-biofoundrycopilot.duckdns.org/mcp`로만 노출
- 내부 `/tools/*` API를 외부에 직접 열면 인증 우회나 오동작 위험이 커집니다. 가능하면 reverse proxy 뒤로만 두세요.

## UI + Nginx (Docker)
프론트엔드를 5173/443에 고정으로 올리고 `/api/`를 pipeline-mcp로 프록시합니다.

```bash
cd /opt/protein_pipeline/deploy/nginx
# TLS certs: certs/fullchain.pem + certs/privkey.pem
docker compose -f docker-compose.frontend.yml up -d
```

프론트엔드에서 API 베이스는 기본적으로 `/api`를 사용합니다.
