"""HTTP client for the fail-closed PPIformer affinity worker (bop:18113).

Ported verbatim from the antigen pipeline, where it has been exercised at
run scale. It is copied rather than rewritten on purpose: every guard below
exists because a specific failure happened once - a worker restarted onto
different checkpoints mid-run, a 1926-candidate request blew a fixed timeout,
an ensemble came back with fewer scores than checkpoints. Re-deriving those
guards from scratch would mean re-earning them.

RAPID has NOT benchmarked ddG as a gate. The registry marks this
`wired_unvalidated`: it can run, and that is a different claim from it working.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import math
import statistics
from typing import Any, Sequence

import requests


class AffinityClientError(RuntimeError):
    pass


class AffinityClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str | None = None,
        timeout_s: float = 600.0,
        max_batch_size: int = 200,
        replica_urls: Sequence[str] | None = None,
        max_concurrency: int | None = None,
    ) -> None:
        self.base_url = str(base_url or "").strip().rstrip("/")
        if not self.base_url:
            raise ValueError("affinity base_url is required")
        #: Every worker that can answer /score. ppiformer_affinity_worker.py
        #: serializes predictions behind a process-wide _PREDICT_LOCK (its
        #: per-request PyG cache fix installs a temp dir by mutating a module
        #: global, so two in-flight requests in one process would clobber each
        #: other), which makes ddG the run's longest serial stretch: ~25h for
        #: the ~10,900-candidate pool the 96-well preset generates. Threads
        #: cannot get around that, but separate processes each have their own
        #: globals - so parallelism comes from several worker processes and the
        #: batches below being spread across them.
        self.replica_urls = [
            str(url).strip().rstrip("/")
            for url in (replica_urls or [self.base_url])
            if str(url).strip()
        ] or [self.base_url]
        self.token = str(token or "").strip() or None
        self.timeout_s = float(timeout_s)
        if self.timeout_s <= 0:
            raise ValueError("affinity timeout must be positive")
        #: One POST carries every candidate, so its wall-clock scales with the
        #: candidate count while the read timeout stays fixed - a 1926-candidate
        #: request (200 backbones x 10 sequences) blew the 1800s timeout after
        #: 400 candidates had taken 22 minutes. Splitting into batches keeps any
        #: single request's duration bounded by this instead of by the run size.
        self.max_batch_size = int(max_batch_size)
        if self.max_batch_size <= 0:
            raise ValueError("affinity max_batch_size must be positive")
        #: How many batches may be in flight. Deliberately separate from the
        #: number of URLs: the deployed pool sits behind a single round-robin
        #: front (one externally reachable port, like every other worker), and a
        #: load balancer can only spread requests it actually receives at the
        #: same time - it cannot create concurrency. Measured: 160 candidates in
        #: 8 batches through that front took 2.93 s/candidate sequentially,
        #: indistinguishable from one worker, because only one batch was ever in
        #: flight.
        self.max_concurrency = int(
            max_concurrency if max_concurrency is not None else len(self.replica_urls)
        )
        if self.max_concurrency <= 0:
            raise ValueError("affinity max_concurrency must be positive")

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def health(self) -> dict[str, Any]:
        try:
            response = requests.get(
                f"{self.base_url}/healthz",
                headers=self._headers(),
                timeout=self.timeout_s,
            )
            try:
                payload = response.json()
            except Exception as exc:
                raise AffinityClientError(
                    f"affinity worker returned non-JSON HTTP {response.status_code}"
                ) from exc
            if response.status_code >= 400:
                detail = payload.get("error") if isinstance(payload, dict) else None
                raise AffinityClientError(
                    str(detail or f"affinity worker returned HTTP {response.status_code}")
                )
            response.raise_for_status()
        except AffinityClientError:
            raise
        except Exception as exc:
            raise AffinityClientError(f"affinity worker health check failed: {exc}") from exc

        if not isinstance(payload, dict):
            raise AffinityClientError("affinity health response must be an object")
        if payload.get("ok") is not True or payload.get("ready") is not True:
            raise AffinityClientError(str(payload.get("error") or "affinity model is not ready"))
        model = str(payload.get("model") or "").strip()
        version = str(payload.get("version") or "").strip()
        checkpoints = payload.get("checkpoint_hashes")
        if not model or not version:
            raise AffinityClientError("affinity health response lacks model provenance")
        if (
            not isinstance(checkpoints, list)
            or not checkpoints
            or any(not str(value).strip() for value in checkpoints)
        ):
            raise AffinityClientError("affinity health response lacks checkpoint hashes")
        return dict(payload)

    def score(
        self,
        *,
        structure: str,
        candidates: Sequence[dict[str, object]],
    ) -> dict[str, Any]:
        if not str(structure or "").strip():
            raise AffinityClientError("reference structure is required")
        normalized = [dict(candidate) for candidate in candidates]
        expected_ids = [str(candidate.get("id") or "").strip() for candidate in normalized]
        if not expected_ids or any(not value for value in expected_ids):
            raise AffinityClientError("every affinity candidate needs an id")
        if len(set(expected_ids)) != len(expected_ids):
            raise AffinityClientError("affinity candidate ids must be unique")

        if len(normalized) <= self.max_batch_size:
            return self._score_once(structure=structure, candidates=normalized)

        batches = [
            normalized[start : start + self.max_batch_size]
            for start in range(0, len(normalized), self.max_batch_size)
        ]
        # Up to max_concurrency batches in flight, round-robin over whatever
        # URLs there are. Results are reassembled in batch order below, so
        # which request finished first cannot change the output.
        if self.max_concurrency > 1:
            with ThreadPoolExecutor(max_workers=self.max_concurrency) as pool:
                payloads = list(
                    pool.map(
                        lambda item: self._score_once(
                            structure=structure,
                            candidates=item[1],
                            base_url=self.replica_urls[item[0] % len(self.replica_urls)],
                        ),
                        enumerate(batches),
                    )
                )
        else:
            payloads = [
                self._score_once(structure=structure, candidates=batch)
                for batch in batches
            ]

        merged: dict[str, Any] | None = None
        results: list[dict[str, Any]] = []
        for payload in payloads:
            if merged is None:
                merged = dict(payload)
            else:
                # Provenance must not drift mid-run: a worker restarted onto
                # different checkpoints between batches would otherwise
                # silently produce one result set scored by two models.
                for key in ("model", "version", "checkpoint_hashes"):
                    if payload.get(key) != merged.get(key):
                        raise AffinityClientError(
                            f"affinity provenance changed between batches ({key})"
                        )
            results.extend(payload.get("results") or [])
        if merged is None:  # pragma: no cover - guarded by the length check above
            raise AffinityClientError("affinity scoring produced no batches")
        merged["results"] = results
        return merged

    def _score_once(
        self,
        *,
        structure: str,
        candidates: Sequence[dict[str, object]],
        base_url: str | None = None,
    ) -> dict[str, Any]:
        normalized = [dict(candidate) for candidate in candidates]
        expected_ids = [str(candidate.get("id") or "").strip() for candidate in normalized]
        target = str(base_url or self.base_url).rstrip("/")

        try:
            response = requests.post(
                f"{target}/score",
                json={"structure": structure, "candidates": normalized},
                headers=self._headers(),
                timeout=self.timeout_s,
            )
            try:
                payload = response.json()
            except Exception as exc:
                raise AffinityClientError(
                    f"affinity worker returned non-JSON HTTP {response.status_code}"
                ) from exc
            if response.status_code >= 400:
                detail = payload.get("error") if isinstance(payload, dict) else None
                raise AffinityClientError(
                    str(detail or f"affinity worker returned HTTP {response.status_code}")
                )
            response.raise_for_status()
        except AffinityClientError:
            raise
        except Exception as exc:
            raise AffinityClientError(f"affinity worker request failed: {exc}") from exc

        return self._validate_response(payload, expected_ids)

    @staticmethod
    def _validate_response(payload: object, expected_ids: Sequence[str]) -> dict[str, Any]:
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            detail = payload.get("error") if isinstance(payload, dict) else None
            raise AffinityClientError(str(detail or "affinity worker did not return ok=true"))
        model = str(payload.get("model") or "").strip()
        version = str(payload.get("version") or "").strip()
        checkpoints = payload.get("checkpoint_hashes")
        results = payload.get("results")
        if not model or not version:
            raise AffinityClientError("affinity response lacks model provenance")
        if not isinstance(checkpoints, list) or not checkpoints:
            raise AffinityClientError("affinity response lacks checkpoint hashes")
        if not isinstance(results, list):
            raise AffinityClientError("affinity response lacks results")

        by_id: dict[str, dict[str, Any]] = {}
        for item in results:
            if not isinstance(item, dict):
                raise AffinityClientError("affinity result must be an object")
            candidate_id = str(item.get("id") or "").strip()
            if not candidate_id or candidate_id in by_id:
                raise AffinityClientError("affinity response has missing or duplicate candidate ids")
            model_scores = item.get("model_scores")
            if not isinstance(model_scores, list) or len(model_scores) != len(checkpoints):
                raise AffinityClientError(
                    f"affinity response has incomplete ensemble scores for {candidate_id}"
                )
            try:
                values = [float(value) for value in model_scores]
                mean_ddg = float(item.get("mean_ddg"))
                std_ddg = float(item.get("std_ddg"))
            except (TypeError, ValueError) as exc:
                raise AffinityClientError(
                    f"affinity response has invalid ensemble scores for {candidate_id}"
                ) from exc
            if not all(math.isfinite(value) for value in (*values, mean_ddg, std_ddg)):
                raise AffinityClientError(
                    f"affinity response has non-finite ensemble scores for {candidate_id}"
                )
            if abs(mean_ddg - statistics.fmean(values)) > 1e-6:
                raise AffinityClientError(
                    f"affinity response mean does not match ensemble scores for {candidate_id}"
                )
            if abs(std_ddg - statistics.pstdev(values)) > 1e-5:
                raise AffinityClientError(
                    f"affinity response std does not match ensemble scores for {candidate_id}"
                )
            normalized = dict(item)
            normalized["model_scores"] = values
            normalized["mean_ddg"] = mean_ddg
            normalized["std_ddg"] = std_ddg
            by_id[candidate_id] = normalized

        missing = [candidate_id for candidate_id in expected_ids if candidate_id not in by_id]
        extra = [candidate_id for candidate_id in by_id if candidate_id not in expected_ids]
        if missing:
            raise AffinityClientError(f"affinity response is missing candidate(s): {missing}")
        if extra:
            raise AffinityClientError(f"affinity response has unexpected candidate(s): {extra}")

        normalized_payload = dict(payload)
        normalized_payload["results"] = [by_id[candidate_id] for candidate_id in expected_ids]
        return normalized_payload
