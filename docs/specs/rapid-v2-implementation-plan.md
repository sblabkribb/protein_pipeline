# RAPID v2.0 구현 계획

**설계 승인일 기준.** 설계 문서:
`docs/specs/rapid-task-profile-adaptive-allocation-v2-design.md`.

이 문서는 **무엇을 어떤 순서로 만들고, 각 단계를 무엇으로 통과 판정할지**를
정한다. 설계 결정을 다시 하지 않는다 - 설계에 없는 것이 필요해지면 설계를 먼저
고친다.

---

## 0. 이 계획이 지키는 것

```
v1 은 바뀌지 않는다.
  scripts/transcoder/rapid_sr/allocation.py       수정 금지
  pipeline-mcp/src/pipeline_mcp/allocation.py     수정 금지
  두 파일은 v2 작업 내내 byte-identical 로 남는다.

통과해야 하는 테스트 (매 단계)
  test_allocation_v1_golden.py     31 개
  test_v1_freeze.py                 4 개
  test_allocation_runtime.py        두 사본을 묶는 테스트
  test_results_of_record.py        28 개 (원고·기록 수치)
  전체 스위트                       현재 1,238 통과 유지
```

**규칙: golden test 가 통과하는 동안에만 리팩터링한다.** 깨지면 리팩터링이
아니라 정책 변경이다.

---

## 1. 시작 전에 고칠 것 — 동결의 구멍

계획을 쓰면서 발견한 것이다. 설계는
`scripts/transcoder/rapid_sr/allocation.py` 를 수정 금지로 선언했는데,
**그 파일이 freeze manifest 에 없다.**

```
manifest 의 code 목록 (7 개)
  26_holdout_grid.py · 39_ · 40_ · 41_ · 43_
  rapid_sr/protocol.py
  pipeline_mcp/allocation.py          ← 런타임 정본은 있다
                                      ← rapid_sr/allocation.py 가 없다
```

이 파일은 `16_allocation_budget_simulation.py` 가 쓰고
`test_allocation_runtime.py` 가 런타임 사본과 묶고 있다. 두 파일은 실제로
다르다 (재현 사본에 `simulate` 와 `clustered_policy_bootstrap` 이 더 있다).
지금 상태로는 재현 사본이 드리프트해도 해시 검사가 잡지 못한다.

**Phase 0 의 첫 작업으로 manifest 에 추가한다.**

태그 `rapid_structural_v1` 은 옮기지 않는다. 기존 항목의 해시는 하나도 바뀌지
않고 **manifest 의 적용 범위만 넓어지는 것**이므로, v1 결과는 영향을 받지
않는다. 그 사실을 manifest 와 커밋 메시지에 적는다.

---

## 2. 코드가 놓일 자리

새 패키지를 만든다. 기존 모듈을 고쳐서 v2 를 얹지 않는다 - 그러면 v1 경로와
v2 경로가 같은 파일에서 갈라진다.

```
pipeline-mcp/src/pipeline_mcp/rapid_core/
    __init__.py
    arm.py            DesignArm (generic)
    observation.py    AllocationObservationModel · BetaBernoulliState
    evaluation.py     EvaluationResult
    transform.py      ScoreTransform + registry 조회
    permission.py     scientific permission
    coverage.py       CoverageState                      (Phase 4)
    core.py           RapidCore  ← 모델 이름 없음
    profiles/
        __init__.py
        fixed_backbone_redesign.py
        antigen_adapter.py    contract 만. Antigen 코드 변경 없음.

pipeline-mcp/src/pipeline_mcp/task_profile.py
    model_routing.Route 위에 얹는 TaskProfile resolver
```

레지스트리는 **YAML 이 원본이고 JSON 이 미러**다 (`_read_registry_document` 는
JSON 을 먼저 읽는다). YAML 을 고치면 JSON 을 다시 만들어야 하고, 이미 드리프트
검사가 있다. 각 Phase 의 체크리스트에 넣는다.

