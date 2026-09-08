import json
import shutil
import tempfile
import unittest
from unittest import mock

import pipeline_mcp.literature as literature_mod
import pipeline_mcp.reference as reference_mod
from pipeline_mcp.reference import (
    INTERPRO_BASE,
    PDB_SEARCH_URL,
    UNIPROT_BASE,
    _clamp_limit,
    search_interpro,
    search_pdb,
    search_reference,
    search_uniprot,
    search_uniref,
)
from pipeline_mcp.pipeline import PipelineRunner
from pipeline_mcp.tools import ToolDispatcher, tool_definitions


ROW_KEYS = {"title", "detail", "identifier", "url", "source"}

PDB_PAYLOAD = {
    "result_set": [
        {
            "identifier": "4HHB",
            "score": 1.0,
            "services": [
                {
                    "nodes": [
                        {"match_context": [{"matched_string": "hemoglobin"}],
                         "rcsb_id": "4HHB"}
                    ],
                    "identifier": "full_text",
                }
            ],
        },
        {"identifier": "1BBB", "score": 0.8, "services": []},
        {"no_identifier": "x"},
        "junk",
    ],
    "total_count": 2,
}

UNIPROT_PAYLOAD = {
    "results": [
        {
            "primaryAccession": "P69905",
            "proteinDescription": {
                "recommendedName": {"fullName": {"value": "Hemoglobin subunit alpha"}},
            },
            "organism": {"scientificName": "Homo sapiens"},
            "sequence": {"length": 142},
        },
        {
            "primaryAccession": "P68871",
            "proteinDescription": {},
            "organism": {},
            "sequence": {},
        },
        {"no_accession": True},
        "junk",
    ]
}

INTERPRO_PAYLOAD = {
    "results": [
        {
            "metadata": {
                "accession": "IPR023411",
                "name": {"name": "ABC transporter"},
                "type": "family",
                "source_database": "interpro",
            },
        },
        {
            "metadata": {"accession": "IPR000001", "name": "Legacy", "type": "unknown"},
        },
        {"metadata": {"no_accession": True}},
        "junk",
    ]
}

UNIREF_PAYLOAD = {
    "results": [
        {"id": "UniRef100_P69905", "memberCount": 51},
        {"id": "UniRef100_A0A001", "proteinCount": 7},
        {"id": "UniRef100_B0B001", "proteinCount": "bad", "memberCount": "worse"},
        {"no_id": True},
        "junk",
    ]
}

FIXTURES = {
    search_pdb: PDB_PAYLOAD,
    search_uniprot: UNIPROT_PAYLOAD,
    search_interpro: INTERPRO_PAYLOAD,
    search_uniref: UNIREF_PAYLOAD,
}


def urlopen_returning(payload):
    response = mock.MagicMock()
    response.read.return_value = json.dumps(payload).encode()
    response.__enter__.return_value = response
    return response


class TestClamp(unittest.TestCase):
    def test_clamps_and_defaults(self) -> None:
        self.assertEqual(_clamp_limit(0), 1)
        self.assertEqual(_clamp_limit(99), 25)
        self.assertEqual(_clamp_limit(8), 8)
        self.assertEqual(_clamp_limit("bad"), 8)
        self.assertEqual(_clamp_limit(None), 8)


class TestPdb(unittest.TestCase):
    def test_rows_and_request(self) -> None:
        with mock.patch("pipeline_mcp.reference.urllib.request.urlopen",
                        return_value=urlopen_returning(PDB_PAYLOAD)) as urlopen:
            out = search_pdb("hemoglobin", limit=5)
        self.assertNotIn("error", out)
        self.assertEqual(out["query"], "hemoglobin")
        self.assertEqual(len(out["items"]), 2)
        first = out["items"][0]
        self.assertEqual(first["title"], "hemoglobin")
        self.assertEqual(first["detail"], "실험 구조 (PDB)")
        self.assertEqual(first["identifier"], "4HHB")
        self.assertEqual(first["url"], "https://www.rcsb.org/structure/4HHB")
        self.assertEqual(first["source"], "structural")
        # services 가 비어 있으면 identifier 기반 폴백 제목을 쓴다.
        self.assertEqual(out["items"][1]["title"], "PDB 1BBB")
        request = urlopen.call_args[0][0]
        self.assertEqual(request.full_url, PDB_SEARCH_URL)
        self.assertEqual(request.get_method(), "POST")
        self.assertIn("json", (request.get_header("Content-type") or ""))
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["query"]["service"], "full_text")
        self.assertEqual(body["query"]["parameters"]["value"], "hemoglobin")
        self.assertEqual(body["request_options"]["paginate"]["rows"], 5)
        self.assertEqual(body["request_options"]["results_content_type"], ["experimental"])
        self.assertEqual(body["return_type"], "entry")

    def test_limit_clamped_into_body(self) -> None:
        with mock.patch("pipeline_mcp.reference.urllib.request.urlopen",
                        return_value=urlopen_returning(PDB_PAYLOAD)) as urlopen:
            search_pdb("hemoglobin", limit=99)
        body = json.loads(urlopen.call_args[0][0].data.decode("utf-8"))
        self.assertEqual(body["request_options"]["paginate"]["rows"], 25)


