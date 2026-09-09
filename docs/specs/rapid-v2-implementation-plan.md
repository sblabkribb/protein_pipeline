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
| acceptance | 두 파일 중 하나를 한 바이트 고치면 테스트가 실패한다 (실제로 넣었다 되돌려 확인)<br>**정규화 경로가 중복되면 manifest 생성이 hard fail** (basename keying 사고 재발 방지)<br>**manifest 에 `schema_version` 이 있고, 읽는 쪽이 모르는 버전이면 실패** |
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
| acceptance | Antigen 저장소 파일이 하나도 바뀌지 않는다 (`/opt/antigen_pipeline` git status clean)<br>adapter 가 없거나 실패하면 기존 배분으로 돌아간다 (fail-open) 를 테스트로 확인<br>**PPIformer · AF3 · ipSAE 가 reward 경로에 들어가면 테스트가 실패한다** — 이름으로 막는 것이 아니라 `scientific_permissions.allocation != true` 인 evaluator 의 값이 `ArmState.expected_utility` 에 도달하는 경로 자체를 금지 (Invariant 6)<br>feasibility 로 쓰는 것은 허용 — gate 허가는 있다 (설계 §SS5) |
| 의존 | Phase 3 (Phase 4 는 아니다 — contract 만이므로) |

---

## 4. 병렬 측정 트랙 — 지금 시작할 수 있다

코드 위험이 없고 Phase 4 를 막고 있으므로 **Phase 0 과 동시에 시작한다.**

### M1 — basin 구조 기술 통계 (Phase 4 를 막는다)

M1 은 **basin 정의를 고르는 분석이 아니라, 후보 basin 정의가 얼마나 안정적인지
확인하는 기술 통계**다. 이 구분이 M1 의 전부다.

```
대상   홀드아웃 RFD3 백본 60 개, (가능하면) Antigen ~200 개

한다
  백본 쌍별 구조 거리 분포 (전체, 타겟 내, 타겟 간)
  사전에 정한 임계값 격자에서 클러스터 수와 그 안정성
  클러스터 크기 분포 · 싱글턴 비율
  타겟마다 클러스터 수가 얼마나 다른지

하지 않는다
  정책 비교 (adaptive vs static)
  FDBC 계산
  yield / 성공률과의 상관
  "우리 결과가 잘 나오는 임계값" 고르기
```

**임계값 격자는 데이터를 보기 전에 적는다.** 격자를 먼저 커밋하고 그 다음에
돌린다. 그래야 사후에 격자를 넓히거나 좁히는 일이 기록에 남는다.

안정성 판정의 뜻: 임계값을 조금 움직였을 때 클러스터 수가 급변하면 그
정의는 basin 축으로 쓰기에 취약하다는 뜻이다. 완만하면 그 구간 어디를 잡아도
같은 구조를 본다는 뜻이다. **어느 쪽인지를 기록하는 것이 M1 의 산출물이고,
그것을 보고 사람이 basin 을 고른다.**

끝나면 사람이 basin 정의를 고르고 **별도 freeze 문서**에 설계 §SS3 의 8 개
항목을 못 박는다. v1 의 `holdout_experiment_spec.json` 과 같은 형식.

### M2 — endpoint 의 동적 범위 (Phase 4 endpoint 동결을 막는다)

M1 이 `coverage_unit = backbone_id` 를 동결시키면서 새 위험이 생겼다.
**binary feasible-backbone coverage 가 의무 probe 만으로 포화할 수 있다.**
타겟당 backbone 5 개 × 최소 probe 4 회면 모든 정책이 5/5 를 내고, 그러면 지표가
정책을 구별하지 못한다. 포화한 지표로 사전등록하면 실험이 답을 낼 수 없다.

```
한다 (정책 비교 아님)
  의무 probe 직후 타겟별 "통과 후보 ≥1" backbone 수의 분포
  통과 후보가 backbone 별로 얼마나 몰려 있는가 (entropy · effective number)
  고정 크기 portfolio 에서 실제로 대표되는 backbone 수

하지 않는다
  adaptive vs static 비교
  어느 정책이 나은지에 대한 어떤 진술
```

이것은 성능 측정이 아니라 **자를 먼저 재는 것**이다. 라벨을 읽지만 정책은
돌리지 않는다 - 서열은 무작위로 뽑는다.

```
포화하지 않으면   Feasible Backbone Coverage @ Fixed Budget (단순 count)
포화하면          Effective Feasible Backbone Coverage = exp(H)
```

### M2b — coverage floor 후보값 (Phase 4 를 막지 않는다)

```
근거 둘이 이미 있다
  v1     probe 바닥 20 (= 4 × 5), 이득이 예산 23 부터
  Antigen surrogate probe 최적 예산 몫 25–35%
단위와 pipeline 이 다르므로 같은 값이라 주장하지 않는다.
task 별로 재서 minimum_exploration_policy 에 넣는다.
```

### M3 — guardrail 비열등 마진 — **확정됨**

