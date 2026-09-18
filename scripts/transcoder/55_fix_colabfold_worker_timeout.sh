#!/usr/bin/env bash
# BOP ColabFold 워커의 COLABFOLD_TIMEOUT_S 를 6 h -> 1 h 로 내린다.
#
# **v2 캠페인이 끝난 뒤에 실행한다.** 워커를 재시작하므로 진행 중인 폴드가
# 끊긴다 (앞서 LB 재시작 때 203 건이 그렇게 실패했다).
#
# 왜 필요한가
# -----------
# ColabFold 는 MSA 를 외부 API 로 가져오는데, 응답이 끊기면 내부 폴링 루프에서
# sleep 만 반복한다. 워커는 COLABFOLD_TIMEOUT_S 가 지나야 그 서브프로세스를
# 죽이므로, 기본값 21600 (6 h) 에서는 슬롯 하나가 6 시간 동안 죽은 채 물린다.
# 2026-09-14 실측: 4 슬롯 중 1 개가 63 분째 CPU 0.5%, 열린 연결 0 개였고
# 그래서 4-way 가 실제로는 3-way 로 돌고 있었다. 회수 후 처리율이
# 77.1 -> 66.7 s/fold 로 13% 개선됐다.
#
# 이것은 우리 캠페인만의 문제가 아니다. UI 로 RAPID 를 쓰는 모든 사용자에게
# 같은 일이 일어나며, 아무도 모르는 채로 슬롯이 사라진다.
#
# 왜 3600 인가
# ------------
# 정상 폴드는 실측 200-250 s 에 끝난다. 이 코호트 최장 서열이 386 aa 이므로
# 1 h 는 약 14 배 여유다. 값을 더 줄이면 긴 서열의 정상 폴드를 죽일 위험이
# 생기고, 더 늘리면 애초의 문제가 남는다.
#
# systemd 밖에서 도는 워커는 건드리지 않는다
# ------------------------------------------
# 2026-09-17 확인: `protein-model-colabfold` 유닛은 `inactive`/`disabled` 인데
# 포트 18161 은 PPID 1 의 맨 프로세스가 18 일째 서빙하고 있다. 이 유닛에
# `systemctl --user restart` 를 걸면 systemd 가 새 프로세스를 띄우고, 그것이
# 이미 점유된 0.0.0.0:18161 에 bind 하려다 EADDRINUSE 로 죽는다. `Restart=always`
# 이므로 **크래시 루프**가 된다. 기존 프로세스는 계속 서빙하므로 LB 는 정상으로
# 보이고 고장은 저널에만 남는다.
#
# 그래서 유닛이 active 가 아니면 재시작하지 않고 경고만 낸다. 그 워커의
# 타임아웃을 실제로 바꾸려면 맨 프로세스를 먼저 정리해야 하고, 그것은 이
# 스크립트의 일이 아니다 (공유 서버의 운영 결정이다).
#
# 이 스크립트가 하지 않는 것: 업스트림 수·max_active·LB 설정은 건드리지 않는다.
set -euo pipefail

HOST="${RAPID_GPU_HOST:-211.188.35.221}"
KEY="${RAPID_GPU_KEY:-/root/.ssh/infra_dashboard_gpu_ed25519}"
NEW="${NEW_TIMEOUT_S:-3600}"
UNITS="protein-model-colabfold protein-model-colabfold-gpu0b protein-model-colabfold-gpu1 protein-model-colabfold-gpu1b"

ssh_do() { timeout 120 ssh -o BatchMode=yes -o ConnectTimeout=10 -i "$KEY" "pipeline@$HOST" "$@"; }

echo "=== 적용 전 상태"
ssh_do "for u in $UNITS; do printf '  %-38s %-26s active=%s\n' \"\$u\" \"\$(grep -o 'COLABFOLD_TIMEOUT_S=[0-9]*' ~/.config/systemd/user/\$u.service)\" \"\$(systemctl --user is-active \$u 2>&1)\"; done"

echo "=== systemd 밖에서 도는 워커 (재시작하지 않는다)"
ssh_do "for u in $UNITS; do
  if [ \"\$(systemctl --user is-active \$u 2>/dev/null)\" != active ]; then
    p=\$(grep -oP 'port \\K[0-9]+' ~/.config/systemd/user/\$u.service | head -1)
    owner=\$(ss -ltnp 2>/dev/null | grep \":\$p \" | grep -oP 'pid=\\K[0-9]+' | head -1)
    printf '  !! %-36s 유닛 비활성 · 포트 %s 는 PID %s 가 서빙 → 건너뛴다\n' \"\$u\" \"\${p:-?}\" \"\${owner:-없음}\"
  fi
done; true"

echo "=== 진행 중인 폴드 (재시작하면 끊긴다)"
ssh_do "ps -eo etimes,pcpu,args | grep colabfold_batch | grep -v grep | wc -l | sed 's/^/  /'"

if [ "${CONFIRM:-0}" != "1" ]; then
  echo
  echo "실제로 적용하려면 CONFIRM=1 로 다시 실행한다."
  echo "  CONFIRM=1 bash $0"
  exit 0
fi

echo "=== 백업 후 적용"
ssh_do "mkdir -p ~/rapid_timeout_change
for u in $UNITS; do
  f=~/.config/systemd/user/\$u.service
  cp \$f ~/rapid_timeout_change/\$u.service.bak
  sed -i 's|^Environment=COLABFOLD_TIMEOUT_S=.*|Environment=COLABFOLD_TIMEOUT_S=$NEW|' \$f
done
cat > ~/rapid_timeout_change/revert.sh <<'EOF'
#!/usr/bin/env bash
set -e
for f in ~/rapid_timeout_change/*.service.bak; do
  u=\$(basename \$f .service.bak)
  cp \$f ~/.config/systemd/user/\$u.service
done
systemctl --user daemon-reload
for u in $UNITS; do
  if [ x\$(systemctl --user is-active \$u 2>/dev/null) = xactive ]; then
    systemctl --user restart \$u.service
  fi
done
echo '원복 완료 (COLABFOLD_TIMEOUT_S=21600)'
EOF
chmod +x ~/rapid_timeout_change/revert.sh
systemctl --user daemon-reload
# active 인 유닛만 재시작한다. 비활성 유닛은 포트가 이미 맨 프로세스에 잡혀
# 있어서 재시작하면 EADDRINUSE 크래시 루프가 된다.
for u in $UNITS; do
  if [ x\$(systemctl --user is-active \$u 2>/dev/null) = xactive ]; then
    systemctl --user restart \$u.service
  else
    echo '  건너뜀 (유닛 비활성): '\$u
  fi
done"

sleep 8
echo "=== 적용 후"
ssh_do "for u in $UNITS; do printf '  %-38s %s  %s\n' \"\$u\" \"\$(grep -o 'COLABFOLD_TIMEOUT_S=[0-9]*' ~/.config/systemd/user/\$u.service)\" \"\$(systemctl --user is-active \$u.service)\"; done"
echo "=== LB 도달 확인"
curl -sS --max-time 10 "http://$HOST:18160/status" | python3 -c "import sys,json;d=json.load(sys.stdin);print('  ready', sum(u['ready'] for u in d['upstreams']), '/', len(d['upstreams']))"
echo
echo "원복: ssh pipeline@$HOST 'bash ~/rapid_timeout_change/revert.sh'"
echo "이후 임시 reaper(54_)는 내려도 된다."
