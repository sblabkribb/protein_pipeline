# RAPID 구조와 Figure 1 뼈대

이 문서는 지금까지 측정된 것만으로 RAPID 의 구조를 고정한다. 각 주장에는
아티팩트를 붙였고, 아직 안 나온 것은 자리만 비워뒀다. 그림을 그리기 전에
숫자가 어디서 오는지 한 곳에 모으는 것이 목적이다.

## 개념적 전환점

Gate 1B 는 **어떤 서열이 좋은지 찍는 문제가 아니라, 어디를 몇 번 더 찔러볼지
결정하는 문제**다. 서열 수준 저비용 예측기가 구조 성공을 가리지 못한다는 것을
측정했기 때문에 나온 정의이고, 이것이 현재 논문의 개념적 축이다.

---

## Figure 1A — 왜 계층적으로 계산하는가

```
Target
  ↓
Backbones
  ↓
Sequences
```

관측된 구조 성공 변이의 귀속 (설계 1,299 · 타겟 20 · 백본 37):

| 수준 | 귀속 비율 |
|---|---|
| Target | 49.5% |
| Backbone within target | 14.7% |
| Sequence within backbone | 35.8% |

관측된 후보군에서 변이가 없던 백본 15/37 (41%), 그 백본들이 차지하는 설계
477/1,299 (37%).

**표현 주의.** "구조 성공의 64% 가 백본 수준에서 결정된다" 가 아니라 "이
코호트의 분산 분해에서 64.2% 가 타겟 및 백본 수준 차이에 귀속되었다" 다.
분산 분해는 관측된 코호트의 귀속이지 인과적 결정이 아니다. 포화 백본도 "어떤
서열 수준 예측기도 원리적으로 쓸모없다" 가 아니라 "관측된 후보군에서 서열
랭킹으로 구분할 수 있는 변이가 없었다" 다 — 서열을 더 생성하면 달라질
가능성까지 막는 주장이 아니다.

출처: `public_data/benchmark/gate0/variance_decomposition_structural.json`

Gate 0 이 이 구조를 겨냥한다: ProteinMPNN encoder 로 백본 수준 성공을
예측하는 out-of-fold AUC 0.7247 [0.7088, 0.7397], 62 타겟.
출처: `public_data/benchmark/gate0/gate0_target_level.json`

---

## Figure 1B — 적응적 고리

```
Gate 0: backbone prior
ProteinMPNN encoder · OOF AUC 0.725
        ↓
Sequence generation ←──────────────────┐
        ↓                              │
SoluProt >= 0.5                        │
(pre-specified objective constraint)   │
        ↓                              │
Initial probe: AF2 4-8                 │
        ↓                              │
p_hat                                  │
uncertainty   = posterior SD           │
movability    = 4p(1-p)                │
        ↓                              │
     Decision                          │
        │                              │
        ├─ probe_more_sequences ───────┤
        │                              │
        ├─ explore_generation_condition┘
        │     (조건 변경 후 재생성)
        │
        ├─ verify_with_af2
        │     └─→ additional AF2 → Structural evaluation
        │
        └─ abandon_backbone
              └─→ STOP this backbone
```

네 행동의 갈림은 정확히 이렇다. `abandon_backbone` 은 아래로 흐르지 않는다 —
그 백본에서 끝난다.

**uncertainty 와 movability 는 다른 값이다.** 그림에서도 분리한다.

| | 뜻 | 언제 큰가 |
|---|---|---|
| `uncertainty` | 사후분포 SD. `p_hat` 을 얼마나 확신하지 못하는가 | 관측이 적을 때 |
| `movability` | `4p(1-p)`. 상태가 움직일 여지 | `p_hat` 이 0.5 근처일 때 |

관측이 많아도 p 가 0.5 면 movability 는 크고 uncertainty 는 작다. 둘을 같은
개념으로 그리면 심사자가 묻는다. 코드에서도 `probe_state()` 가 두 값을 별도
필드로 낸다.

임계값: `MIN_PROBE_SEQUENCES = 4` (이보다 얇으면 판정하지 않고 서열을 더
뽑는다), `MOVABILITY_FLOOR = 0.2` (p 가 약 0.05 또는 0.95 인 지점).

백본은 홀로 판정되지 않는다. 타겟 사후분포를 사전분포로 받는 부분 풀링이
있어서, 형제 백본의 관측이 그 백본의 `p_hat` 을 끌어당긴다.

구현: `pipeline-mcp/src/pipeline_mcp/allocation.py`,
도구 `pipeline.allocation_next_action`.
정책이 보는 정보는 Gate 0 사전분포와 실제 관측뿐이다 — 참값 yield 를 주입하는
경로가 없고 `set_backbone_true_yield` 는 부르면 예외를 낸다.

**아직 실행 루프가 이 도구를 부르지 않는다.** 현재는 기록된 결과 위에서
평가하는 정책이고, 시스템이 스스로 재배분하지는 않는다. 논문에서 "정책"과
"시스템 기능"을 구별해서 써야 한다.

