#!/usr/bin/env bash
# 멈춘 colabfold_batch 를 회수한다.
#
# 왜 필요한가: ColabFold 는 MSA 를 외부 API 로 가져오는데, 그 응답이 끊기면
# 내부 폴링 루프에서 sleep 만 반복한다. 워커의 COLABFOLD_TIMEOUT_S 가 21600
# (6 h) 이라 그런 프로세스가 슬롯 하나를 6 시간 동안 물고 있는다. 실측으로
# 4 슬롯 중 1 개가 63 분째 CPU 0.5% 로 멈춰 있었고, 그래서 4-way 가 실제로는
# 3-way 로 돌고 있었다.
#
# 판정 기준은 두 개를 **함께** 본다. 시간만 보면 정상적으로 오래 걸리는 긴
# 서열을 죽이고, CPU 만 보면 GPU 대기 중인 정상 폴드를 죽인다.
#   - 살아 있은 시간 > AGE_S       (정상 폴드는 실측 200-250 s 에 끝난다)
#   - 평균 CPU < CPU_PCT           (계산 중이면 150-200% 가 나온다)
#
# 죽인 폴드는 우리 쪽에서 실패로 기록되고, 폴딩 단계가 재개 가능하므로 다음
# 패스에서 다시 접는다. 잃는 것은 그 한 건의 재작업뿐이고, 되찾는 것은
# 슬롯 하나다.
set -u

HOST="${RAPID_GPU_HOST:-211.188.35.221}"
KEY="${RAPID_GPU_KEY:-/root/.ssh/infra_dashboard_gpu_ed25519}"
AGE_S="${AGE_S:-900}"      # 정상 폴드의 4 배 여유
CPU_PCT="${CPU_PCT:-5}"
INTERVAL="${INTERVAL:-600}"
ONCE="${ONCE:-0}"

ssh_do() { timeout 60 ssh -o BatchMode=yes -o ConnectTimeout=10 -i "$KEY" "pipeline@$HOST" "$@"; }

reap() {
  ssh_do "ps -eo etimes,pid,pcpu,args | grep colabfold_batch | grep -v grep |
    awk -v a=$AGE_S -v c=$CPU_PCT '\$1>a && \$3<c {print \$2, \$1, \$3}'" 2>/dev/null |
  while read -r pid age cpu; do
    [ -z "$pid" ] && continue
    echo "$(date -u +%FT%TZ) 회수: pid=$pid age=${age}s cpu=${cpu}%"
    ssh_do "kill $pid 2>/dev/null; sleep 5; kill -0 $pid 2>/dev/null && kill -9 $pid" >/dev/null 2>&1
  done
}

if [ "$ONCE" = "1" ]; then reap; exit 0; fi

echo "$(date -u +%FT%TZ) reaper 시작 (age>${AGE_S}s & cpu<${CPU_PCT}%, 주기 ${INTERVAL}s)"
while true; do
  reap
  sleep "$INTERVAL"
done
