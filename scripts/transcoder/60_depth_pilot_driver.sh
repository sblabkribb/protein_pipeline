#!/usr/bin/env bash
# 깊이 확장 파일럿을 설계 -> 폴딩으로 끝까지 돌린다.
#
# 왜 셸 드라이버인가: 두 단계가 하루에 걸쳐 있고 각각 재개 가능하다. 설계는
# candidates_ext.json 의 backbone_key 로, 폴딩은 af2_order_metric.csv 의
# sequence_id 로 이미 한 것을 건너뛴다. 죽으면 다시 부르면 된다.
#
# 동결값은 여기 없다. 전부 59_ 가 사전지정에서 읽거나 상수로 갖고 있다.
set -u
cd /opt/protein_pipeline-work
PY=/opt/protein_pipeline/venv/bin/python
LOG=logs/hier

mkdir -p "$LOG"
# 앞서 timeout 으로 죽은 설계 프로세스가 남아 있으면 끝나기를 기다린다.
while pgrep -f "59_extend_depth_pilot.py --stage design" >/dev/null 2>&1; do
  sleep 20
done

echo "=== [A] 설계 재개 $(date -u +%FT%TZ)"
until $PY scripts/transcoder/59_extend_depth_pilot.py --stage design \
      >>"$LOG/design.log" 2>&1; do
  echo "  설계가 0 이 아닌 코드로 끝났다. 진행분은 남아 있으므로 다시 붙는다."
  sleep 30
done
echo "=== [A] 설계 완료 $(date -u +%FT%TZ)"

echo "=== [C] 폴딩 시작 $(date -u +%FT%TZ)"
$PY scripts/transcoder/59_extend_depth_pilot.py --stage fold \
    --fold-workers 4 >>"$LOG/fold.log" 2>&1
echo "=== [C] 폴딩 종료 $(date -u +%FT%TZ)"