시뮬레이션 결과 (62 타겟 기록 재생, 타겟 단위 clustered bootstrap):
예산 50 에서 +7.6 [2, 17], 120 에서 +18.8 [5, 45], 480 에서 +73.4 [20, 172].
대조군은 k 를 사후 최적값으로 고른 static top-K 라 우리 주장에 보수적이다.
출처: `public_data/benchmark/gate0/allocation_simulation_oof.json`

⟦전향적 검증 — 개발에 쓰지 않은 12 타겟, 6×24 격자. 결과 채움⟧

---

## Figure 1C — 평가와 최종 후보 선정

```
Structural evaluation
        ↓
Successful / viable candidates
        ↓
Candidate prioritization

[Validated / measured]
├─ Structural quality      pLDDT, 연속 RMSD
├─ SoluProt                pre-specified objective constraint
└─ Diversity               위치 엔트로피, 쌍별 거리

[Auxiliary annotations]
├─ Aggregation liability   Gate 1B ranking NO-GO
├─ Stability               Rosetta ↔ pLDDT rho ~ -0.36 · tie-break only
└─ Novelty                 정의와 검증 미확정
        ↓
   Final candidates
```

### 구조 품질은 이진으로 끝내지 않는다

게이트는 최소 수용 기준을 정하고, 통과 이후에는 연속값을 유지한다. 둘 다
`pLDDT >= 85, RMSD <= 2.0 A` 를 통과해도 pLDDT 96 / RMSD 0.8 A 와
pLDDT 86 / RMSD 1.9 A 는 같은 후보가 아니다.

온도 분석이 이를 뒷받침한다. 패널 1 에서 이진 endpoint 는 판정 불가였으나
(정보 백본 4/15) 연속 pLDDT 는 T=0.2 의 열세를 CI 0 제외로 잡았다
(-1.19 [-2.08, -0.39]).

### SoluProt 은 제약이지 연속 순위 변수가 아니다

검증된 정책은 `SoluProt >= 0.5` 라는 제약이다. "0.91 이 0.70 보다 나으니
우선한다" 는 **별도의 정책이고 검증되지 않았다.** 최종 후보 선택에서 SoluProt
연속값이 값어치가 있다는 것을 따로 확인한 뒤에 올린다.

SoluProt 은 대장균 가용 발현 예측기이지 AF2 pLDDT/RMSD 예측기가 아니다.
같은 타겟 안에서 어느 서열이 구조를 유지할지 가리는 능력은 타겟 내 AUROC
중앙값 0.540 이다.

### 보조 annotation 인 이유

**Aggregation** — SoluProt 위에 타겟 내 구조 성공 랭킹 정보를 더하지 않는다
(+0.014 [-0.110, +0.134], 정보 타겟 11/20). pooled 지표는 개선처럼 보이지만
(AUROC 0.261 → 0.428) 그것은 타겟 난이도를 더 잘 맞힌 것이다. NO-GO for
Gate 1B promotion, Gate 1A developability annotation 으로 유지.
이 판단은 구조 성공 랭킹에만 적용되고, 실험적 developability·발현·응집
결과에 값어치가 없다는 뜻이 아니다.
출처: `public_data/benchmark/gate0/incremental_information_test.json`

**Stability** — 백본 안에서 Rosetta score 가 pLDDT 를 따라간다
(rho -0.356, 117 백본 중 90.6% 같은 방향). **독립 축이 아니므로 구조 품질과
나란히 순위에 넣으면 같은 신호를 두 번 센다.** 게이트로 쓰면 백본 내 중앙값
컷에서 pLDDT 상위 10% 설계의 32.6% 를 버린다 (무작위 게이트라면 50%). ThermoMPNN 은 학습이
FireProtDB/MegaScale 점변이라 de novo 다중 변이 설계에 맞춰본 적이 없고
다중 변이는 에피스테이시스를 무시한 가법 합이다.
출처: `public_data/benchmark/gate0/stability_shadow_gate.json`

**Novelty** — 레지스트리 `objective_status` 에 항목이 없다. 파이프라인
`_STAGE_ORDER` 에 이름만 있다. 그림에 넣으려면 무엇을 재는지부터 정의해야
한다.

---

## 도식에 넣지 않는 것

- **Binder / small-molecule** — task plugin 이지 일반 filter 가 아니다.
  DiffDock 과 Boltz2 는 워커 누적 실행 0 건이다.
- **NetSolP, AggreProt, CamSol** — 같은 축이라 정보 중복 가능성이 크고,
  우리 휴리스틱으로 그 축을 재보니 Gate 1B 이득이 없었다.
- **ESMFold 중간 계층** — 비용 사다리를 한 단 늘리는 것은 adaptive allocation
  서사를 강화하지만 v2 다. 현재 실험 중간에 넣지 않는다.

## 아직 비어 있는 칸

1. 전향적 홀드아웃 결과 (Figure 1B)
2. Novelty 의 정의
3. 실행 루프가 `allocation_next_action` 을 부르는 배선
