#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$PROJECT_ROOT"

"$PYTHON_BIN" scripts/benchmark/05_aggregate_and_test.py
"$PYTHON_BIN" scripts/benchmark/06_make_figures.py
"$PYTHON_BIN" scripts/benchmark/07_mpnn_error_decomposition.py
"$PYTHON_BIN" scripts/benchmark/09_bias_analysis.py
"$PYTHON_BIN" scripts/benchmark/10_ensemble_benchmark.py
"$PYTHON_BIN" scripts/benchmark/11_make_method_figures.py
"$PYTHON_BIN" scripts/benchmark/12_make_cath_curated_figure.py
if [[ -d /opt/protein_pipeline/cath_outputs ]]; then
  "$PYTHON_BIN" scripts/benchmark/17_run_pooled_surrogate_scaling.py \
    --cath-root /opt/protein_pipeline/cath_outputs \
    --feature-mode composition
fi

echo "Regenerated benchmark tables and figures."
