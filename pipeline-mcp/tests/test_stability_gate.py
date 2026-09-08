from __future__ import annotations

from pipeline_mcp import tools
from pipeline_mcp.models import PipelineRequest


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
