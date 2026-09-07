import json
import shutil
import tempfile
import unittest
from unittest import mock

import pipeline_mcp.literature as literature_mod
from pipeline_mcp.literature import (
    EUROPEPMC_BASE,
    _clamp_limit,
    _row,
    search_literature,
)
from pipeline_mcp.pipeline import PipelineRunner
from pipeline_mcp.tools import ToolDispatcher, tool_definitions


class TestRow(unittest.TestCase):
    def test_doi_wins_over_pmid(self) -> None:
        row = _row({"doi": "10.1/x", "pmid": "123", "id": "456",
                    "title": "T", "authorString": "A, B", "journalTitle": "J",
                    "pubYear": "2022", "citedByCount": 7, "isOpenAccess": "Y",
                    "source": "MED"})
        self.assertEqual(row["url"], "https://doi.org/10.1/x")
        self.assertEqual(row["identifier"], "10.1/x")
        self.assertTrue(row["open_access"])
        self.assertEqual(row["citations"], 7)

    def test_pmid_fallback_url(self) -> None:
        row = _row({"pmid": "123", "id": "456", "title": "T", "source": "MED"})
        self.assertEqual(row["identifier"], "123")
        self.assertEqual(row["url"], "https://europepmc.org/article/MED/123")

    def test_id_only_and_authors_truncated(self) -> None:
        row = _row({"id": "789", "source": "PPR", "title": "T",
                    "authorString": "x" * 200})
        self.assertEqual(row["url"], "https://europepmc.org/article/PPR/789")
        self.assertEqual(len(row["authors"]), 80)
        self.assertFalse(row["open_access"])
        self.assertEqual(row["citations"], 0)


class TestClamp(unittest.TestCase):
    def test_clamps_and_defaults(self) -> None:
        self.assertEqual(_clamp_limit(0), 1)
        self.assertEqual(_clamp_limit(99), 25)
        self.assertEqual(_clamp_limit(8), 8)
        self.assertEqual(_clamp_limit("bad"), 8)
        self.assertEqual(_clamp_limit(None), 8)


class TestSearch(unittest.TestCase):
    def test_empty_query_is_error(self) -> None:
        self.assertIn("error", search_literature("  "))

    def test_network_failure_is_error_contract(self) -> None:
        with mock.patch("pipeline_mcp.literature.urllib.request.urlopen",
                        side_effect=OSError("down")):
            out = search_literature("protein design")
        self.assertIn("error", out)

    def test_parses_result_list(self) -> None:
        payload = {"resultList": {"result": [
            {"id": "1", "doi": "10.1/a", "title": "Paper A",
             "authorString": "A", "journalTitle": "J", "pubYear": "2023",
             "citedByCount": 3, "isOpenAccess": "Y", "source": "MED"},
            {"not": "a row"},
        ]}}
        response = mock.MagicMock()
        response.read.return_value = json.dumps(payload).encode()
        response.__enter__.return_value = response
        with mock.patch("pipeline_mcp.literature.urllib.request.urlopen",
                        return_value=response) as urlopen:
            out = search_literature("protein", limit=5)
        self.assertEqual(len(out["items"]), 1)
        self.assertEqual(out["items"][0]["title"], "Paper A")
        self.assertEqual(out["query"], "protein")
        request = urlopen.call_args[0][0]
        self.assertTrue(request.full_url.startswith(f"{EUROPEPMC_BASE}/search?"))
        self.assertIn("format=json", request.full_url)
        self.assertIn("pageSize=5", request.full_url)
        self.assertIn("sort=CITED+desc", request.full_url)
        self.assertIn("resultType=lite", request.full_url)


class TestRegistration(unittest.TestCase):
    def test_tool_is_listed(self) -> None:
        names = [t["name"] for t in tool_definitions()]
        self.assertIn("pipeline.search_literature", names)

    def test_dispatch_rejects_blank_query(self) -> None:
        runner = PipelineRunner(output_root="/tmp/unused-lit", mmseqs=None,
                                proteinmpnn=None, soluprot=None, af2=None)
        out = ToolDispatcher(runner).call_tool("pipeline.search_literature", {"query": "  "})
        self.assertIn("error", out)

    def test_dispatch_delegates(self) -> None:
        tmp = tempfile.mkdtemp(prefix="lit_")
        try:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None,
                                    soluprot=None, af2=None)
            with mock.patch.object(literature_mod, "search_literature",
                                   return_value={"items": [{"title": "T"}], "query": "q"}) as fake:
                out = ToolDispatcher(runner).call_tool(
                    "pipeline.search_literature", {"query": "q", "limit": 3})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(out["items"], [{"title": "T"}])
        fake.assert_called_once_with("q", 3)


if __name__ == "__main__":
    unittest.main()
