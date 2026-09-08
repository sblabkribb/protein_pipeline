"""ESMFold 워커 클라이언트 (bop:18162, facebook/esmfold_v1).

왜 붙이는가
-----------
지금까지 실패한 것은 대부분 저비용 **서열 점수**로 AF2 성공을 맞히려는
시도였다. 타겟 안에서 SoluProt 은 AUROC 중앙값 0.540, 응집 휴리스틱의 증분은
+0.014 [-0.110, +0.134], MPNN global_score 는 structural_pass 에 rho 0.041 이다.
ESMFold 는 서열 점수가 아니라 실제 3D 구조 예측이므로 다른 정보원이다.

그러면 비용 계층이 두 단에서 세 단이 된다.

    cheap      SoluProt, Gate 0, 서열 통계
    medium     ESMFold          <- 여기가 비어 있었다
    expensive  AF2/ColabFold

RAPID 의 문제가 "어느 서열에 AF2 를 쓸 것인가" 에서 "어느 후보를 어느 fidelity
평가자에 보낼 것인가" 로 넓어진다.

지금 상태
---------
**배선만 한다. 파이프라인이 아직 부르지 않는다.** 레지스트리에서
`wired_unvalidated` 이고, 게이트도 순위도 아니다. 검증은 응집에 쓴 것과 같은
증분 정보 검정으로 따로 한다 - ESMFold pLDDT 가 **타겟 안에서** AF2 구조 성공을
가르는지. 그 전에 순위에 넣으면 맞춰본 적 없는 기준으로 후보를 정렬하게 된다.

진행 중인 홀드아웃 코호트에는 쓰지 않는다. 분산 분해와 정책 검증 계획이
동결되어 있고, 거기에 새 특징을 넣으면 그 계획을 벗어난다.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..models import SequenceRecord
from .local_http import LocalHttpRunClient, _strip_inline_archive_payloads


@dataclass
class LocalHTTPESMFoldClient:
    """워커는 ColabFold 와 같은 비동기 `POST /run` 규약을 쓴다.

    MSA 가 없으므로 `db_preset` 이나 `max_template_date` 같은 인자가 없다. 그게
    ESMFold 가 싼 이유이자, AF2 와 같은 것을 재지 않는 이유다.
    """

    base_url: str
    token: str | None = None
    #: AF2 기본값(6 시간)보다 짧게 둔다. MSA 가 없어 폴드가 훨씬 빠르고, 길게
    #: 잡으면 워커가 매달릴 때 클라이언트가 오래 붙잡힌다.
    timeout_s: float = 3600.0
    endpoint_id: str | None = None

    def predict(
        self,
        sequences: list[SequenceRecord],
        *,
        num_recycles: int | None = None,
        chunk_size: int | None = None,
        extra_flags: str | None = None,
        on_job_id: Callable[[str, str], None] | None = None,
    ) -> dict[str, Any]:
        """서열마다 `{"pdb": ..., "best_plddt": ...}` 를 돌려준다.

        pLDDT 는 워커가 PDB 의 B-factor 열에서 평균해 계산한다 (`_mean_plddt_from_pdb`).
        **AF2 pLDDT 와 같은 척도로 섞어 쓰면 안 된다** - 다른 모형의 신뢰도다.
        """
        if not sequences:
            return {}
        payload: dict[str, Any] = {
            "sequences": [{"id": seq.id, "sequence": seq.sequence} for seq in sequences],
        }
        if num_recycles is not None:
            payload["num_recycles"] = int(num_recycles)
        if chunk_size is not None:
            payload["chunk_size"] = int(chunk_size)
        if extra_flags:
            payload["extra_flags"] = str(extra_flags)

        output = LocalHttpRunClient(self.base_url, self.token, self.timeout_s).run(payload)
        job_id = str(output.get("job_id") or "").strip()
        if job_id and on_job_id:
            for seq in sequences:
                on_job_id(seq.id, job_id)

        # 워커는 records 리스트로 돌려준다. id 로 색인해 AF2 클라이언트와 같은
        # 모양으로 맞춘다 - 호출자가 두 평가자를 같은 방식으로 다룰 수 있게.
        records = output.get("records")
        if isinstance(records, list):
            indexed: dict[str, Any] = {}
            for item in records:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("id") or item.get("name") or "").strip()
                if key:
                    indexed[key] = item
            if indexed:
                stripped = _strip_inline_archive_payloads(indexed)
                return stripped if isinstance(stripped, dict) else indexed

        results = output.get("results") if isinstance(output.get("results"), dict) else output
        if len(sequences) == 1 and ("pdb" in output or "best_plddt" in output):
            stripped = _strip_inline_archive_payloads(output)
            return {sequences[0].id: stripped if isinstance(stripped, dict) else output}
        stripped = _strip_inline_archive_payloads(results)
        return stripped if isinstance(stripped, dict) else results
