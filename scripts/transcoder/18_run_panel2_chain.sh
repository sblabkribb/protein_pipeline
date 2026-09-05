#!/usr/bin/env bash
# 패널 2 생성 -> 패널 2 AF2 -> 패널 1 재측정 순으로 이어 돌린다.
#
# 패널 1 을 다시 도는 이유: 원래 480 폴드는 전체 CA kabsch RMSD 로 측정되었고,
# 그것은 게이트 0 의 2.0 A 임계값이 정해진 정의가 아니다. 두 패널을 나란히
# 보고하려면 같은 자로 재야 한다. 원본 CSV 는 지우지 않는다 - 그 파일이 버그의
# 기록이다.
set -uo pipefail
cd /opt/protein_pipeline-work
BASE=public_data/benchmark/gate0
P2=$BASE/temperature_panel2

echo "=== [1/3] 패널 2 서열 생성 $(date -Is) ==="
python3 scripts/transcoder/09_temperature_sweep.py \
  --panel-manifest $P2/panel_manifest.json --out-dir $P2 --mpnn-timeout 900 || exit 1

echo "=== [2/3] 패널 2 AF2 $(date -Is) ==="
python3 scripts/transcoder/10_temperature_af2.py \
  --sequences $P2/sequences.csv --out $P2/af2_stage1.csv --workers 4 || exit 1

echo "=== [3/3] 패널 1 재측정 (수정된 RMSD) $(date -Is) ==="
python3 scripts/transcoder/10_temperature_af2.py \
  --sequences $BASE/temperature_sweep/sequences.csv \
  --out $BASE/temperature_sweep/af2_stage1_rmsd_fixed.csv --workers 4 || exit 1

echo "=== 완료 $(date -Is) ==="
