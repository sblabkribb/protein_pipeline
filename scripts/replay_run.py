"""Replay a finished or interrupted run from its saved request.json.

Mirrors pipeline_mcp.run_recovery._resume_one: the request payload is reused
verbatim so the request hash - and therefore every upstream stage cache - is
preserved. Intended to be launched with the pipeline-mcp service's own
EnvironmentFile so client credentials come from the same place the service
reads them.

Usage: replay_run.py <run_id> [output_root]
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, "/opt/protein_pipeline/pipeline-mcp/src")

# The service's EnvironmentFile sets PIPELINE_OUTPUT_ROOT, and systemd applies it
# after any Environment= override, so an output root passed on the command line has
# to win here instead - otherwise a rehearsal against a copied run silently reads
# and acts on the real outputs directory.
if len(sys.argv) > 2 and str(sys.argv[2]).strip():
    os.environ["PIPELINE_OUTPUT_ROOT"] = str(sys.argv[2]).strip()

from pipeline_mcp.app import build_runner  # noqa: E402
from pipeline_mcp.tools import ToolDispatcher  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: replay_run.py <run_id> [output_root]", file=sys.stderr)
        return 2
    run_id = sys.argv[1]
    root = Path(os.environ.get("PIPELINE_OUTPUT_ROOT", "/opt/protein_pipeline/outputs"))
    run_dir = root / run_id
    print(f"[replay] output_root={root}", flush=True)

    payload = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print(f"[replay] {run_id}: request.json is not an object", file=sys.stderr)
        return 1
    payload["run_id"] = run_id

    # pipeline.run refuses a run whose status is still "running" (duplicate-job
    # guard), which is exactly the state an interrupted run is left in.
    status_path = run_dir / "status.json"
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        status = None
    if isinstance(status, dict) and str(status.get("state") or "").lower() == "running":
        status["state"] = "interrupted"
        status_path.write_text(json.dumps(status), encoding="utf-8")

    print(f"[replay] starting run_id={run_id}", flush=True)
    result = ToolDispatcher(build_runner()).call_tool("pipeline.run", payload)
    print("[replay] finished:", json.dumps(result, default=str)[:800], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
