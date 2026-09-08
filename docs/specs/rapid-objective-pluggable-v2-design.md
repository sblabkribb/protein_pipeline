# RAPID v2 — objective-pluggable 설계안

**상태: 설계. 구현 승인 전.** v1 코드는 건드리지 않는다.

## 위험의 위치

돌고 있는 격자가 바뀌는 것이 아니다. 격자는 12 타겟 고정 수집이고
`allocation_next_action` 은 온라인 실행 루프에 연결돼 있지 않다. 실질 위험은
**논문에서 동결한 v1 정책 코드와 이후 replay·분석 대상이 바뀌는 것**이다.

따라서 v1 을 동결하고 v2 를 별도로 만드는 한, 설계와 준비는 지금 해도 된다.

```
rapid_structural_v1    동결. 수정 금지. 논문의 검증 대상.
rapid_objective_v2     신규. 별도 버전.
```

`scripts/transcoder/rapid_sr/allocation.py` 는 v2 작업 중 수정하지 않는다.
논문 분석이 그 사본을 쓰고, 테스트가 두 사본을 묶고 있다.

## 목표 구조

```
RAPID Core
│
├─ Objective              무엇을 개선할 것인가
├─ Capability Registry    어떤 모델로 측정할 수 있는가
├─ EvaluationResult       무엇을 관측했는가
├─ ObservationModel       관측으로 arm 상태를 어떻게 갱신하는가
└─ Allocator              다음 계산을 어디에 쓸 것인가
```

**성공 조건: allocator 안에 모델 이름이 하나도 없어야 한다.** SoluProt, AF2,
PPIformer, Rosetta 어느 것도.

---

## 1. Capability Registry — 운영 상태와 과학적 허가를 합치지 않는다

두 축은 서로 다른 질문이다.

| | 질문 | 값 |
|---|---|---|
| operational | 지금 실행할 수 있는가 | installed · service_alive · wired |
| scientific permission | 이 목적으로 써도 되는가 | annotation · ranking · gate · allocation |

한 상태값으로 합치면 표현할 수 없는 조합이 생긴다. PPIformer 가
`service_alive: true`, `validated_for_annotation: true`,
`validated_for_allocation: false` 인 상태가 실재한다.

현재 `availability`(3 값)는 **운영 상태로 유지**한다. 합칠 것은
`objective_status` 와 `validated_for_*` 이고, 그것을 **objective 별
capability** 로 옮긴다.

```yaml
ppiformer_ddg:
  operational:
    installed: true
    service_alive: true
    wired: true
    checked_utc: "2026-09-08"

  objectives:
    binding_affinity:
      allowed_roles: [annotation, ranking]
      forbidden_roles: [hard_gate, allocation]
      evidence:
        - kind: assumption
          statement: RAPID 이 어떤 결합 라벨에도 맞춰본 적이 없다
      to_allow_more: 결합 라벨 코호트에서 맞춰보고 임계값을 정한다
```

허가는 **모델 단위가 아니라 (모델 × objective) 단위**다. 같은 모델이 어떤
objective 에는 gate 로, 다른 objective 에는 annotation 으로만 허용될 수 있다.

기존 `objective_status` 의 내용은 여기로 옮긴다. 예를 들어 aggregation 의
`decision: NO-GO for Gate 1B promotion` 은
`allowed_roles: [annotation]`, `forbidden_roles: [ranking, hard_gate, allocation]`
이 된다.

**`installed == true` 가 `allocation` 허가를 뜻하지 않는다.** 오늘 이 저장소가
그 오류를 갖고 있었다 — `not_wired` 로 적힌 네 모델이 실제로는 살아 있었고,
그걸 보고 "설치가 필요하다" 고 판단하면 틀린다.

---

## 2. ObservationModel — Continuous 를 바로 만들지 않는다

objective 마다 값의 분포와 노이즈가 다르다. activity, binding ΔΔG, Rosetta
energy, solubility score, expression 이 같은 모델을 쓸 이유가 없다. 처음부터
`ContinuousAllocationState` 하나로 일반화하면 다시 뜯게 된다.

