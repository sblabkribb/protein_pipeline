"""Time the read-only tool calls the console issues on a view switch.

Read-only: status/listing/artifact reads only, no run mutation.
Usage: time_tools.py <run_id>
"""

import sys
import time

sys.path.insert(0, "/opt/protein_pipeline/pipeline-mcp/src")

from pipeline_mcp.app import build_runner  # noqa: E402
from pipeline_mcp.tools import ToolDispatcher  # noqa: E402


def main() -> int:
    run_id = sys.argv[1]
    d = ToolDispatcher(build_runner())

    calls = [
        ("pipeline.status", {"run_id": run_id}),
        ("pipeline.list_artifacts", {"run_id": run_id}),
        ("pipeline.read_artifact", {"run_id": run_id, "path": "backbones.json", "max_bytes": 300000}),
        ("pipeline.read_artifact", {"run_id": run_id, "path": "events.jsonl", "max_bytes": 512000}),
        ("pipeline.read_artifact", {"run_id": run_id, "path": "request.json", "max_bytes": 2000000}),
        ("pipeline.list_agent_events", {"run_id": run_id}),
        ("pipeline.get_hit_list", {"run_id": run_id}),
        ("pipeline.get_report", {"run_id": run_id}),
        ("pipeline.compare_runs", {"run_id": run_id}),
    ]

    print(f"{'tool':-<42} {'ms':>9}  {'bytes':>10}")
    total = 0.0
    for name, args in calls:
        t0 = time.perf_counter()
        try:
            out = d.call_tool(name, args)
            size = len(str(out))
            err = ""
        except Exception as exc:  # noqa: BLE001 - timing harness
            size = 0
            err = f"  <{type(exc).__name__}: {str(exc)[:60]}>"
        ms = (time.perf_counter() - t0) * 1000.0
        total += ms
        label = name if "path" not in args else f"{name}[{args['path']}]"
        print(f"{label:-<42} {ms:>9.1f}  {size:>10}{err}")
    print(f"{'TOTAL':-<42} {total:>9.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
