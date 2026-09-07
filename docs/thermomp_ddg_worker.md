# ThermoMPNN ddG 워커 (bop:18114)

ThermoMPNN (Kuhlman-Lab, MIT) 을 bop GPU 서버에 HTTP 워커로 띄우고, RAPID 의
안정성(stability) 평가자와 biomodel.kbiofoundry.kr 포털에 붙인 배치 기록.

## 이 모델이 주는 값과 한계

- 단일 점변이의 **ΔΔG (kcal/mol, 접힘 기준)**. 양수 = 불안정화
  (ΔG_mutant − ΔG_wildtype).
- 학습 코호트는 FireProtDB/MegaScale (실험 포인트 변이). **de-novo 백본이나
  다중 변이 설계에는 맞춰본 적이 없다** — RAPID 레지스트리에서
  `thermomp_ddg` 는 `wired_unvalidated` 다.
- 다중 변이 설계에는 각 변이의 단일-변이 예측을 **더한 가법 합**을 기록한다.
  에피스테이시스를 무시하는 근사다.
- RAPID 는 이 값을 게이트로 쓰지 않는다. 기록만 한다. 게이트로 쓰려면 알려진
  안정성 순위 코호트와의 대조(`to_enable`)가 먼저다.

## bop 배치 상태 (2026-09-07 설치 완료)

| 항목 | 값 |
|---|---|
| systemd 유닛 | `protein-model-thermomp-ddg.service` (root 유닛, `User=pipeline`) |
| 포트 | TCP 18114 (`0.0.0.0`, **NCP ACG 허용 대기 중** — RAPID 외부 직접 호출에 필요) |
| 소스 | `/home/pipeline/models/src/ThermoMPNN` (git clone, 가중치 포함) |
| venv | `/home/pipeline/models/venvs/thermomp` (torch cu130 + pytorch_lightning) |
| 워커 스크립트 | `deploy/gpu/thermomp_ddg_http_worker.py` + `deploy/gpu/thermomp_predict.py` |
| GPU | `CUDA_VISIBLE_DEVICES=1` (L40S #2) |

검증: 업스트림 레퍼런스 `examples/ThermoMPNN_inference_2OCJ.csv` 와 전체 스캔
대조 — 겹치는 3,686개 예측 전부 1e-3 이내 일치 (0 불일치). 레퍼런스에는 C 로의
변이가 빠져 있어 행 수는 다르다 (3880 vs 3686).

## RAPID 연동

- 클라이언트: `pipeline_mcp/clients/thermomp.py` (`LocalHTTPThermoMPNNClient`).
- provider env: `THERMOMP_HTTP_URL` (+선택 `THERMOMP_HTTP_TOKEN`,
  `THERMOMP_HTTP_TIMEOUT_S`) 또는 `THERMOMP_ENDPOINT_ID` (RunPod 호환 게이트웨이
  경유 — `RUNPOD_API_BASE`/provider `api_base` 와 조합).
- 파이프라인: `relax_enabled=true` 실행에서 AF2 구조가 있는 설계마다
  native 대비 변이 목록을 만들어 워커로 돌리고, per-mutation ΔΔG 와 가법 합을
  `tiers/<tier>/relax/<seq>/metrics.json` 의 `thermomp` 키와
  `tiers/<tier>/relax_scores.json` 의 `thermomp` 맵에 기록한다. 평가자가
  설정되지 않으면 아무 일도 일어나지 않는다 (opt-in).
- 같은 relax 아티팩트에 `delta_reu_vs_wt` (Rosetta relax, 같은 백본 한정 상대
  비교) 도 함께 기록된다. `comparability: same_backbone_only`.

## biomodel.kbiofoundry.kr 포털 연동

- gateway `endpoints.yaml` 에 `thermomp-ddg-local` (worker_url
  `http://127.0.0.1:18114` — 게이트웨이와 같은 호스트라 루프백, ACG 불필요).
- adapter `thermomp` (`gateway/prep/thermomp.py`): inline `pdb_content` /
  `input_pdb_content` / `pdb_base64` 또는 `input_archive` 에서 PDB 추출.
- 포털 카탈로그에 `ThermoMPNN ddG` 파이프라인 추가 (docking 카테고리, 변이
  목록/사슬/top_n 입력 필드). 백엔드 env `THERMOMP_DDG_ENDPOINT_ID=thermomp-ddg-local`.
- 배포 시 주의: bop 라이브 게이트웨이의 `prep/`, `bio/` 패키지가 빠져 있어서
  prep 기반 adapter 전체가 호출 시점에 깨지는 상태였다. 이 배치에서 함께
  동기화해 복구했다.

## RAPID ↔ gateway (RunPod 호환) 소비

RunPodClient 가 이제 `api_base` 를 받는다 (`RUNPOD_API_BASE` 환경변수 또는
provider store 레코드의 `api_base`). 예: provider `thermomp` 를
`provider_type=runpod`, `endpoint_id=thermomp-ddg-local`,
`api_base=http://127.0.0.1:8500/v2` (bop 위의 RAPID) 로 두면 게이트웨이를
거쳐간다. 공개 도메인(`https://biomodel.kbiofoundry.kr`)의 `/v2` 노출은 SSO
뒤라 서버 간 호출용이 아니며, 필요하면 Caddy 에 토큰 인증 라우트를 별도로
추가해야 한다 — 이 배치에서는 하지 않았다.