상위 인터페이스를 먼저 잡는다.

```
AllocationObservationModel        (interface)
    ├── BetaBernoulliState        ← v1. 현재 구현 그대로.
    ├── ContinuousState           ← 이후
    └── MultiObjectiveState       ← 이후
```

인터페이스는 네 가지만 요구한다.

```python
class AllocationObservationModel(Protocol):
    def update(self, observation: EvaluationResult) -> None: ...
    def expected_utility(self) -> float: ...
    def uncertainty(self) -> float: ...
    def allocation_signal(self) -> float: ...
```

**allocator 는 관측이 이진인지 연속인지 몰라도 된다.** 이것이 실제로
objective-pluggable 한 지점이다.

v1 대응은 그대로 매핑된다.

| 인터페이스 | v1 (`BetaBernoulliState`) |
|---|---|
| `update` | `BetaPosterior.update(successes, trials)` |
| `expected_utility` | `posterior.mean` (부분 풀링 적용) |
| `uncertainty` | `posterior.sd` |
| `allocation_signal` | `movability = 4p(1-p)` |

### 왜 이 슬롯을 `allocation_signal` 로 부르는가

**`movability` 는 expected information gain 이 아니다.** 이름을 그렇게 붙이면
틀린 해석을 굳힌다.

`4p(1-p)` 는 사후평균 하나만 보고 계산한다. 관측이 4 개든 400 개든 p 가 0.5 면
값은 1 이다. 반면 추가 관측 한 번의 정보 이득은 n 이 커지면 줄어든다 — 400 개
관측 뒤의 한 번은 4 개 뒤의 한 번보다 훨씬 덜 가르쳐준다. 두 양은 같지 않고,
`movability` 는 후자를 재지 않는다.

`movability` 가 실제로 재는 것은 **상태가 움직일 여지**다. p 가 0.5 근처면
조건을 바꿨을 때 결과가 움직일 수 있고, 0 이나 1 에 붙어 있으면 무엇을 바꿔도
같은 값에 붙어 있다. 그것이 배분에 쓸모 있는 신호인 이유이고, 정보 이득이라는
주장과는 별개다.

그래서 인터페이스 이름은 중립적으로 `allocation_signal` 로 둔다. v2 의 연속
objective 에서는 EI·PI·expected information gain 같은 다른 신호를 쓸 수 있지만,
**그것들이 movability 와 같은 통계량이라고 가정하지 않는다.** 같은 슬롯에
들어가는 다른 함수다.

`uncertainty` 와 `allocation_signal` 은 **끝까지 분리된 채로 둔다.** 관측이
많아도 p 가 0.5 면 allocation_signal 은 크고 uncertainty 는 작다.

연속 objective 의 첫 구현은 세 후보 중 **하나를 명시적으로 고른다**:
probability of improvement · expected improvement · normalized objective
improvement. 근거 없이 Beta posterior 를 연속 점수에 재사용하지 않는다.

---

## 3. Objective — 평행 체계를 만들지 않는다

`objective_planner.Objective` 가 이미 있다. `ObjectiveSpec` 을 따로 만들어
두 체계를 오래 유지하지 않는다. 기존 것을 version-compatible 하게 확장한다.

```
현재                  확장 후
weights      →  primary + secondary + annotations (role 로 분리)
constraints  →  constraints (유지)
budget       →  budget (유지)
purpose      →  purpose (유지)
(없음)       →  direction · reference
```

```python
@dataclass
class Objective:
    purpose: str = DEFAULT_PURPOSE
    primary: ObjectiveTerm | None = None
    constraints: list[ObjectiveTerm] = field(default_factory=list)
    secondary: list[ObjectiveTerm] = field(default_factory=list)
    annotations: list[ObjectiveTerm] = field(default_factory=list)
    budget: dict[str, int] = field(default_factory=dict)

    # v1 입력을 받는다. weights/constraints dict 를 위 형태로 변환한다.
    @classmethod
    def from_v1(cls, *, weights, constraints, budget, purpose) -> "Objective": ...
```