---

## 3. Phase

각 Phase 는 **acceptance** 를 통과해야 다음으로 간다. acceptance 는 전부
자동 검사 가능한 형태로 적었다.

### Phase 0 — 안전망 (선행 없음)

| | |
|---|---|
| 작업 | 1. freeze manifest 에 `rapid_sr/allocation.py` 추가 (§1)<br>2. `test_v1_immutable.py` 신규: 두 allocation.py 가 manifest 해시와 일치<br>3. CI 에서 v2 브랜치가 두 파일을 건드리면 실패하는 검사 |
| 산출 | `pipeline-mcp/tests/test_v1_immutable.py` |
| acceptance | 두 파일 중 하나를 한 바이트 고치면 테스트가 실패한다 (실제로 넣었다 되돌려 확인) |
| 의존 | 없음 |

### Phase 1 — contract 만. 동작 없음.

순수 추가다. 기존 코드 호출 경로를 건드리지 않으므로 v1 위험이 0 이다.

| | |
|---|---|
| 작업 | `EvaluationResult` (설계 §L2 의 13 필드)<br>`ScoreTransform` + 버전 태그<br>`permission.py` — operational × scientific 2 축 (설계 §M)<br>registry 조회 키를 `TaskProfile × evaluator × objective × role` 로 확장 |
| acceptance | `validity` / `failure_reason` 가 없는 결과를 만들 수 없다 (생성자에서 실패)<br>`raw_value` 없이 `ScoreTransform` 을 통과시킬 수 없다<br>role 이 registry 에 없으면 조회가 예외를 던진다<br>기존 스위트 1,238 통과 유지 |
| 의존 | Phase 0 |

`validity` 와 `failure_reason` 을 필수로 두는 이유는 이번 캠페인에서 같은 실패를
세 번 겪었기 때문이다 - 동결 지표가 거부한 48 행, 메시지가 사라진 ThermoMPNN
8 건, pose 0 개인데 22/22 ok. **"값 없음" / "실패" / "거부" 는 서로 다른
상태다.**

### Phase 2 — TaskProfile

| | |
|---|---|
| 작업 | `purposes` 스키마에 설계 §I1 의 필드 추가 (design_arm_schema, available_optimization_modes, coverage_semantics, minimum_exploration_policy, allowed_actions, scientific_permissions, artifact_contract)<br>`task_profile.py` resolver<br>task-aware objective 검증 — 기존 `Objective.unsupported()` 를 **task 별로** 확장<br>`fixed_backbone_redesign` 프로파일 선언<br>실패 경로 (설계 §K3) |
| acceptance | `fixed_backbone_redesign` + `binding` 요청이 **거부되고**, 메시지가 이유·필요 조건·대안 profile 을 담는다 (설계 §K2 문구)<br>`antibody_design` 요청이 registry 의 `referral` 로 안내된다 (이미 `executable=False`)<br>YAML→JSON 미러 드리프트 검사 통과<br>기존 `test_model_routing.py` · `test_purpose_routing_plan.py` 통과 유지 |
| 의존 | Phase 1 |

### Phase 3 — Core. 가장 위험한 단계.

| | |
|---|---|
| 작업 | `DesignArm` generic (설계 §J1)<br>`AllocationObservationModel` interface + `BetaBernoulliState`<br>`RapidCore` — generic `ArmState` 만 받는다<br>v1 정책을 `rapid_structural_v1` **프로파일로 재현** |
| acceptance | **환원 테스트**: `RapidCore` 를 `rapid_structural_v1` 프로파일로 돌린 결과가 golden test 의 `EXPECTED_ACTIONS` 6 개와 `EXPECTED_STATE` 6 쌍과 **정확히** 일치<br>acquisition 순위가 golden 의 `["T\|B2\|T0.1","T\|B3\|T0.1","T\|B1\|T0.1","T\|B0\|T0.1"]` 와 일치<br>부분 풀링 값 일치 (형제 8/8 이 미관측 arm 을 0.42 → 0.8418181818)<br>`test_core_no_model_names.py`: Core 모듈에 금지 식별자 0 건 (Invariant 5)<br>v1 파일 여전히 byte-identical |
| 의존 | Phase 2 |

