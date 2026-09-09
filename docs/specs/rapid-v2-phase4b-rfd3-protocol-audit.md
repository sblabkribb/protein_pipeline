# Phase 4B — RFD3 생성 프로토콜 audit

**판정: A (조건부).** calibration 생성 분포는 holdout 과 **정확히** 같다.
다만 프로토콜 자체에 결정되지 않은 것 하나와 실제 결함 하나가 있어 함께
기록한다. 둘 다 두 코호트에 **동일하게** 적용되므로 calibration 목적에는
영향이 없다.

폴딩은 하지 않았다. joint-pass · SoluProt · pLDDT · EFBC 를 계산하지 않았다.
backbone 을 추가 생성하지 않았고 51 개를 삭제하지 않았다.

---

## 1. 실제 실행된 RFD3 spec

request 객체가 아니라 endpoint 로 간 최종 spec (`rfd3/inputs.json`,
`rfd3/mode.json`) 이다.

세 타겟 모두 **완전히 동일한 형태**다.

```
mode                     local_diversify
requested/effective      partial_t 5.0
sampling_strategy        auto
target_rmsd_cutoff       2.0
backbone_filter_use_dssp true
max_attempted_designs    15
requested_final_count    5
design chain             A
fail_on_duplicate        false
ligand                   (없음 - spec 에 항목 자체가 없다)

spec-1:
  input                  input.pdb
  contig                 A2-<마지막 잔기>
  unindex                A1
  select_fixed_atoms     {"A1": "ALL"}
  partial_t              5.0
```

| 타겟 | contig | select_fixed_atoms | 결과 |
|---|---|---|---|
| 1j0tA00 (5/5) | A2-77 | {A1: ALL} | 5 통과 |
| 5nazA00 (2/15) | A2-226 | {A1: ALL} | 2 통과 |
| 2r01A02 (0/15) | A2-191 | {A1: ALL} | 0 통과 |

**세 타겟의 조건이 구조적으로 같다.** 실패가 서로 다른 conditioning 때문이
아니다.

## 2. `select_fixed_atoms` 의 정체 — 위치 앵커다

`pipeline_mcp/infer_rfd3.py::get_inferred_enzyme_fields`:

```python
first_res = residues[0]
unindex = f"{first_chain}{first_res.resseq}"                    # A1
contig  = f"{first_chain}{residues[1].resseq}-{last_res.resseq}" # A2-N
select_fixed_atoms = {unindex: "ALL"}                            # {A1: ALL}
```

**첫 잔기를 첫 잔기라는 이유로 고정한다.** 보존도에서 온 것도, 촉매 잔기도,
리간드 접촉도 아니다. 함수 이름의 `enzyme` 은 리간드/촉매 conditioning 을
염두에 둔 흔적으로 보이지만, 리간드가 없는 CATH 도메인에서는 "잔기 1 고정" 으로
축퇴한다.

즉 사실상 **구조 전체가 partial diffusion 대상**이고 앵커 하나만 박혀 있다.

## 3. 입력 구조 audit

```
chain            세 타겟 모두 A 단일
HETATM           0 (12 타겟 전부)
ligand           없음 → 리간드 conditioning 은 이 코호트에서 공허하다
A1 존재          세 타겟 모두 존재 (select_fixed_atoms 대상이 실재한다)
```

**발견된 결함: altLoc 중복이 RFD3 입력까지 들어간다.**

```
1j0tA00   CA  77 · 고유 resseq  77 · altLoc 잔기  0
5nazA00   CA 228 · 고유 resseq 226 · altLoc 잔기  2   (LYS A37 A/B 등)
2r01A02   CA 201 · 고유 resseq 191 · altLoc 잔기 10   (VAL A6 A/B 등)
```

25_ 의 전처리는 "첫 모델만 · CA 없는 잔기 제거 · 음수 resseq 제거 · 1 부터
재번호" 를 하지만 **altLoc 을 정리하지 않는다.** 같은 잔기에 CA 가 둘 들어간
구조가 RFD3 와 수용 게이트로 간다.

### 이 결함이 shortfall 의 원인인가 — 아니다

처음에 세 타겟만 보고 dose-response 라고 적었는데, 12 개 전부 보면 성립하지
않는다.

```
altLoc 0  → backbone [5, 5, 5, 5, 4, 5]
altLoc 2  → [2, 5, 5]
altLoc 10 → [0, 5]
altLoc 11 → [5]
```

7o1zA01 은 altLoc 10 개인데 5/5 를 채웠고, 2mq6A00 은 altLoc 0 인데 4 개다.
**altLoc 은 실제 데이터 위생 결함이지만 수용률을 설명하지 않는다.**

### 생성된 backbone 은 깨끗하다

```
5nazA00 출력  CA 226 · 고유 226 · 중복 0
3f2pA01 출력  CA 316 · 고유 316 · 중복 0
```

RFD3 가 conformer 하나로 정리한다. 따라서 영향 범위는 **입력과 생성 시점
수용 게이트까지**이고, 동결된 v1 구조 지표(각 backbone 자신의 PDB 를 기준으로
쓴다)는 오염되지 않았다.

### holdout 도 같은 결함을 갖는다

동결된 holdout 12 타겟 중 **3 개**가 오염돼 있다.

```
3es1A01 (altLoc 2) · 3f2pA01 (4) · 5pc8A00 (1)
```

이것이 오히려 calibration 에는 유리하다 - 같은 결함이 두 코호트에 같은 방식으로
있으므로 생성 분포가 어긋나지 않는다.

## 4. shortfall 의 실제 원인 — 게이트와 RMSD 분포

게이트는 `target_ca_rmsd_dssp_non_loop`, 컷 2.0 Å.

