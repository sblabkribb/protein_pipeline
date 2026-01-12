from __future__ import annotations

from dataclasses import dataclass
import os
import time
from typing import Any
from collections.abc import Callable

import requests


def _env_true(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def requests_verify_arg(*, ca_bundle: str | None, skip_verify: bool) -> bool | str:
    if skip_verify or _env_true("RUNPOD_INSECURE"):
        return False
    if ca_bundle:
        return ca_bundle
    return True


@dataclass(frozen=True)
class RunPodClient:
    api_key: str
    ca_bundle: str | None = None
    skip_verify: bool = False
    timeout_s: float = 60.0
    poll_interval_s: float = 2.0

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def run(self, endpoint_id: str, input_payload: dict[str, Any]) -> str:
        url = f"https://api.runpod.ai/v2/{endpoint_id}/run"
        r = requests.post(
            url,
            headers=self._headers(),
            json={"input": input_payload},
            timeout=self.timeout_s,
            verify=requests_verify_arg(ca_bundle=self.ca_bundle, skip_verify=self.skip_verify),
        )
        r.raise_for_status()
        data = r.json()
        job_id = data.get("id")
        if not job_id:
            raise RuntimeError(f"RunPod response missing job id: {data}")
        return str(job_id)

    def status(self, endpoint_id: str, job_id: str) -> dict[str, Any]:
        url = f"https://api.runpod.ai/v2/{endpoint_id}/status/{job_id}"
        r = requests.get(
            url,
            headers=self._headers(),
            timeout=self.timeout_s,
            verify=requests_verify_arg(ca_bundle=self.ca_bundle, skip_verify=self.skip_verify),
        )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected RunPod status response: {data!r}")
        return data

    def wait(self, endpoint_id: str, job_id: str) -> dict[str, Any]:
        start = time.monotonic()
        while True:
            data = self.status(endpoint_id, job_id)
            status = data.get("status") or data.get("state")
            if status in {"COMPLETED", "COMPLETED_WITH_ERRORS", "FAILED", "CANCELLED", "TIMED_OUT"}:
                return data
            elapsed = time.monotonic() - start
            if elapsed > 60 * 60 * 6:
                raise TimeoutError(f"RunPod job timeout (>6h): endpoint={endpoint_id} job_id={job_id}")
            time.sleep(self.poll_interval_s)

    def run_and_wait(self, endpoint_id: str, input_payload: dict[str, Any]) -> dict[str, Any]:
        return self.run_and_wait_with_job_id(endpoint_id, input_payload)[1]

    def run_and_wait_with_job_id(
        self,
        endpoint_id: str,
        input_payload: dict[str, Any],
        *,
        on_job_id: Callable[[str], None] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        job_id = self.run(endpoint_id, input_payload)
        if on_job_id is not None:
            on_job_id(job_id)
        data = self.wait(endpoint_id, job_id)
        return job_id, data
