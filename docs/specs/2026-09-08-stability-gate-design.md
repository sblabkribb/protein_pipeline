# 안정성 게이트 승격 (ThermoMPNN ΔΔG) — 설계

- 날짜: 2026-09-08
- 상태: 진행 (사용자 선택: **게이트로 승격** — 재설계 루프 아님. 실행 시간·비용 증가 없음, 승인 화면에서 임계값 설정)
- 불변: 기존 실행 동작 (게이트는 **요청이 켜야만** 동작 — 기본 off), 근거 강제 체계, evolution 모드의 기존 서로게이트.

## 0. 핵심 아이디어

ThermoMPNN ΔΔG는 **구조 + 변이 목록**으로 예측한다 (evolution 서로게이트가 이미 이 패턴 — pipeline.py:11169~, `_design_mutations_vs_native`). 티어 서열은 백본 WT의 변이이므로, 백본 구조 + 변이 목록으로 서열 단위 ΔΔG를 예측해 **AF2 제출 전 게이트**로 쓴다.

## 1. 요청 필드 (`models.py` PipelineRequest)

```python
thermomp_gate: bool = False              # 기본 off — 기존 실행 완전 동일
thermomp_ddg_cutoff: float = 2.0         # kcal/mol; 예측 ΔΔG(합)가 초과하면 탈락
```

- `dry_run`이면 게이트 스킵(기존 dry_run 규칙 준수).
- `runner.thermomp` 미연결 → 게이트 스킵 + 아티팩트에 사유 기록 (soluprot 폴백 패턴과 동일).

## 2. 계획 노출 (`objective_planner.py`)

- `build_plan`에 결정 추가: `thermomp_ddg_cutoff` (editable, 근거: evolution 서로게이트 관측 — 문헌 아님을 kind로 명시) + `thermomp_gate`(bool). 둘 다 `plan_to_request_overrides` 매핑 추가 (soluprot_cutoff이 매핑되는 방식 참고).
- 목적 경로가 stability 미검증임을 유지 — 게이트는 "미검증 평가자를 참고 필터로 쓴다"는 것을 결정 rationale에 명시.

## 3. 파이프라인 게이트 (`pipeline.py` 표준 티어 흐름)

위치: 티어별 soluprot+liabilities 통과 후, AF2 제출 전 (pipeline.py:9733 블록 이후).

```python
# 안정성 게이트(선택). 백본 구조 + 변이 목록으로 ΔΔG를 예측해 임계값 초과 설계를
# AF2 앞에서 걸러낸다. 미검증 평가자다 — 결과는 참고 필터이고 게이트가 켜야만
# 동작한다. 실패한 설계는 탈락이 아니라 "보류"로 기록한다(도구 실패는 설계 실패가 아니다).
```

- 각 티어 통과 서열에 대해: 백본 PDB 텍스트 + `_design_mutations_vs_native` 변이 목록 → `runner.thermomp.predict(pdb_text=..., mutations=[...], wt_sequence=...)` → 서열 단위 ΔΔG 합.
- **스킵 조건** (하나라도 참이면 게이트 미동작, 아티팩트에 `skipped_reason`): thermomp 미연결 / 백본 PDB 부재(denovo-only) / 게이트 off / dry_run.
- **아티팩트**: `tiers/<k>/thermomp.json` — soluprot.json과 같은 계약:
  `{scores: {seq_id: ddG}, cutoff, passed_ids, skipped?: reason, error?: str}`
- **AF2 진행**: `passed_ids ∩ ddG ≤ cutoff` 만 AF2로. 게이트 off면 기존과 100% 동일.
- 예측 실패한 개별 서열 → 탈락 처리하지 않고 통과(보수적) + 아티팩트 note.
- 캐시: evolution의 cached_thermomp 패턴 참고(같은 백본+변이 재예측 방지) — 티어 간 같은 서열이면 재사용.

## 4. 결과 노출

- 퍼널(`buildFunnelRow`): af2 단계가 자연히 줄어든다 — 변경 불필요. 다만 히트리스트/에이전트 판정이 thermomp.json을 참조할 수 있게 에이전트 판정에 게이트 요약 1줄 추가(선택, agent_panel의 기존 패턴 따름).
- 근거 탭: `tiers/<k>/thermomp.json`이 존재하면 리아빌리티 카드 옆에 ΔΔG 요약(통과/탈락 수, 컷오프) 표시.

## 5. 테스트

- 백엔드: 요청 필드 기본값(off), 게이트 on+client+백본 → 통과/탈락 필터와 아티팩트, client 미연결 → skipped 아티팩트 + AF2 전체 진행, dry_run 스킵, 예측 실패 서열 → 통과 처리, plan 결정 노출 + overrides 매핑, funnel 변화.
- 기존 전체 백엔드 스위트 회귀 0 (게이트 off 기본).

## 6. 범위 밖

- 재설계 루프 (ΔΔG → 재표집) — 사용자가 "게이트로 승격" 선택, 별도 검증 과제로 유지.
- relax(REU) 기반 게이트 — evolution의 ΔREU 비교와 별개로 유지.
