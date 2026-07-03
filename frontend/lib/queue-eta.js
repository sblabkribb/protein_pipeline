// Pure render/format helpers for the worker-queue ETA card.
// All times are approximate; missing data degrades to counts-only text.

export function etaMinutes(seconds) {
  if (seconds == null || Number.isNaN(Number(seconds)) || seconds <= 0) return null;
  return Math.max(1, Math.ceil(Number(seconds) / 60));
}

export function finishClock(finishS, nowMs = Date.now()) {
  if (finishS == null || Number.isNaN(Number(finishS))) return null;
  const d = new Date(nowMs + Number(finishS) * 1000);
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${hh}:${mm}`;
}

export function renderQueueEta(payload, lang = "ko") {
  if (!payload || typeof payload !== "object") return "";
  const ko = String(lang || "").startsWith("ko");
  const perStage = Array.isArray(payload.per_stage) ? payload.per_stage : [];
  const queued = perStage.reduce((a, s) => a + (Number(s.queued) || 0), 0);
  const running = perStage.reduce((a, s) => a + (Number(s.running) || 0), 0);

  if (payload.fallback || payload.est_finish_s == null) {
    return ko
      ? `대기 ${queued} · 실행 ${running} (예상 시간 산출 불가)`
      : `queued ${queued} · running ${running} (estimate unavailable)`;
  }

  const mins = etaMinutes(payload.est_finish_s);
  const clock = finishClock(payload.est_finish_s);
  const stage = payload.current_stage || (perStage[0] && perStage[0].stage) || "-";
  return ko
    ? `현재 단계 ${stage} · 내 앞 대기 ${queued} · 예상 완료 ~${mins}분 후(~${clock}, 근사)`
    : `stage ${stage} · ${queued} ahead · ~${mins} min (~${clock}, approx)`;
}
