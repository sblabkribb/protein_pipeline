#!/usr/bin/env bash
#
# 원고와 보충자료의 표·그림을 저장된 구조예측 격자에서 다시 만든다.
#
# 이 스크립트는 구조예측(AlphaFold2/ColabFold)을 다시 수행하지 않는다.
# 이미 저장된 격자(af2_order_metric.csv)와 ESM-2 임베딩 캐시를 입력으로
# 분석 코드만 재실행하고, 그 결과를 저장소의 원본 결과 파일과 대조한다.
#
# 사용법:
#   bash scripts/reproduce_paper_tables_figures.sh            # 분석 + 대조 + 그림
#   REPRO_SKIP_FIGURES=1 bash scripts/reproduce_paper_tables_figures.sh
#
# 필요한 환경: Python 3.12 이상, numpy, scikit-learn, matplotlib.
# ESM-2 임베딩 캐시가 data/benchmark/ 에 있으면 네트워크 접근이 필요 없다.
# 캐시가 없으면 ESM_EMBEDDING_URL 로 임베딩 서버를 지정해야 한다.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

GATE0="public_data/benchmark/gate0"
OUT="${REPRO_OUT:-$(mktemp -d -t rapid-repro-XXXXXX)}"
PY="${PYTHON:-python3}"
CMP="scripts/benchmark/_compare_results.py"

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export MPLBACKEND="${MPLBACKEND:-Agg}"

mkdir -p "$OUT"

echo "재현 출력: $OUT"
echo "Python:    $($PY -c 'import sys; print(sys.version.split()[0])')"
$PY - <<'PYV'
for name in ("numpy", "sklearn", "scipy", "matplotlib"):
    try:
        mod = __import__(name)
        print(f"  {name:12s} {getattr(mod, '__version__', '?')}")
    except ImportError:
        print(f"  {name:12s} (없음)")
PYV
echo

# 분석 이름: 스크립트 : 결과 파일
ANALYSES=(
  "실험 2 기준선:scripts/benchmark/33_v2_mpnn_baseline.py:v2_mpnn_baseline"
  "초기 배분 평가:scripts/benchmark/35_hierarchical_replay.py:hierarchical_replay"
  "깊이 확장:scripts/benchmark/37_depth_scaling.py:depth_scaling"
  "선택 이득 분해:scripts/benchmark/39_selection_gain_decomposition.py:selection_gain_decomposition"
  "EFBC 분산도:scripts/benchmark/40_coverage_preserving.py:coverage_preserving"
  "구조 분산 진단:scripts/benchmark/41_structural_dispersion.py:structural_dispersion"
  "후속 평가 주 분석:scripts/benchmark/42_hierarchical_confirmatory.py:hierarchical_confirmatory"
  "종료 규칙 진단:scripts/benchmark/45_stop_rule_diagnosis.py:stop_rule_diagnosis"
)

fail=0
ran=0
figfail=0
for entry in "${ANALYSES[@]}"; do
  IFS=: read -r label script stem <<<"$entry"
  orig="$GATE0/$stem.json"
  if [[ ! -f "$script" ]]; then
    echo "[건너뜀] $label — $script 없음"
    continue
  fi
  if [[ ! -f "$orig" ]]; then
    echo "[건너뜀] $label — 원본 결과 $orig 없음"
    continue
  fi
  echo "[실행] $label"
  if ! $PY "$script" --out "$OUT/$stem.json" >"$OUT/$stem.log" 2>&1; then
    echo "  실행 실패. 로그: $OUT/$stem.log"
    tail -5 "$OUT/$stem.log" 2>/dev/null | sed 's/^/      /' || true
    fail=$((fail + 1))
    continue
  fi
  ran=$((ran + 1))
  $PY "$CMP" "$orig" "$OUT/$stem.json" || fail=$((fail + 1))
done

echo
if [[ "${REPRO_SKIP_FIGURES:-0}" != "1" ]]; then
  for fig in scripts/paper_runs/61_manuscript_figures_en.py \
             scripts/paper_runs/62_confirmatory_figures_en.py; do
    if [[ -f "$fig" ]]; then
      echo "[그림] $fig"
      $PY "$fig" >"$OUT/$(basename "$fig" .py).log" 2>&1 \
        || { echo "  실패(경고). 로그: $OUT/$(basename "$fig" .py).log";
             figfail=$((figfail + 1)); }
    fi
  done
  echo "  그림 출력: figures/submission/"
fi

echo
echo "재실행 $ran개 · 수치 불일치/실행 실패 $fail건"
if [[ $figfail -gt 0 ]]; then
  echo "그림 생성 실패 $figfail건 (matplotlib 가 필요하다). 수치 판정과는 별개다."
fi
echo "출력 디렉터리: $OUT"
[[ $fail -eq 0 ]] || exit 1
