from __future__ import annotations

import json
from pathlib import Path

from pipeline_mcp import tools
from pipeline_mcp.models import PipelineRequest, SequenceRecord
from pipeline_mcp.objective_planner import (
    Objective,
    apply_edits,
    build_plan,
    plan_to_request_overrides,
)
from pipeline_mcp.pipeline import _dummy_backbone_pdb, _run_thermomp_gate


BACKBONE_PDB = _dummy_backbone_pdb("ACDEFGHIK")


class FakeThermoMPNN:
    """ThermoMPNN 워커 계약을 흉내낸다: additive_ddg_kcal_mol + per-mutation."""

    def __init__(
        self,
        ddg_by_mutation: dict[str, float] | None = None,
        default_ddg: float = 0.1,
        fail_on: set[str] | None = None,
    ) -> None:
        self.ddg_by_mutation = ddg_by_mutation or {}
        self.default_ddg = default_ddg
        self.fail_on = fail_on or set()
        self.calls: list[dict] = []

    def predict(
        self,
        *,
        pdb_text: str,
        target_id: str = "design",
        chain: str | None = None,
        mutations: list[str] | None = None,
        wt_sequence: str | None = None,
        top_n: int | None = None,
    ) -> dict:
        self.calls.append(
            {
                "pdb_text": pdb_text,
                "target_id": target_id,
                "chain": chain,
                "mutations": list(mutations or []),
                "wt_sequence": wt_sequence,
            }
        )
        for mutation in mutations or []:
            if mutation in self.fail_on:
                raise RuntimeError(f"worker blew up on {mutation}")
        per_mutation = [
            {
                "wildtype": m[0],
                "resseq": int(m[1:-1]),
                "mutation": m[-1],
                "ddG_kcal_mol": float(self.ddg_by_mutation.get(m, self.default_ddg)),
            }
            for m in (mutations or [])
        ]
        additive = sum(item["ddG_kcal_mol"] for item in per_mutation)
        return {"additive_ddg_kcal_mol": additive, "mutations": per_mutation}


def _request(**overrides) -> PipelineRequest:
    defaults: dict = dict(
        target_fasta=">q1\nACDEFGHIK\n",
        target_pdb="1abc",
        thermomp_gate=True,
    )
    defaults.update(overrides)
    return PipelineRequest(**defaults)


def _seq(seq_id: str, sequence: str) -> SequenceRecord:
    return SequenceRecord(id=seq_id, sequence=sequence, header=seq_id)


def _tier_dir(tmp_path: Path) -> Path:
    tier_dir = tmp_path / "tiers" / "50"
    tier_dir.mkdir(parents=True, exist_ok=True)
    return tier_dir


def _artifact_payload(tmp_path: Path) -> dict:
    return json.loads(
        ((tmp_path / "tiers" / "50") / "thermomp.json").read_text(encoding="utf-8")
    )


def test_gate_off_returns_unfiltered_without_artifact(tmp_path):
    tier_dir = _tier_dir(tmp_path)
    passed = [_seq("s1", "ACDEFGHIK"), _seq("s2", "ACDEFGHIW")]

    kept, kept_ids, artifact = _run_thermomp_gate(
        passed=passed,
        passed_ids=["s1", "s2"],
        backbone_pdb_text=BACKBONE_PDB,
        wt_sequence="ACDEFGHIK",
        tier_dir=tier_dir,
        request=_request(thermomp_gate=False),
        thermomp_client=FakeThermoMPNN(),
        cache={},
    )

    assert artifact is None
    assert [s.id for s in kept] == ["s1", "s2"]
    assert kept_ids == ["s1", "s2"]
    assert not (tier_dir / "thermomp.json").exists()


def test_gate_filters_above_cutoff_and_writes_artifact(tmp_path):
    client = FakeThermoMPNN(ddg_by_mutation={"K9W": 2.5, "A1W": 0.5})
    passed = [
        _seq("s_wt", "ACDEFGHIK"),
        _seq("s_hi", "ACDEFGHIW"),  # K9W -> 2.5
        _seq("s_lo", "WCDEFGHIK"),  # A1W -> 0.5
    ]

    kept, kept_ids, artifact = _run_thermomp_gate(
        passed=passed,
        passed_ids=["s_wt", "s_hi", "s_lo"],
        backbone_pdb_text=BACKBONE_PDB,
        wt_sequence="ACDEFGHIK",
        tier_dir=_tier_dir(tmp_path),
        request=_request(thermomp_ddg_cutoff=1.0),
        thermomp_client=client,
        cache={},
    )

    assert [s.id for s in kept] == ["s_wt", "s_lo"]
    assert kept_ids == ["s_wt", "s_lo"]
    assert artifact["scores"] == {"s_wt": 0.0, "s_hi": 2.5, "s_lo": 0.5}
    assert artifact["cutoff"] == 1.0
    assert artifact["passed_ids"] == ["s_wt", "s_lo"]
    assert "skipped" not in artifact
    assert _artifact_payload(tmp_path)["passed_ids"] == ["s_wt", "s_lo"]
    assert client.calls[0]["mutations"] == ["K9W"]
    assert client.calls[1]["mutations"] == ["A1W"]
    assert client.calls[0]["wt_sequence"] == "ACDEFGHIK"
    assert client.calls[0]["chain"] == "A"


