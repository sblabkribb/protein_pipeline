import os
import tempfile
import unittest
from pathlib import Path

from pipeline_mcp import soluprot_server as srv


class TestSequenceCleaning(unittest.TestCase):
    def test_uppercases_and_drops_non_letters(self) -> None:
        self.assertEqual(srv.clean_sequence("acd efg\nhik*"), "ACDEFGHIK")

    def test_empty_input_is_empty(self) -> None:
        self.assertEqual(srv.clean_sequence(""), "")
        self.assertEqual(srv.clean_sequence(None), "")  # type: ignore[arg-type]


class TestCacheKey(unittest.TestCase):
    def test_key_depends_on_sequence(self) -> None:
        self.assertNotEqual(srv.cache_key("ACDEF" * 5), srv.cache_key("ACDEG" * 5))

    def test_key_is_stable(self) -> None:
        self.assertEqual(srv.cache_key("ACDEF" * 5), srv.cache_key("ACDEF" * 5))


class TestShortSequencePolicy(unittest.TestCase):
    def test_short_sequences_are_not_sent_to_the_model(self) -> None:
        """20 잔기 미만이 섞이면 SoluProt 이 배치 전체를 거부하므로 미리 걸러낸다."""
        calls: list[list[str]] = []

        def fake_chunk(sequences: list[str]) -> dict[str, float]:
            calls.append(sequences)
            return {s: 0.5 for s in sequences}

        original = srv._run_chunk
        original_cache = srv.CACHE
        srv._run_chunk = fake_chunk  # type: ignore[assignment]
        tmp = tempfile.TemporaryDirectory(prefix="soluprot-test-")
        # 가짜 점수가 운영 캐시에 남지 않도록 임시 캐시를 쓴다.
        srv.CACHE = srv.ScoreCache(Path(tmp.name) / "cache.sqlite3")
        try:
            long_seq = "MKVLAAGIVLGSTQWRDPLLNKACFGHIYE"
            scores = srv.score_sequences([long_seq, "MKV", ""])
        finally:
            srv._run_chunk = original  # type: ignore[assignment]
            srv.CACHE = original_cache
            tmp.cleanup()

        self.assertNotIn("MKV", scores)
        self.assertEqual([s for call in calls for s in call], [long_seq])


class TestInstallationCheck(unittest.TestCase):
    def test_missing_installation_is_reported(self) -> None:
        original = srv.SOLUPROT_DIR
        srv.SOLUPROT_DIR = original.parent / "does-not-exist"
        try:
            problems = srv.installation_problems()
        finally:
            srv.SOLUPROT_DIR = original
        self.assertTrue(any("soluprot.py" in p for p in problems))


@unittest.skipUnless(
    os.environ.get("SOLUPROT_INTEGRATION") == "1",
    "SoluProt 설치가 있는 호스트에서만 돈다",
)
class TestRealModel(unittest.TestCase):
    def test_known_sequence_matches_published_score(self) -> None:
        seq = "MKVLAAGIVLGSTQWRDPLLNKACFGHIYE"
        scores = srv.score_sequences([seq])
        self.assertAlmostEqual(scores[seq], 0.1752, places=4)


if __name__ == "__main__":
    unittest.main()
