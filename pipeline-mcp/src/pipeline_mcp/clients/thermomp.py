"""ThermoMPNN ddG HTTP 클라이언트 (bop:18114 워커).

ThermoMPNN (Kuhlman-Lab, MIT) 은 구조에서 단일 점변이의 ΔΔG (kcal/mol, 접힘
기준) 를 예측한다. 다중 변이 설계에 대해서는 각 변이의 단일-변이 예측을 더한
값을 기록하는데, 이는 가법 근사이고 에피스테이시스를 무시한다.

서명 규약: ΔΔG > 0 이면 불안정화 (ΔG_mutant − ΔG_wildtype). RAPID 는 이 값을
기록만 하고 안정성 게이트로 쓰지 않는다 - FireProtDB 학습 코호트 외부의
백본(특히 de-novo 설계)에 대해 맞춰본 적이 없기 때문이다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .local_http import LocalHttpRunClient


@dataclass(frozen=True)
class LocalHTTPThermoMPNNClient:
    base_url: str
    token: str | None = None
    timeout_s: float = 3600.0

    def _client(self) -> LocalHttpRunClient:
        return LocalHttpRunClient(self.base_url, self.token, self.timeout_s)

    def predict(
        self,
        *,
        pdb_text: str,
        target_id: str = "design",
        chain: str | None = None,
        mutations: list[str] | None = None,
        wt_sequence: str | None = None,
        top_n: int | None = None,
    ) -> dict[str, Any]:
        """설계 구조의 ΔΔG 예측.

        mutations 예: ["A123W", "T45G"] (chain + 1-based resseq + mutant AA).
        비우면 워커가 구조의 전체 단일-변이 스캔을 돌린다 (top_n 으로 상한).
        """
        if not str(pdb_text or "").strip():
            raise ValueError("ThermoMPNN requires pdb_text")
        payload: dict[str, Any] = {
            "target_id": str(target_id or "design"),
            "pdb_content": str(pdb_text),
        }
        if chain:
            payload["chain"] = str(chain)
        if mutations:
            payload["mutations"] = [str(m) for m in mutations]
        if wt_sequence:
            payload["wt_sequence"] = str(wt_sequence)
        if top_n:
            payload["top_n"] = int(top_n)
        return self._client().run(payload)

    def health(self) -> dict[str, Any]:
        import requests

        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        response = requests.get(
            self.base_url.rstrip("/") + "/healthz", headers=headers, timeout=30.0
        )
        response.raise_for_status()
        return response.json()
