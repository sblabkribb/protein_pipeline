#!/usr/bin/env bash
# wave 2/3 백본 증량이 끝나면 온도 sweep 의 paired AF2 480 을 돌리고 판정까지 이어간다.
#
# 증량 캠페인과 ColabFold 워커를 공유하므로 순서를 지켜야 한다. 동시에 돌리면
# 서로 큐에서 밀려 두 실험 모두 느려지고, 온도 비교의 wall-clock 도 오염된다.
set -u
cd /opt/protein_pipeline-work

MAX_WAIT_S=${MAX_WAIT_S:-86400}
started=$(date +%s)

echo "[chain] waiting for wave 2/3 to finish"
while pgrep -f "04d_run_gate0_campaign.py" > /dev/null; do
  now=$(date +%s)
  if [ $((now - started)) -ge "$MAX_WAIT_S" ]; then
    echo "[chain] max wait reached; proceeding anyway"
    break
  fi
  sleep 120
done
echo "[chain] waves done after $(( $(date +%s) - started ))s"

export PYTHONPATH=pipeline-mcp/src
echo "[chain] AF2 480 (paired, index 0-7)"
python3 scripts/transcoder/10_temperature_af2.py \
  --out public_data/benchmark/gate0/temperature_sweep/af2_stage1.csv || {
    echo "[chain] AF2 stage failed"; exit 1; }

echo "[chain] clustered analysis"
python3 scripts/transcoder/11_temperature_af2_analysis.py || {
    echo "[chain] analysis failed"; exit 1; }

echo "[chain] done"