def test_boundary_ddg_equal_to_cutoff_passes(tmp_path):
    client = FakeThermoMPNN(ddg_by_mutation={"K9W": 1.0, "A1W": 0.5})
    passed = [_seq("s_hi", "ACDEFGHIW"), _seq("s_lo", "WCDEFGHIK")]

    kept, _, artifact = _run_thermomp_gate(
        passed=passed,
        passed_ids=["s_hi", "s_lo"],
        backbone_pdb_text=BACKBONE_PDB,
        wt_sequence="ACDEFGHIK",
        tier_dir=_tier_dir(tmp_path),
        request=_request(thermomp_ddg_cutoff=1.0),
        thermomp_client=client,
        cache={},
    )

    assert "s_hi" in [s.id for s in kept]
    assert artifact["scores"]["s_hi"] == 1.0


def test_wt_sequence_scores_zero_without_predict_call(tmp_path):
    client = FakeThermoMPNN()
    passed = [_seq("s_wt", "ACDEFGHIK"), _seq("s_hi", "ACDEFGHIW")]

    _, _, artifact = _run_thermomp_gate(
        passed=passed,
        passed_ids=["s_wt", "s_hi"],
        backbone_pdb_text=BACKBONE_PDB,
        wt_sequence="ACDEFGHIK",
        tier_dir=_tier_dir(tmp_path),
        request=_request(),
        thermomp_client=client,
        cache={},
    )

    assert artifact["scores"]["s_wt"] == 0.0
    # 빈 mutations 로 predict 를 부르면 워커가 전체 단일-변이 스캔을 돌린다.
    assert [c["target_id"] for c in client.calls] == ["s_hi"]


def test_prediction_failure_passes_sequence_and_records_note(tmp_path):
    client = FakeThermoMPNN(ddg_by_mutation={"K9W": 2.5, "A1W": 0.5}, fail_on={"K9W"})
    passed = [_seq("s_hi", "ACDEFGHIW"), _seq("s_lo", "WCDEFGHIK")]

    kept, kept_ids, artifact = _run_thermomp_gate(
        passed=passed,
        passed_ids=["s_hi", "s_lo"],
        backbone_pdb_text=BACKBONE_PDB,
        wt_sequence="ACDEFGHIK",
        tier_dir=_tier_dir(tmp_path),
        request=_request(thermomp_ddg_cutoff=1.0),
        thermomp_client=client,
        cache={},
    )

    assert "s_hi" in [s.id for s in kept]
    assert "s_hi" in kept_ids
    assert artifact["scores"]["s_hi"] is None
    assert any("s_hi" in note for note in artifact["notes"])


def test_cache_reuses_prediction_across_tiers(tmp_path):
    client = FakeThermoMPNN(ddg_by_mutation={"K9W": 2.5, "A1W": 0.5})
    request = _request(thermomp_ddg_cutoff=1.0)
    cache: dict = {}
    for _ in range(2):
        _run_thermomp_gate(
            passed=[_seq("s_hi", "ACDEFGHIW")],
            passed_ids=["s_hi"],
            backbone_pdb_text=BACKBONE_PDB,
            wt_sequence="ACDEFGHIK",
            tier_dir=_tier_dir(tmp_path),
            request=request,
            thermomp_client=client,
            cache=cache,
        )

    assert len(client.calls) == 1
    assert cache


def _assert_skipped(tmp_path, kept, kept_ids, artifact, reason):
    assert artifact["skipped"] == reason
    assert [s.id for s in kept] == ["s1", "s2"]
    assert kept_ids == ["s1", "s2"]
    assert _artifact_payload(tmp_path)["skipped"] == reason


def test_client_none_writes_skipped_artifact_and_keeps_all(tmp_path):
    kept, kept_ids, artifact = _run_thermomp_gate(
        passed=[_seq("s1", "ACDEFGHIK"), _seq("s2", "ACDEFGHIW")],
        passed_ids=["s1", "s2"],
        backbone_pdb_text=BACKBONE_PDB,
        wt_sequence="ACDEFGHIK",
        tier_dir=_tier_dir(tmp_path),
        request=_request(),
        thermomp_client=None,
        cache={},
    )

    _assert_skipped(tmp_path, kept, kept_ids, artifact, "thermomp_unavailable")


