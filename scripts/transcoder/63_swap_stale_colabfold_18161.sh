#!/usr/bin/env bash
# :18161 의 22 일 된 고아 ColabFold 워커를 systemd 관리 워커로 교체한다.
#
# **폴딩이 도는 동안 부르지 말 것.** 진행 중인 폴드가 끊긴다. 안전한 창은
# 한 캠페인이 끝나고 다음 폴딩이 시작되기 전이다.
#
# 왜 필요한가
# -----------
# LB(:18160) 는 18161,18163,18164,18165 네 업스트림에 MAX_ACTIVE=4 로 분배한다.
# 18163-65 는 systemd 가 관리하고 COLABFOLD_TIMEOUT_S=3600 이다. 18161 은
# 유닛이 inactive/disabled 인데 PPID 1 고아가 포트를 쥐고 있고, 그 프로세스의
# 실제 환경은 **21600 (6 h)** 이다 - 유닛 파일의 3600 은 그 뒤에 추가돼
# 적용되지 않는다. ColabFold 가 MSA 업스트림을 잃으면 그 타임아웃까지 sleep
# 만 하므로 슬롯 하나가 6 시간 죽은 채 물린다 (2026-09-14 실측: 4-way 가
# 실제로 3-way 가 되어 66.7 -> 77.1 s/fold).
#
# 순서가 중요하다
# ---------------
# 고아를 **먼저** 죽여야 한다. 포트가 점유된 상태에서 유닛을 start 하면
# EADDRINUSE 로 죽고 Restart=always 때문에 크래시 루프가 된다.
#
# enable 은 하지 않는다
# ---------------------
# 공유 서버다. `systemctl --user enable` 은 다른 사용자의 가정을 바꾼다.
# start 만 한다 - 재부팅 후에는 원래대로 돌아간다.
set -u
HOST=${HOST:-211.188.35.221}
SSH="ssh -o BatchMode=yes -o ConnectTimeout=8 pipeline@$HOST"

busy () {
  $SSH 'p=$(ss -lptn "sport = :18161" 2>/dev/null | grep -oE "pid=[0-9]+" | head -1 | cut -d= -f2)
        [ -z "$p" ] && { echo none; exit 0; }
        n=$(pgrep -cP "$p" 2>/dev/null || echo 0)
        echo "$p $n"'
}

echo "=== 사전 점검 $(date -u +%FT%TZ)"
read -r PID NCHILD <<<"$(busy)"
echo "  :18161 pid=$PID 자식=$NCHILD"
if [ "$PID" = "none" ]; then echo "  포트가 비어 있다. 유닛만 start 한다."; PID=""; fi
if [ "${NCHILD:-0}" != "0" ]; then
  echo "  !! 작업 중이다. 폴드가 끊기므로 멈춘다."
  echo "     폴딩이 끝난 뒤 다시 부를 것."
  exit 1
fi
if [ "${CONFIRM:-0}" != "1" ]; then
  echo "  CONFIRM=1 을 주면 실제로 교체한다. (지금은 점검만 했다)"
  exit 0
fi

echo "=== 교체"
[ -n "$PID" ] && $SSH "kill $PID; sleep 3; kill -9 $PID 2>/dev/null; true"
$SSH 'ss -lptn "sport = :18161" | tail -1'
$SSH 'systemctl --user start protein-model-colabfold && sleep 5
      systemctl --user is-active protein-model-colabfold
      p=$(ss -lptn "sport = :18161" 2>/dev/null | grep -oE "pid=[0-9]+" | head -1 | cut -d= -f2)
      echo "새 pid=$p ppid=$(ps -o ppid= -p $p | tr -d " ")"
      tr "\0" "\n" < /proc/$p/environ | grep COLABFOLD_TIMEOUT_S'

echo "=== 원복이 필요하면"
echo "  ssh pipeline@$HOST 'systemctl --user stop protein-model-colabfold'"
echo "  (고아를 되살릴 수는 없다. 유닛 워커가 3600 s 로 계속 서빙한다.)"
