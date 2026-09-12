#!/usr/bin/env bash
# RAPID v2.0 multi-source 캠페인을 backbones -> design -> fold 로 끝까지 돌린다.
#
# 왜 셸 드라이버인가: 세 단계가 며칠에 걸쳐 있고, 각 단계는 그 자체로 재개
# 가능하다. 한 프로세스로 묶어 두면 중간에 죽었을 때 어디까지 갔는지가
# 프로세스 상태에 숨는다. 단계마다 따로 부르고 로그를 나눠 남긴다.
#
# 동결값은 하나도 여기 없다. 전부 52_ 가 multisource_validation_plan.json
# 에서 읽는다.
set -u

cd /opt/protein_pipeline-work

export RAPID_GPU_HOST="${RAPID_GPU_HOST:-211.188.35.221}"
export RFD3_HTTP_URL="${RFD3_HTTP_URL:-http://$RAPID_GPU_HOST:18104}"
export BIOEMU_HTTP_URL="${BIOEMU_HTTP_URL:-http://$RAPID_GPU_HOST:18103}"
export PROTEINMPNN_GPU_URL="${PROTEINMPNN_GPU_URL:-http://$RAPID_GPU_HOST:18101}"

# 생성 워커의 폴링 상한. 기본값은 21600 s(6 h) 인데, BioEmu 는 job 을 잃고
# 워커가 유휴인 채로 클라이언트만 매달리는 stall 이 실측으로 세 번 나왔다.
# 정상 실행은 50 aa 에서 45 s 였으므로 1 h 는 충분한 여유이고, stall 하나가
# 6 h 가 아니라 1 h 만 먹게 한다. 실패한 run 은 `done` 으로 닫히지 않으므로
# 다음 pass 가 다시 집는다 - 상한을 줄이는 것이 시도 횟수를 줄이지 않는다.
export BIOEMU_HTTP_TIMEOUT_S="${BIOEMU_HTTP_TIMEOUT_S:-3600}"
export RFD3_HTTP_TIMEOUT_S="${RFD3_HTTP_TIMEOUT_S:-3600}"

PY=/opt/protein_pipeline/venv/bin/python
RUNNER=scripts/transcoder/52_v2_multisource_campaign.py
LOG=${V2_LOG_DIR:-/tmp/v2log}
mkdir -p "$LOG"

# 앞선 단계가 돌고 있으면 끝날 때까지 기다린다. 같은 상태 파일을 두 프로세스가
# 쓰면 마지막에 쓴 쪽이 이기고, 그 사이의 기록이 조용히 사라진다.
if [ -n "${WAIT_PID:-}" ]; then
  echo "[driver] 선행 프로세스 $WAIT_PID 대기"
  while kill -0 "$WAIT_PID" 2>/dev/null; do sleep 30; done
  echo "[driver] 선행 종료"
fi

for stage in backbones design fold; do
  echo "[driver] === $stage 시작 $(date -u +%FT%TZ)"
  $PY "$RUNNER" --stage "$stage" >> "$LOG/${stage}.log" 2>&1
  rc=$?
  echo "[driver] === $stage 종료 rc=$rc $(date -u +%FT%TZ)"
  if [ $rc -ne 0 ]; then
    echo "[driver] $stage 가 rc=$rc 로 끝났다. 다음 단계로 넘어가지 않는다 -"
    echo "[driver] 부분 입력 위에서 다음 단계를 돌리면 무엇이 빠졌는지가"
    echo "[driver] 산출물에서 보이지 않게 된다."
    exit $rc
  fi
done
echo "[driver] 전체 완료 $(date -u +%FT%TZ)"
