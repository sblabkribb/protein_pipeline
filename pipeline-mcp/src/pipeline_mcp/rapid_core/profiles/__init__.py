"""PolicyProfile 정의. 여기는 Core 가 아니므로 도메인 어휘를 써도 된다."""

from .rapid_structural_v1 import RAPID_STRUCTURAL_V1, build_v1_core

__all__ = ["RAPID_STRUCTURAL_V1", "build_v1_core"]
