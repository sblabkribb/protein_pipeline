"""2축 게이팅 실험의 동결된 상수와 측정 primitive.

정의의 출처는 docs/specs/2026-09-10-surrogate-rapid-2d-gate-design.md 하나다.
이 파일의 숫자를 바꾸면 스펙을 위반한다 - 결과를 보고 바꾸지 않는다.
"""

from __future__ import annotations

#: joint-pass 문턱. THRESHOLD_PROVENANCE 에서 고정됐고 이 실험에서 다시 고르지 않는다.
PLDDT_MIN = 85.0
RMSD_MAX = 2.0
SOLUPROT_MIN = 0.5

#: Δ_Top4 의 K. m2_endpoint_dynamic_range.json 의 min_probe_per_unit 과 같은 값.
TOP_K = 4

#: GO 문턱.
GATE2_DELTA_MIN = 0.10
GATE1_RHO_MIN = 0.25

#: 단측 LCB 의 alpha. 90% LCB 이므로 0.10.
LCB_ONE_SIDED_ALPHA = 0.10

#: 이보다 적으면 판정하지 않는다. holdout_experiment_spec.json 규칙 승계.
MIN_INFORMATIVE_TARGETS = 8

#: 부트스트랩 시드. 스펙의 시뮬레이션과 같은 값을 쓴다.
BOOTSTRAP_SEED = 20260910