```python
@dataclass
class ObjectiveTerm:
    name: str                    # KNOWN_OBJECTIVES 안
    role: str                    # 아래 5 값
    direction: str | None        # maximize | minimize | None(constraint 전용)
    threshold: float | None
    reference: str | None        # input_protein | wild_type | None
    evaluator: str | None        # None 이면 registry 가 고른다
    fidelity: str | None         # cheap | medium | expensive | None
```

`role` 5 값: `primary_objective` · `hard_constraint` · `soft_constraint` ·
`secondary_objective` · `annotation`.

**`annotation` 은 정책과 후보 제거에 자동으로 영향을 주지 않는다.** 이것을
테스트로 고정한다 — annotation 만 바꿨을 때 allocator 결정과 선정 결과가
바이트 단위로 같아야 한다.

이름을 `ObjectiveSpec` 으로 승격하는 것은 나중에 해도 된다. `from_v1` 파서가
있으면 기존 호출자가 깨지지 않는다.

---

## 4. EvaluationResult — evaluator 출력을 통일한다

현재 evaluator 출력이 각자 형식이다. AF2 는 `best_plddt`, Rosetta 는
`score_per_residue`, ThermoMPNN 은 `additive_ddg_kcal_mol`, SoluProt 은 스칼라.
allocator 가 이것들을 알면 안 된다.

```python
@dataclass
class EvaluationResult:
    objective: str
    raw_score: float | None
    normalized_score: float | None      # 방향 정규화. 높을수록 좋음.
    uncertainty: float | None
    direction: str                      # maximize | minimize
    valid: bool
    provenance: dict                    # 아래 필수 키
```

`provenance` 필수 키: `model` · `version` · `config` · `input_artifact` ·
`output_artifact` · `runtime_s` · `failure_status` · `calibration_status`.

**`normalized_score` 를 evaluator 가 만들 수 없으면 `None` 을 낸다.** 정규화
규칙을 짐작해서 채우지 않는다 — 방향을 모르는 점수로 순위를 매기면 반대로
정렬될 수 있다.

adapter 는 클라이언트마다 얇게 둔다 (`clients/*.py` 옆). 5~6 개.

---

## 5. Allocator — 행동 이름을 일반화한다

arm 정의는 유지한다: `backbone × generation_condition`.

```
v1                              v2
probe_more_sequences        →   generate_more
explore_generation_condition →   explore_generation_condition  (그대로)
verify_with_af2             →   evaluate_at_higher_fidelity
abandon_backbone            →   abandon_arm
```

`verify_with_af2` 만 구조 전용이었다. AF2 는 fidelity provider 중 하나가 되고,
어느 evaluator 로 올릴지는 registry 의 `fidelity` 와 허가가 정한다.

acquisition 은 evaluator-independent 하게 쓴다.

```
v1  A = p̂ + β·U − λ·C − γ·D + η·(movability × 조건 불확실성)
v2  A = expected_utility + β·uncertainty + η·allocation_signal − λ·cost − γ·redundancy
```

**v1 식을 근거 없이 폐기하지 않는다.** v1 은 전향 검증을 받는 대상이므로
`rapid_structural_v1` 프로파일로 재현 가능하게 남는다. v2 식이 v1 식으로
환원되는지(binary objective 이고 allocation_signal 이 movability 일 때) 테스트로
고정한다.

---

## 6. 실패는 크게 낸다

다음은 대체하지 않고 실패한다.

```
objective 에 맞는 evaluator 가 없음
required input 이 없음
evaluator 가 해당 role 로 허가되지 않음
score direction 을 알 수 없음
reference-relative score 가 정의되지 않음
model service unavailable
```

유사한 evaluator 로 자동 대체하지 않는다.