**환원 테스트가 이 Phase 의 존재 이유다.** 통과하지 못하면 Core 를 합치지
않는다. v1 을 고쳐서 맞추는 것은 금지다.

금지 식별자 목록: `AF2 AF3 ESMFold SoluProt PPIformer Rosetta ThermoMPNN
AntiFold ProteinMPNN colabfold alphafold IMGT CDR framework epitope antibody
antigen backbone_source plddt rmsd soluprot`.
`backbone` 자체는 `DesignArm.dimensions` 의 키로만 등장할 수 있으므로 Core
모듈에서는 금지한다.

### Phase 4 — coverage. basin 동결에 걸려 있다.

| | |
|---|---|
| 작업 | `CoverageState` contract — **basin 정의를 주입받는 형태로** 만든다<br>`optimization_mode` (structural_yield / coverage_preserving)<br>`portfolio_redundancy` 항 (batch 항과 분리, 설계 §E3b)<br>FDBC@B 계산기 (설계 §SS1) |
| acceptance | basin 정의를 바꿔 끼우면 같은 코드가 backbone 기준과 cluster 기준 둘 다 계산한다<br>`feasible coverage` 와 `explored coverage` 가 **다른 이름의 다른 값**으로 나온다 (Invariant 7)<br>coverage mode 보고에 guardrail 값이 없으면 실패<br>`δ = 0` 에서 Core 가 Phase 3 환원 테스트를 여전히 통과 |
| 의존 | Phase 3 **그리고 M1 basin 동결** |

**중요**: 이 Phase 는 basin 이 무엇인지 **모르는 채로** 만든다. 코드는 basin
정의를 주입받고, 구체적 정의는 동결 문서가 준다. 그래야 M1 을 기다리지 않고
contract 를 짤 수 있고, 동시에 결과를 보고 basin 을 고르는 일이 구조적으로
불가능해진다.

`δ` (portfolio_redundancy 가중) 의 값은 이 Phase 에서 정하지 않는다. 기본 0 으로
두고, 열린 질문 3 번이 닫힌 뒤에 넣는다. **0 이 아닌 값을 임의로 넣고
coverage-aware 라고 부르지 않는다** (설계 §O1).

### Phase 5 — Antigen adapter contract

| | |
|---|---|
| 작업 | `profiles/antigen_adapter.py` — **contract 만**<br>Antigen state → `ArmState` 매핑 정의<br>`WetOutcome` 스키마 (설계 §AG8)<br>`AntigenTaskProfile` 을 registry 에 선언 (executable=False 유지) |
| acceptance | Antigen 저장소 파일이 하나도 바뀌지 않는다 (`/opt/antigen_pipeline` git status clean)<br>adapter 가 없거나 실패하면 기존 배분으로 돌아간다 (fail-open) 를 테스트로 확인<br>Antigen 의 어떤 evaluator도 `allocation` 허가를 받지 않는다 (Invariant 6·7) |
| 의존 | Phase 3 (Phase 4 는 아니다 — contract 만이므로) |

---

## 4. 병렬 측정 트랙 — 지금 시작할 수 있다

코드 위험이 없고 Phase 4 를 막고 있으므로 **Phase 0 과 동시에 시작한다.**

### M1 — basin 구조 기술 통계 (Phase 4 를 막는다)

```
대상   홀드아웃 RFD3 백본 60 개, (가능하면) Antigen ~200 개
목적   서로 얼마나 다른지 기술한다. 정책 비교는 하지 않는다.
산출   백본 쌍별 구조 거리 분포, 임계값별 클러스터 수 곡선
금지   이 단계에서 정책을 비교하거나 basin 정의를 고르는 것
```