class TestUniprot(unittest.TestCase):
    def test_rows_and_request(self) -> None:
        with mock.patch("pipeline_mcp.reference.urllib.request.urlopen",
                        return_value=urlopen_returning(UNIPROT_PAYLOAD)) as urlopen:
            out = search_uniprot("hemoglobin", limit=5)
        self.assertNotIn("error", out)
        self.assertEqual(len(out["items"]), 2)
        first = out["items"][0]
        self.assertEqual(first["title"], "Hemoglobin subunit alpha")
        self.assertEqual(first["detail"], "Homo sapiens · 142 aa")
        self.assertEqual(first["identifier"], "P69905")
        self.assertEqual(first["url"], "https://www.uniprot.org/uniprotkb/P69905")
        self.assertEqual(first["source"], "curated")
        # recommended name 이 없으면 accession 으로 폴백한다.
        self.assertEqual(out["items"][1]["title"], "P68871")
        request = urlopen.call_args[0][0]
        self.assertTrue(request.full_url.startswith(f"{UNIPROT_BASE}/uniprotkb/search?"))
        self.assertIn("format=json", request.full_url)
        self.assertIn("size=5", request.full_url)
        self.assertIn("query=hemoglobin", request.full_url)

    def test_limit_clamped(self) -> None:
        with mock.patch("pipeline_mcp.reference.urllib.request.urlopen",
                        return_value=urlopen_returning(UNIPROT_PAYLOAD)) as urlopen:
            search_uniprot("q", limit=99)
        self.assertIn("size=25", urlopen.call_args[0][0].full_url)


class TestInterpro(unittest.TestCase):
    def test_rows_and_request(self) -> None:
        with mock.patch("pipeline_mcp.reference.urllib.request.urlopen",
                        return_value=urlopen_returning(INTERPRO_PAYLOAD)) as urlopen:
            out = search_interpro("transporter", limit=5)
        self.assertNotIn("error", out)
        self.assertEqual(len(out["items"]), 2)
        first = out["items"][0]
        self.assertEqual(first["title"], "ABC transporter")
        self.assertEqual(first["detail"], "family · interpro")
        self.assertEqual(first["identifier"], "IPR023411")
        self.assertEqual(first["url"], "https://www.ebi.ac.uk/interpro/entry/InterPro/IPR023411/")
        self.assertEqual(first["source"], "curated")
        request = urlopen.call_args[0][0]
        self.assertTrue(request.full_url.startswith(f"{INTERPRO_BASE}/entry/interpro/?"))
        self.assertIn("page_size=5", request.full_url)
        self.assertIn("search=transporter", request.full_url)

    def test_limit_clamped(self) -> None:
        with mock.patch("pipeline_mcp.reference.urllib.request.urlopen",
                        return_value=urlopen_returning(INTERPRO_PAYLOAD)) as urlopen:
            search_interpro("q")
        self.assertIn("page_size=8", urlopen.call_args[0][0].full_url)


class TestUniref(unittest.TestCase):
    def test_rows_and_request(self) -> None:
        with mock.patch("pipeline_mcp.reference.urllib.request.urlopen",
                        return_value=urlopen_returning(UNIREF_PAYLOAD)) as urlopen:
            out = search_uniref("hemoglobin", limit=5)
        self.assertNotIn("error", out)
        self.assertEqual(len(out["items"]), 3)
        first = out["items"][0]
        self.assertEqual(first["title"], "UniRef100_P69905")
        self.assertEqual(first["detail"], "51 members")
        self.assertEqual(first["identifier"], "UniRef100_P69905")
        self.assertEqual(first["url"], "https://www.uniprot.org/uniref/UniRef100_P69905")
        self.assertEqual(first["source"], "clusters")
        # proteinCount 만 있어도, 둘 다 문자열이어도 잡아낸다.
        self.assertEqual(out["items"][1]["detail"], "7 members")
        self.assertEqual(out["items"][2]["detail"], "0 members")
        request = urlopen.call_args[0][0]
        self.assertTrue(request.full_url.startswith(f"{UNIPROT_BASE}/uniref/search?"))
        self.assertIn("size=5", request.full_url)
        self.assertIn("format=json", request.full_url)

    def test_limit_clamped(self) -> None:
        with mock.patch("pipeline_mcp.reference.urllib.request.urlopen",
                        return_value=urlopen_returning(UNIREF_PAYLOAD)) as urlopen:
            search_uniref("q", limit=0)
        self.assertIn("size=1", urlopen.call_args[0][0].full_url)