```
yield ratio >= 0.90     (10% 상대 비열등 마진)

판정   FDBC 개선의 클러스터 bootstrap 95% CI 가 0 을 제외
       AND yield ratio 단측 95% 하한 >= 0.90

comparator
  primary    같은 예산의 static / equal allocation
  secondary  frozen structural-yield RAPID
```

**운영상 사전등록 기준이지 biological truth 가 아니다.** 설계 §SS2 에 근거와
함께 적혀 있다. 남은 M3 작업은 측정이 아니라 이 값을 basin freeze 문서에
복사하는 것뿐이다.

---

## 5. 의존 관계

```
Phase 0 ──┬─→ Phase 1 ─→ Phase 2 ─→ Phase 3 ─┬─→ Phase 4
          │                                   └─→ Phase 5
          └─→ M1 (완료) ─→ coverage_unit 동결 ────↗
                  └─→ M2 ─→ endpoint 형태 동결 ───↗
                      M2b ─→ minimum_exploration ─↗
                      M3 (완료) ─→ guardrail 0.90 ↗
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

---

## 9. v2.0 multi-source 로의 개정 (2026-09-09)

동결 문서: [`rapid-v2-multisource-validation-freeze.md`](rapid-v2-multisource-validation-freeze.md)
기계 정본: `public_data/benchmark/gate0/multisource_validation_plan.json`

이 절은 §3 Phase 4B 이후의 실행 순서를 대체한다. **§0 의 v1 불변식과 §7 의 위험
표는 그대로 유효하다.** Core 는 여전히 모델 이름을 모르고, source 는 profile
수준의 개념이다.

### 바뀐 것

```
calibration    기존 RFD3 51 backbone 재사용
               → fresh 12 targets x 10 backbones x 2 sources
confirmatory   12 x 5 RFD3 x 24 = 1,440
               → 12 x 10 RFD3 x 18 + 12 x 10 BioEmu x 18 = 4,320 (서로 독립)
후보 깊이       backbone 당 24 (5-backbone ceiling 기준)
               → backbone 당 18 = 6/6/6, ceiling 180/source
posterior      단일 q_b · 단일 kappa_pool
               → q_b,RFD3 / q_b,BioEmu · kappa_pool,RFD3 / kappa_pool,BioEmu
판정            1 회
               → source 마다 1 회, 합치지 않는다
```

### 왜 Core 를 고치지 않아도 되는가

`ArmSchema` 는 이미 hierarchy 를 profile 이 선언하게 되어 있다. source 별 독립은
**두 개의 독립 campaign** 으로 표현된다 - 하나의 schema 에 source 축을 더하는
것이 아니다.

```
❌ hierarchy = ("target", "source", "backbone")   → 한 pool 이 된다
✅ campaign(rfd3)   hierarchy = ("target", "backbone")
   campaign(bioemu) hierarchy = ("target", "backbone")
   두 campaign 은 state 도 hyperparameter 도 공유하지 않는다
```

이렇게 두면 Core 에 `bioemu` 라는 문자열이 등장하지 않는다. source 는 campaign
을 만드는 쪽(profile / 실행 스크립트)에만 나타난다. **금지 식별자 테스트가
그대로 통과해야 한다.**

### 새로 필요한 구현 작업

```
i.   47_position_mapping_spike.py 에 source 인자
     rfd3: staged→backbone 항등 · bioemu: renumbered_from_1
     알 수 없는 source 는 hard fail (조용한 기본값 금지)
ii.  BioEmu backbone 생성 스크립트 (유한 규칙 · 동결 seed 순서)
     num_samples 50 · max_return 10 · max_attempted 200 · cutoff 2.0
iii. M1-BioEmu 구조 진단 (M1 절차 재사용, outcome 미사용)
iv.  calibration/confirmatory 실행에 source 차원 기록
     af2_order_metric.csv 의 backbone_source 열을 그대로 쓴다 (이미 있다)
v.   kappa 식별을 source 별로 두 번 (§9 기준 불변)
vi.  EFBC 보고에 unit 수 u 와 EFBC/u 를 함께 남긴다
vii. warmup=3 replay (사전 등록된 secondary sensitivity, 추가 폴딩 0)
     primary 는 warmup=4 다. GO/NO-GO 에 쓰지 않는다.
```

`iv` 가 작은 이유는 `backbone_source` 가 처음부터 열로 있었기 때문이다. 동결된
1,728 격자도 `rfd3 1,440 + native 288` 로 이미 두 source 를 담고 있다. 이번에
바뀌는 것은 **그 열이 배분 단위가 아니라 실험 설계 축이 된다**는 것이다.

### 통과 판정

```
test_multisource_validation_freeze.py     숫자·provenance
test_bioemu_backbone_provenance.py        매핑·서열 동일성
test_masked_holdout_freeze.py             타겟 동결이 유지되는가
test_calibration_cohort_freeze.py         §9 가 대체되지 않았는가
test_v1_freeze.py                         27/27 그대로
금지 식별자 테스트                          Core 에 source 이름이 없는가
```