def test_empty_backbone_skips(tmp_path):
    kept, kept_ids, artifact = _run_thermomp_gate(
        passed=[_seq("s1", "ACDEFGHIK"), _seq("s2", "ACDEFGHIW")],
        passed_ids=["s1", "s2"],
        backbone_pdb_text="   ",
        wt_sequence="ACDEFGHIK",
        tier_dir=_tier_dir(tmp_path),
        request=_request(),
        thermomp_client=FakeThermoMPNN(),
        cache={},
    )

    _assert_skipped(tmp_path, kept, kept_ids, artifact, "backbone_unavailable")


def test_dry_run_skips(tmp_path):
    kept, kept_ids, artifact = _run_thermomp_gate(
        passed=[_seq("s1", "ACDEFGHIK"), _seq("s2", "ACDEFGHIW")],
        passed_ids=["s1", "s2"],
        backbone_pdb_text=BACKBONE_PDB,
        wt_sequence="ACDEFGHIK",
        tier_dir=_tier_dir(tmp_path),
        request=_request(dry_run=True),
        thermomp_client=FakeThermoMPNN(),
        cache={},
    )

    _assert_skipped(tmp_path, kept, kept_ids, artifact, "dry_run")


def test_multi_chain_backbone_skips(tmp_path):
    multi_chain_pdb = (
        _dummy_backbone_pdb("ACDE", chain_id="A") + _dummy_backbone_pdb("FGHIK", chain_id="B")
    )

    kept, kept_ids, artifact = _run_thermomp_gate(
        passed=[_seq("s1", "ACDEFGHIK"), _seq("s2", "ACDEFGHIW")],
        passed_ids=["s1", "s2"],
        backbone_pdb_text=multi_chain_pdb,
        wt_sequence="ACDEFGHIK",
        tier_dir=_tier_dir(tmp_path),
        request=_request(),
        thermomp_client=FakeThermoMPNN(),
        cache={},
    )

    _assert_skipped(tmp_path, kept, kept_ids, artifact, "skipped_multi_chain")


def test_build_plan_includes_thermomp_decisions():
    plan = build_plan(Objective(weights={"solubility": 1.0}))
    by_field = {d["field"]: d for d in plan["decisions"]}

    assert "thermomp_gate" in by_field
    assert "thermomp_ddg_cutoff" in by_field
    assert by_field["thermomp_gate"]["value"] is False
    assert by_field["thermomp_ddg_cutoff"]["value"] == 2.0
    assert by_field["thermomp_gate"]["editable"] is True
    assert by_field["thermomp_ddg_cutoff"]["editable"] is True
    for field in ("thermomp_gate", "thermomp_ddg_cutoff"):
        kinds = {e["kind"] for e in by_field[field]["evidence"]}
        assert kinds == {"assumption"}


def test_plan_overrides_map_thermomp_fields():
    plan = build_plan(Objective(weights={"solubility": 1.0}))

    out = plan_to_request_overrides(plan)

    assert out["request_overrides"]["thermomp_gate"] is False
    assert out["request_overrides"]["thermomp_ddg_cutoff"] == 2.0
    assert "thermomp_gate" not in out["unmapped_decisions"]
    assert "thermomp_ddg_cutoff" not in out["unmapped_decisions"]


def test_edited_plan_overrides_carry_user_values():
    plan = build_plan(Objective(weights={"solubility": 1.0}))
    edited = apply_edits(plan, {"thermomp_gate": True, "thermomp_ddg_cutoff": 1.5})

    out = plan_to_request_overrides(edited)

    assert out["request_overrides"]["thermomp_gate"] is True
    assert out["request_overrides"]["thermomp_ddg_cutoff"] == 1.5


def test_request_defaults_are_off_with_cutoff_2():
    request = PipelineRequest(target_fasta=">q\nACDEFGHIK\n", target_pdb="1abc")
    assert request.thermomp_gate is False
    assert request.thermomp_ddg_cutoff == 2.0


def test_pipeline_request_from_args_parses_gate_fields():
    request = tools.pipeline_request_from_args(
        {
            "target_fasta": ">q1\nACDEFGHIK\n",
            "thermomp_gate": True,
            "thermomp_ddg_cutoff": 2.5,
        }
    )
    assert request.thermomp_gate is True
    assert request.thermomp_ddg_cutoff == 2.5


def test_pipeline_request_from_args_defaults_keep_gate_off():
    request = tools.pipeline_request_from_args({"target_fasta": ">q1\nACDEFGHIK\n"})
    assert request.thermomp_gate is False
    assert request.thermomp_ddg_cutoff == 2.0


def test_pipeline_run_schema_advertises_thermomp_gate_fields():
    defs = {tool["name"]: tool for tool in tools.tool_definitions()}
    props = defs["pipeline.run"]["inputSchema"]["properties"]

    assert props["thermomp_gate"]["type"] == "boolean"
    assert props["thermomp_ddg_cutoff"]["type"] == "number"
    assert "AF2" in props["thermomp_gate"]["description"]
    assert "kcal/mol" in props["thermomp_ddg_cutoff"]["description"]
