#!/usr/bin/env bash
# 패널 2 재폴딩 -> 두 패널 분석 -> (백본 생성 완료 대기) -> 홀드아웃 격자.
#
# 격자는 ColabFold 4 워커를 전부 쓴다. 백본 생성이 재폴딩보다 오래 걸리므로
# 생성 완료를 기다리는 것만으로 재폴딩과의 경합이 자연히 피해진다.
set -uo pipefail
cd /opt/protein_pipeline-work

REFOLD_PID="${1:?재폴딩 PID}"
GEN_PID="${2:?백본 생성 PID}"
B=public_data/benchmark/gate0

wait_for () {  # $1=pid $2=이름
  while kill -0 "$1" 2>/dev/null; do sleep 60; done
  echo "[$(date +%H:%M)] $2 종료 (pid $1)"
}

echo "[$(date +%H:%M)] 대기 시작 · 재폴딩 $REFOLD_PID · 생성 $GEN_PID"
wait_for "$REFOLD_PID" "재폴딩"

echo
echo "=============== 패널 2 분석 (동결된 spec) ==============="
python3 scripts/transcoder/11_temperature_af2_analysis.py \
  --af2 "$B/temperature_panel2/af2_order_metric.csv" \
  --cluster-unit target_id \
  --panel panel2_informative \
  --panel-manifest "$B/temperature_panel2/panel_manifest.json" \
  --compare-panel "$B/temperature_sweep/af2_analysis_order.json" \
  --out "$B/temperature_panel2/af2_analysis_order.json"
echo "패널 2 분석 종료 코드 $?"

echo
echo "=============== 패널 1 재확인 (변동 없음 확인용) ==============="
python3 scripts/transcoder/11_temperature_af2_analysis.py \
  --af2 "$B/temperature_sweep/af2_order_metric.csv" \
  --cluster-unit backbone_key \
  --panel panel1_unfiltered \
  --out "$B/temperature_sweep/af2_analysis_order.json"
echo "패널 1 분석 종료 코드 $?"

echo
wait_for "$GEN_PID" "백본 생성"
echo
echo "=============== 홀드아웃 격자 6 x 24 x 12 ==============="
python3 scripts/transcoder/26_holdout_grid.py --workers 4
echo "격자 종료 코드 $?"
echo "[$(date +%H:%M)] 체인 완료"