끝나면 사람이 basin 정의를 고르고 **별도 freeze 문서**에 설계 §SS3 의 8 개
항목을 못 박는다. v1 의 `holdout_experiment_spec.json` 과 같은 형식.

### M2 — coverage floor 후보값

```
근거 둘이 이미 있다
  v1     probe 바닥 20 (= 4 × 5), 이득이 예산 23 부터
  Antigen surrogate probe 최적 예산 몫 25–35%
단위와 pipeline 이 다르므로 같은 값이라 주장하지 않는다.
task 별로 재서 minimum_exploration_policy 에 넣는다.
```

### M3 — guardrail 비열등 마진 (사람 결정)

설계 §SS2 의 마진. 통계가 아니라 과학적 판단이므로 측정이 아니라 **결정**이고,
동결 문서에 들어간다.

---

## 5. 의존 관계

```
Phase 0 ──┬─→ Phase 1 ─→ Phase 2 ─→ Phase 3 ─┬─→ Phase 4
          │                                   └─→ Phase 5
          └─→ M1 ─→ basin freeze ─────────────────↗
                M2 ─→ minimum_exploration_policy ─↗
                M3 ─→ guardrail margin ──────────↗
```

Phase 5 는 Phase 4 를 기다리지 않는다. Antigen 은 contract 만이고, 그 contract
는 coverage 구현이 아니라 `ArmState` 모양에 의존한다 (Phase 3).

---

## 6. v2.0 完了 조건

```
✅ Phase 0–5 acceptance 전부 통과
✅ v1 두 파일 byte-identical, 태그 rapid_structural_v1 유효
✅ 환원 테스트 통과 (Core 가 v1 을 재현)
✅ Core 에 모델 이름 0 건
✅ Antigen 저장소 변경 0 건
✅ 전체 스위트 통과 (현재 1,238 + 신규)
✅ basin 동결 문서 존재, Phase 4 가 그것을 읽는다
```

구현하지 않는 것 (설계 §U):

```
generate_new_backbone
full diversity maximization / full multi-objective optimizer
wet-feedback closed loop
Antigen pipeline · UI 변경
continuous Bayesian 모형 확정
multi-fidelity (v2.1)
```

---

## 7. 위험과 완화

| 위험 | 왜 생기나 | 완화 |
|---|---|---|
| **v1 이 조용히 바뀐다** | 리팩터링이 공용 코드를 건드림 | Phase 0 의 immutability 테스트 + 매 단계 golden test |
| **Core 가 v1 을 재현하지 못한다** | 부동소수 순서, 동점 처리, 풀링 순서 차이 | Phase 3 환원 테스트를 acceptance 로. 못 맞추면 합치지 않는다 |
| **basin 을 결과 보고 고른다** | M1 결과와 정책 비교를 같이 봄 | M1 에서 정책 비교 금지, 동결 문서를 prospective 전에 커밋 |
| **coverage 가 explored 로 새어나간다** | 두 값이 비슷해 보임 | Invariant 7 테스트, 이름·자료형 분리 |
| **δ 를 임의로 넣고 coverage-aware 라 부른다** | "뭐라도 넣어야 동작" 압박 | 기본 0, 열린 질문 3 이 닫히기 전 변경 금지 |
| **Antigen 에 손이 간다** | adapter 를 만들다 보면 상류를 고치고 싶어짐 | acceptance 에 "Antigen git status clean" 을 넣음 |
| **모델 이름이 Core 로 샌다** | 편의상 특수 처리 | 금지 식별자 테스트 |

---

## 8. 보고 규칙

v2.0 결과를 낼 때:

```
프로파일 이름을 결과마다 붙인다.
v1 결과와 v2 결과를 같은 표에 섞지 않는다.
coverage 개선은 feasible coverage 로만 말하고 guardrail 값을 함께 낸다.
"backbone diversity 를 확장했다" 는 generate_new_backbone 전에는 쓰지 않는다.
Antigen 은 coverage allocation 까지만 주장한다.
```