class TestRowContract(unittest.TestCase):
    def test_every_row_has_the_uniform_shape(self) -> None:
        for fn, payload in FIXTURES.items():
            with self.subTest(source=fn.__name__):
                with mock.patch("pipeline_mcp.reference.urllib.request.urlopen",
                                return_value=urlopen_returning(payload)):
                    out = fn("query")
                self.assertTrue(out["items"])
                for row in out["items"]:
                    self.assertEqual(set(row.keys()), ROW_KEYS)
                    self.assertTrue(row["source"] in
                                    {"structural", "curated", "clusters", "published"})


class TestErrorContract(unittest.TestCase):
    def test_empty_query_is_error(self) -> None:
        for fn in FIXTURES:
            with self.subTest(source=fn.__name__):
                self.assertIn("error", fn("  "))
                self.assertIn("error", fn(None))

    def test_network_failure_is_error_contract(self) -> None:
        for fn in FIXTURES:
            with self.subTest(source=fn.__name__):
                with mock.patch("pipeline_mcp.reference.urllib.request.urlopen",
                                side_effect=OSError("down")):
                    out = fn("protein design")
                self.assertIn("error", out)

    def test_literature_network_failure_passthrough(self) -> None:
        with mock.patch.object(literature_mod, "search_literature",
                               return_value={"error": "Europe PMC 요청 실패: OSError"}):
            out = search_reference("literature", "protein")
        self.assertIn("error", out)

    def test_unknown_source(self) -> None:
        self.assertIn("error", search_reference("wikipedia", "q"))

    def test_source_is_normalized(self) -> None:
        with mock.patch.object(literature_mod, "search_literature",
                               return_value={"items": [], "query": "q"}) as fake:
            out = search_reference("  Literature ", "q")
        self.assertNotIn("error", out)
        fake.assert_called_once_with("q", 8)


class TestLiteraturePassthrough(unittest.TestCase):
    def test_rows_adapt_to_uniform_shape(self) -> None:
        lit_rows = [{"title": "Paper A", "authors": "A, B", "journal": "J",
                     "year": "2023", "citations": 12, "open_access": True,
                     "identifier": "10.1/a", "url": "https://doi.org/10.1/a"}]
        with mock.patch.object(literature_mod, "search_literature",
                               return_value={"items": lit_rows, "query": "q"}):
            out = search_reference("literature", "q", limit=3)
        self.assertEqual(out["query"], "q")
        self.assertEqual(len(out["items"]), 1)
        row = out["items"][0]
        self.assertEqual(set(row.keys()), ROW_KEYS)
        self.assertEqual(row["title"], "Paper A")
        self.assertIn("A, B", row["detail"])
        self.assertIn("2023", row["detail"])
        self.assertIn("인용 12", row["detail"])
        self.assertEqual(row["identifier"], "10.1/a")
        self.assertEqual(row["url"], "https://doi.org/10.1/a")
        self.assertEqual(row["source"], "published")


class TestRegistration(unittest.TestCase):
    def test_tool_is_listed(self) -> None:
        names = [t["name"] for t in tool_definitions()]
        self.assertIn("pipeline.search_reference", names)
        schema = [t for t in tool_definitions()
                  if t["name"] == "pipeline.search_reference"][0]["inputSchema"]
        self.assertEqual(schema["properties"]["source"]["enum"],
                         ["pdb", "uniprot", "interpro", "uniref", "literature"])
        self.assertEqual(schema["required"], ["source", "query"])

    def test_dispatch_rejects_blank_query(self) -> None:
        runner = PipelineRunner(output_root="/tmp/unused-ref", mmseqs=None,
                                proteinmpnn=None, soluprot=None, af2=None)
        out = ToolDispatcher(runner).call_tool(
            "pipeline.search_reference", {"source": "pdb", "query": "  "})
        self.assertIn("error", out)

    def test_dispatch_unknown_source_is_error(self) -> None:
        runner = PipelineRunner(output_root="/tmp/unused-ref", mmseqs=None,
                                proteinmpnn=None, soluprot=None, af2=None)
        out = ToolDispatcher(runner).call_tool(
            "pipeline.search_reference", {"source": "bogus", "query": "q"})
        self.assertIn("error", out)

    def test_dispatch_delegates(self) -> None:
        tmp = tempfile.mkdtemp(prefix="ref_")
        try:
            runner = PipelineRunner(output_root=tmp, mmseqs=None, proteinmpnn=None,
                                    soluprot=None, af2=None)
            with mock.patch.object(reference_mod, "search_reference",
                                   return_value={"items": [], "query": "q"}) as fake:
                out = ToolDispatcher(runner).call_tool(
                    "pipeline.search_reference",
                    {"source": "uniprot", "query": "q", "limit": 3})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(out, {"items": [], "query": "q"})
        fake.assert_called_once_with("uniprot", "q", 3)


if __name__ == "__main__":
    unittest.main()