| 타겟 | mask/CA | 시도 | 통과 | RMSD 중앙 | 최소 | 최대 |
|---|---|---|---|---|---|---|
| 1j0tA00 | 52% | 5 | 5 | 1.54 | 1.34 | 1.69 |
| 4poaA02 | 60% | 5 | 5 | 1.85 | 1.80 | 1.94 |
| 4y07A01 | 64% | 15 | 5 | 2.04 | 1.70 | 2.27 |
| **2mq6A00** | 62% | 15 | 4 | 2.16 | 1.74 | 2.94 |
| **5nazA00** | 50% | 15 | 2 | 2.20 | 1.64 | 2.90 |
| **2r01A02** | 53% | 15 | **0** | 2.58 | **2.24** | 3.13 |

**2r01A02 는 15 개 전부가 게이트 위에 있다** (최소 2.24 > 2.0). mask 비율은
부족 타겟 50-62%, 완료 타겟 52-74% 로 겹쳐서 구분하지 못한다.

원인은 **partial_t = 5.0 의 확산 폭이 이 타겟들에서 2.0 Å 게이트를 넘는 것**
이다. 잘못된 설정이 아니라 타겟 × 프로토콜 상호작용이다.

## 5. constraint data-flow

| constraint | RFD3 입력? | RFD3 에서 의미 | ProteinMPNN 입력? | 코드 경로 | calibration 적용? |
|---|---|---|---|---|---|
| MMseqs2 MSA | ❌ | — | ❌ | `start_from="rfd3"` 로 건너뜀. `msa/` 항목 0 | 아니오 |
| conservation tier 30/50/70 | ❌ | — | ❌ | `26_.generate_sequences` 가 fixed_positions 를 넘기지 않는다 | **아니오** |
| manual/fixed positions | ❌ | — | ❌ | 요청에 없음 | 아니오 |
| ligand 6 Å mask | ❌ | — | ❌ | 이 코호트 HETATM 0 | 해당 없음 |
| `select_fixed_atoms` | ✅ | 좌표 고정 | — | `infer_rfd3.get_inferred_enzyme_fields` | 예 — 단 `{A1: ALL}` 위치 앵커 |

**conservation mask 를 `select_fixed_atoms` 로 변환한 곳은 없다.** 가정하지
말라는 지적대로, 둘은 실제로 연결돼 있지 않다. MSA 보존도는 서열 설계 제약이고
`select_fixed_atoms` 는 좌표 제약인데, 이 파이프라인에서는 **전자가 아예 쓰이지
않고** 후자는 위치 앵커다.

### 부수 발견 — fingerprint 가 실제보다 많이 주장한다

격자 manifest 의 `protocol_fingerprint` 에 `tiers: [0.5]` 가 적혀 있는데,
`26_.generate_sequences` 는 ProteinMPNN 에 fixed position 을 넘기지 않는다.
**기록이 적용되지 않은 제약을 주장한다.** 원고 §2.4 는 tier 를 주장하지 않으므로
논문 서술에는 영향이 없지만, manifest 를 읽는 사람은 오해할 수 있다.

## 6. calibration vs deployment 분포 비교

| 항목 | calibration | holdout (deployment) | 일치 |
|---|---|---|---|
| mode | local_diversify | local_diversify | ✅ |
| partial_t | 5.0 | 5.0 | ✅ |
| contig / unindex | A2-N / A1 | A2-N / A1 | ✅ |
| select_fixed_atoms | {A1: ALL} | {A1: ALL} | ✅ |
| ligand handling | 없음 (HETATM 0) | 없음 | ✅ |
| design chain | A | A | ✅ |
| RMSD gate | 2.0 · dssp_non_loop | 2.0 · dssp_non_loop | ✅ |
| max_attempted | 15 | 15 | ✅ |
| sampling_strategy | auto | auto | ✅ |
| 입력 전처리 | 동일 (altLoc 미정리 포함) | 동일 | ✅ |

**분포 불일치 없음.** blocker 아님.

## 7. 판정

### A — 조건부 통과

```
현재 51 backbone 유지 가능
2r01A02 를 CALIBRATION_GENERATION_INFEASIBLE 로 유지 가능
11-target / 408-fold 로 진행 가능
```

근거: calibration 생성 분포가 holdout 과 모든 축에서 일치한다. calibration 의
목적은 "holdout replay 에 적용할 사후분포" 를 얻는 것이므로, 두 분포가 같다는
것이 요구 조건이고 그것이 충족된다.

### 함께 기록하는 두 가지

**(1) `select_fixed_atoms {A1: ALL}` 은 결정된 적이 없다.**
generic 추론 함수가 낸 위치 앵커다. "RAPID redesign 에서 무엇을 좌표 고정할
것인가" 는 아직 과학적으로 정해지지 않았다. 이것은 §5-C 의 성격이지만,
**calibration 과 deployment 에 동일하게 적용되므로 이번 calibration 을 막지
않는다.** v2.0 deployment protocol 을 동결할 때 별도로 결정해야 한다.

**(2) altLoc 미정리는 고쳐야 하지만 지금 고치면 안 된다.**
지금 전처리를 고치면 calibration 이 holdout 과 달라져 calibration 의 목적이
깨진다. 다음 프로토콜 버전에서 **두 코호트에 동시에** 적용한다.

### 하지 않는 것

```
altLoc 을 지금 고쳐 재생성          → calibration ≠ deployment 가 된다
부족 타겟만 재생성                  → 관측된 결과에 코호트를 맞추는 것이다
conservation 30/50/70 을
  select_fixed_atoms=ALL 로 변환    → 근거 없는 변환. 두 제약은 다른 층이다
```
