#!/usr/bin/env bash
# 격자가 끝나면 패널 2 의 실패 13 건을 재시도하고 판정이 바뀌는지 본다.
#
# 실패는 전부 ConnectionError 로, 설계 품질과 무관한 일시적 워커 끊김이다.
# 다만 T=0.3 이 6 건으로 가장 많이 잃었고 하필 가장 큰 효과를 보인 조건이라,
# 무작위 결측이라는 근거만으로 넘기지 않고 채워서 확인한다.
set -uo pipefail
cd /opt/protein_pipeline-work

# 워커 호스트는 저장소에 적지 않는다. 릴리스 체크리스트가 내부 주소 공개를
# 금지하므로 스크립트 기본값을 비웠고, 여기서 환경변수로 넣는다.
# .env 를 통째로 source 하면 셸이 그 내용을 명령으로 실행한다. 실제로 이 파일에는
# 주석 표시 없는 줄이 있어 "command not found" 가 났다. 필요한 변수만 뽑는다.
RAPID_GPU_HOST="$(sed -n 's/^RAPID_GPU_HOST=//p' \
  /opt/protein_pipeline/pipeline-mcp/.env | tail -1)"
export RAPID_GPU_HOST
: "${RAPID_GPU_HOST:?RAPID_GPU_HOST 가 필요하다 (.env 확인)}"
GRID_PID="${1:?격자 체인 PID}"
B=public_data/benchmark/gate0

while kill -0 "$GRID_PID" 2>/dev/null; do sleep 120; done
echo "[$(date +%H:%M)] 격자 체인 종료 (pid $GRID_PID)"

echo
echo "=============== 실패 13 건 재시도 ==============="
# 22_refold 가 이제 ok 만 완료로 세고 실패 행은 스스로 재시도한다. 예전에는
# 여기서 CSV 를 미리 손봐야 했는데, 그 우회는 근원을 고치면서 없앴다.
python3 scripts/transcoder/22_refold_with_artifacts.py --only panel2 --workers 4
echo "재시도 종료 코드 $?"

echo
echo "=============== 패널 2 재분석 (동결된 spec) ==============="
python3 scripts/transcoder/11_temperature_af2_analysis.py \
  --af2 "$B/temperature_panel2/af2_order_metric.csv" \
  --cluster-unit target_id \
  --panel panel2_informative \
  --panel-manifest "$B/temperature_panel2/panel_manifest.json" \
  --compare-panel "$B/temperature_sweep/af2_analysis_order.json" \
  --out "$B/temperature_panel2/af2_analysis_order_complete.json"
echo "재분석 종료 코드 $?"

echo
echo "=============== 재시도분 S3 보관 ==============="
python3 scripts/transcoder/28_archive_fold_artifacts.py \
  --dir public_data/benchmark/gate0/temperature_panel2
echo "보관 종료 코드 $?"

echo
echo "=============== 리간드 결합 부위 1 단계 (자기도킹, 배선 점검) ==============="
# DiffDock 은 GPU0 이고 격자는 CPU 에 묶여 있다. 격자가 끝난 뒤라 경합이 없다.
python3 scripts/transcoder/33_ligand_pocket_preservation.py --stage self
echo "자기도킹 종료 코드 $?"

echo
echo "=============== 안정성 annotation 비교 ==============="
# ThermoMPNN 을 native-백본 설계에 돌리고 Rosetta·pLDDT·RMSD·변이수와 비교한다.
# SPURS 는 자동 설치하지 않는다 - 이 결과를 보고 사람이 결정한다.
# 확인 가능한 것: 중복성·적용 가능성·불일치·이상 동작.
# 확인 불가능한 것: 누가 맞는지 (wet-lab 안정성 라벨이 없다).
python3 scripts/transcoder/37_stability_annotation_comparison.py --limit 300
echo "안정성 비교 종료 코드 $?"
echo "[$(date +%H:%M)] 완료"
