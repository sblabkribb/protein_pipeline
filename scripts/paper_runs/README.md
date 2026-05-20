# Paper Run Scripts

This directory contains operational wrappers for the RAPID manuscript data
refresh. These scripts may require private RunPod/NCP S3 credentials and are
not part of the public reproducibility package.

Use this directory for live data-generation jobs:

1. `01_fetch_cath_s3_results.py` downloads completed CATH artifacts from NCP S3.
2. `02_launch_structural_context_ablation.py` launches the 8-target structural-context ablation.
3. `03_launch_surrogate_triage_budget.py` launches the AF2-budgeted surrogate-triage runs used for claim 2.
4. `03_launch_multiround_evolution.py` launches experimental-feedback or legacy in-silico evolution traces.
5. `05_collect_surrogate_triage_budget.py` collects surrogate-triage AF2 budget summaries from completed runs.

Keep reusable analysis and figure-generation code in `scripts/benchmark/`.
Keep public, credential-free reproduction code in `public_release/scripts/`.
