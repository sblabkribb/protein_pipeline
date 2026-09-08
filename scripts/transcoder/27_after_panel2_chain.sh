#!/usr/bin/env bash
# 패널 2 재폴딩 -> 두 패널 분석 -> (백본 생성 완료 대기) -> 홀드아웃 격자.
#
# 격자는 ColabFold 4 워커를 전부 쓴다. 백본 생성이 재폴딩보다 오래 걸리므로
# 생성 완료를 기다리는 것만으로 재폴딩과의 경합이 자연히 피해진다.
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

REFOLD_PID="${1:?재폴딩 PID}"
GEN_PID="${2:-}"   # 더 이상 기다리지 않는다. 예비 생성을 체인 안에서 돌린다.
B=public_data/benchmark/gate0

wait_for () {  # $1=pid $2=이름
  while kill -0 "$1" 2>/dev/null; do sleep 60; done
  echo "[$(date +%H:%M)] $2 종료 (pid $1)"
}

echo "[$(date +%H:%M)] 대기 시작 · 재폴딩 $REFOLD_PID"
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
echo "=============== 패널 1/2 산출물 S3 보관 ==============="
# .gitignore 가 *.pdb.gz 를 막으므로 좌표의 사본은 S3 에만 있다.
# 멱등이라 이미 올라간 것은 건너뛴다.
python3 scripts/transcoder/28_archive_fold_artifacts.py \
  --dir public_data/benchmark/gate0/temperature_sweep \
  --dir public_data/benchmark/gate0/temperature_panel2
echo "보관 종료 코드 $?"

echo
echo "=============== 홀드아웃 예비 백본 생성 ==============="
# 재폴딩과 병행하면 ColabFold 가 CPU 에 묶여 있어 3 배 느려진다
# (54 -> 164 s/폴드). 그래서 재폴딩이 끝난 뒤에 돌린다.
python3 scripts/transcoder/25_generate_holdout_backbones.py --use-reserve 6
echo "예비 생성 종료 코드 $?"

echo
echo "=============== 홀드아웃 타겟 확정 (4/4/4) ==============="
python3 scripts/transcoder/29_resolve_holdout_targets.py --write
echo "확정 종료 코드 $?"

echo
echo "=============== 홀드아웃 격자 ==============="
python3 scripts/transcoder/26_holdout_grid.py --workers 4
echo "격자 종료 코드 $?"

echo
echo "=============== 격자 산출물 S3 보관 ==============="
python3 scripts/transcoder/28_archive_fold_artifacts.py \
  --dir public_data/benchmark/gate0/holdout_grid
echo "보관 종료 코드 $?"
echo "[$(date +%H:%M)] 체인 완료"
