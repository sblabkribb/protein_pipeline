#!/usr/bin/env bash
#: 확증 격자 폴딩이 끝나면 동결된 네 분석을 차례로 돌린다.
#:
#:   42_  수확      hierarchical-confirmatory-prespec.md   주 종점 G 차이
#:   39_  분해      selection-gain-decomposition-prespec.md 주 종점 Between-Within
#:   40_  coverage  coverage-preserving-prespec.md          주 종점 EFBC
#:   41_  구조      같은 문서 §6                            CA-RMSD dispersion
#:   45_  진단      docs/notes/stop-rule-diagnosis.md       판정 아님
#:
#: 42_ 가 ESM 임베딩 캐시를 만들고 39_ 가 그것을 다시 쓴다. 41_ 은 40_ 의
#: replay 를 불러 쓰므로 순서를 바꾸지 않는다.
set -uo pipefail
cd /opt/protein_pipeline-work

PY=/opt/protein_pipeline/venv/bin/python
CSV=public_data/benchmark/gate0/hier_confirmatory/af2_order_metric.csv
TOTAL=7728
DRIVER_PID="${DRIVER_PID:-0}"
LOG=logs/hier/analyses.log
mkdir -p logs/hier

say() { echo "=== $(date -u +%FT%TZ) $*" | tee -a "$LOG"; }

say "대기 시작 · 목표 ${TOTAL} 행 · 드라이버 PID ${DRIVER_PID}"
while :; do
  rows=$(( $(wc -l < "$CSV") - 1 ))
  alive=0
  [ "$DRIVER_PID" != "0" ] && kill -0 "$DRIVER_PID" 2>/dev/null && alive=1
  if [ "$rows" -ge "$TOTAL" ]; then say "행 ${rows}/${TOTAL} 도달"; break; fi
  if [ "$alive" = "0" ]; then say "드라이버 종료 · 행 ${rows}/${TOTAL}"; break; fi
  sleep 300
done

#: 마지막 폴드가 CSV 에 기록될 때까지 잠깐 둔다.
sleep 120
rows=$(( $(wc -l < "$CSV") - 1 ))
ok=$(awk -F, 'NR>1 && $0 ~ /,ok,/ {n++} END{print n+0}' "$CSV")
say "폴딩 마감 · 행 ${rows} · ok ${ok}"

#: MPNN 은 CPU 채점이라 폴딩과 겹치면 서로 느려진다. 폴딩이 끝난 뒤 돌린다.
say "43_ MPNN 채점"
nice -n 10 "$PY" scripts/benchmark/43_mpnn_scores_hier.py >>"$LOG" 2>&1 \
  || say "43_ 실패 (mpnn_only arm 없이 진행한다)"

for step in \
  "42_hierarchical_confirmatory.py|수확 (주 종점 G 차이)" \
  "39_selection_gain_decomposition.py|선택 이득 분해 (Between-Within)" \
  "40_coverage_preserving.py|coverage (EFBC)" \
  "41_structural_dispersion.py|구조 dispersion" \
  "45_stop_rule_diagnosis.py|STOP 규칙 진단 (판정 아님)"
do
  s="${step%%|*}"; d="${step##*|}"
  say "${s} — ${d}"
  if "$PY" "scripts/benchmark/${s}" >>"$LOG" 2>&1; then
    say "${s} 완료"
  else
    say "${s} 실패 (아래 로그 참조). 다음 분석을 계속한다."
  fi
done

say "네 분석 종료"