```
Requested objective: catalytic activity
No evaluator permitted for catalytic activity allocation.
  ppiformer_ddg   binding_affinity 에만 허가됨
  rosetta_relax   annotation 으로만 허가됨
활성은 타겟마다 다른 assay 로 정의되므로 assay 라벨 없이는 평가자를 붙일 수 없다.
```

---

## 7. 검증 경계 — 절대 깨지 않는다

현재 논문이 검증하는 것은 **structural-success 기반 target-adaptive
hierarchical compute allocation** 이다.

v2 를 추가했다고 다음을 주장하지 않는다.

```
RAPID improves arbitrary protein function
RAPID improves activity
RAPID improves binding affinity
```

objective 마다 별도의 evaluator validation 이 필요하고, 기능 주장에는
전향적·실험적 검증이 필요하다.

**v1 결과와 v2 결과를 같은 표에 섞지 않는다.** 프로파일 이름이 결과마다
붙는다.

---

## 8. 진행 순서

```
지금 (격자와 무관)
  1. rapid_structural_v1 동결 + golden/regression test      ← 안전망이 먼저
  2. Objective v2 스키마 (이 문서 §3)
  3. EvaluationResult contract (§4)
  4. Registry capability schema (§1)
  5. AllocationObservationModel interface (§2)
     └ 코드 연결은 하지 않는다

격자 완료
  prospective 분석 → v1 결과 freeze
  rapid_objective_v2 구현 착수
     Objective v2 → EvaluationResult adapters → BetaBernoulliState adapter
     → generic action names → continuous objective
```

1 번이 먼저인 이유: golden test 가 통과하는 동안만 리팩터링한다. 그것이
`rapid_structural_v1` 이 정말 동결됐다는 증거다.

## 9. 프로파일

### A. 현재 RAPID 재현 (`rapid_structural_v1`)

```yaml
profile: solubility_structural_redesign
primary: structural_success
constraints:
  soluprot: {min: 0.5}
structural_success: {plddt_min: 85, rmsd_nonloop_order_max: 2.0}
```

**이 프로파일은 기존 결과를 동일하게 재현해야 한다.** golden test 대상.

### B. Stability-oriented

```yaml
profile: stability_redesign
primary: stability
constraints: [structural_fidelity, solubility]
```

허가 확인 필요: ThermoMPNN 은 native-백본 설계에만, annotation 으로만.
설계당 변이 중앙값 77 이라 적용 범위 밖이고 생성 백본에는 정의되지 않는다.

### C. Binder optimization

```yaml
profile: binder_design
primary: binding
constraints: [structural_integrity]
```

현재 허가: PPIformer·ipSAE 는 annotation 까지. `allocation` 은 금지 —
Gate 0 사전분포가 결합 성공에 대해 측정된 바 없다.

### D. Custom

```yaml
profile: custom
primary: {name: user_defined, evaluator: plugin_name}
```

plugin 이 `Evaluator` contract 와 `EvaluationResult` 를 구현하고, registry 에
허가가 기록돼야 실행된다.

## 10. 열린 질문

1. `normalized_score` 정규화 규칙을 objective 별로 어디에 둘 것인가 —
   registry 인가 evaluator 인가
2. 연속 objective 의 부분 풀링. Beta 의 `pooling_strength` 에 해당하는 것이
   Gaussian 계열에서 무엇인가
2b. 연속 objective 의 `allocation_signal` 을 무엇으로 할 것인가. EI·PI·expected
   information gain 중 하나를 고르고, 그것이 movability 와 다른 통계량임을
   명시한다. 이진에서 잘 작동한 신호가 연속에서도 작동한다고 가정하지 않는다.
3. multi-fidelity 에서 낮은 fidelity 관측을 높은 fidelity 사후분포에 어떻게
   반영할 것인가 — 별도 arm 인가 같은 arm 의 다른 노이즈 수준인가
4. Pareto 비교의 tie-break 순서. 현재 권고는 hard constraints → primary →
   secondary Pareto → diversity 이고, 임의 가중합은 명시 요청 또는 검증된
   경우에만
