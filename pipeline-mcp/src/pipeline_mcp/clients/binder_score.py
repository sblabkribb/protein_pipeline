"""HTTP client for the ipSAE binder-score worker (bop:18108).

The worker computes interface confidence from a folded complex plus its PAE.
It is POST-fold: it scores what a validator already produced, so it never
competes with the cheap pre-fold stages for budget.

WHY ipSAE AND NOT ipTM
----------------------
For a two-chain complex, global ipTM is inflated by whatever native pairing the
structure already contains, so a high ipTM can mean "this chain folded" rather
than "these chains bind". ipSAE is scoped to the chain pair, which is the
question a binder design actually asks. `PRIMARY_METRIC` pins that choice in
code so a caller cannot quietly read ipTM instead.

UNSCORED IS NOT FAILED, AND NEITHER IS REJECTED
-----------------------------------------------
Three outcomes are kept apart, because collapsing them loses the distinction
between "we know it is bad" and "we do not know":

  passed is True   - scored, above the cutoff
  passed is False  - scored, below the cutoff        (information)
  passed is None   - not scorable (no PAE, one chain) (no information)

RAPID has not benchmarked this scorer. The registry marks it
`wired_unvalidated`.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence
import json
import urllib.error
import urllib.request


class BinderScoreError(RuntimeError):
    pass


def _http_post(url: str, payload: dict, timeout: float) -> dict:
    request = urllib.request.Request(  # noqa: S310 - fixed internal endpoint
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            return json.loads(body or "{}")
        except json.JSONDecodeError:
            raise BinderScoreError(
                f"binder-score worker returned non-JSON HTTP {exc.code}: {body[:200]}"
            ) from exc


class BinderScoreClient:
    #: 인터페이스 신뢰도의 1차 지표. 복합체의 global ipTM 을 대신 쓰지 않는다.
    PRIMARY_METRIC = "ipsae"

    def __init__(
        self,
        *,
        base_url: str,
        timeout_s: float = 900.0,
        max_batch_size: int = 64,
        transport: Callable[[str, dict, float], dict] | None = None,
    ) -> None:
        self.base_url = str(base_url or "").strip().rstrip("/")
        if not self.base_url:
            raise ValueError("binder_score base_url is required")
        self.timeout_s = float(timeout_s)
        if self.timeout_s <= 0:
            raise ValueError("binder_score timeout must be positive")
        self.max_batch_size = int(max_batch_size)
        if self.max_batch_size <= 0:
            raise ValueError("binder_score max_batch_size must be positive")
        self._transport = transport or _http_post

    def score(
        self,
        *,
        candidates: Sequence[dict[str, Any]],
        epitope: str | None = None,
        **shared: Any,
    ) -> dict[str, Any]:
        normalized = [dict(item) for item in candidates]
        if not normalized:
            raise BinderScoreError("binder_score needs at least one candidate")
        ids: list[str] = []
        for index, item in enumerate(normalized):
            candidate_id = str(item.get("id") or "").strip()
            if not candidate_id:
                raise BinderScoreError(f"candidate {index} has no id")
            # 구조 없이 인터페이스를 채점할 수 없다. 워커까지 보내고 실패하는
            # 대신 여기서 막는다 - 배치 하나가 통째로 죽는 것을 막는다.
            if not str(item.get("structure") or item.get("structure_path") or "").strip():
                raise BinderScoreError(f"candidate {candidate_id} has no structure")
            ids.append(candidate_id)
        if len(set(ids)) != len(ids):
            raise BinderScoreError("binder_score candidate ids must be unique")

        batches = [
            normalized[start : start + self.max_batch_size]
            for start in range(0, len(normalized), self.max_batch_size)
        ]
        collected: dict[str, dict[str, Any]] = {}
        for batch in batches:
            payload: dict[str, Any] = {"task": "score", "candidates": batch}
            if epitope:
                payload["epitope"] = epitope
            payload.update(shared)
            output = self._request({"input": payload})
            for item in output.get("results") or ():
                if not isinstance(item, dict):
                    raise BinderScoreError("binder_score result must be an object")
                candidate_id = str(item.get("id") or "").strip()
                if not candidate_id:
                    raise BinderScoreError("binder_score result has no id")
                if candidate_id in collected:
                    raise BinderScoreError(f"binder_score returned {candidate_id} twice")
                collected[candidate_id] = item

        missing = [candidate_id for candidate_id in ids if candidate_id not in collected]
        if missing:
            raise BinderScoreError(f"binder_score response is missing candidate(s): {missing}")
        extra = [candidate_id for candidate_id in collected if candidate_id not in ids]
        if extra:
            raise BinderScoreError(f"binder_score response has unexpected candidate(s): {extra}")

        results = [collected[candidate_id] for candidate_id in ids]
        return {
            "results": results,
            "count": len(results),
            "primary_metric": self.PRIMARY_METRIC,
            "passed_ids": [r["id"] for r in results if r.get("passed") is True],
            "rejected_ids": [r["id"] for r in results if r.get("passed") is False],
            "unscored_ids": [r["id"] for r in results if r.get("passed") is None],
        }

    def _request(self, body: dict) -> dict[str, Any]:
        try:
            payload = self._transport(f"{self.base_url}/run", body, self.timeout_s)
        except BinderScoreError:
            raise
        except Exception as exc:  # noqa: BLE001 - 어떤 전송 실패든 클라이언트 오류다
            raise BinderScoreError(f"binder-score worker request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise BinderScoreError("binder-score response must be an object")
        status = str(payload.get("status") or "").upper()
        if payload.get("ok") is False or status in {"FAILED", "CANCELLED"}:
            raise BinderScoreError(
                str(payload.get("error") or f"binder-score worker returned {status or 'an error'}")
            )
        output = payload.get("output")
        if not isinstance(output, dict):
            raise BinderScoreError("binder-score response has no output object")
        return output

    def health(self) -> dict[str, Any]:
        with urllib.request.urlopen(f"{self.base_url}/healthz", timeout=30) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8") or "{}")
        if payload.get("ok") is not True or payload.get("ready") is not True:
            raise BinderScoreError(str(payload.get("error") or "binder-score worker is not ready"))
        return payload
