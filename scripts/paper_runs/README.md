# Paper Run Scripts

This directory contains operational wrappers for the RAPID manuscript data
refresh. These scripts may require private RunPod/NCP S3 credentials and are
not part of the public reproducibility package.

Use this directory for live data-generation jobs:

1. `01_fetch_cath_s3_results.py` downloads completed CATH artifacts from NCP S3.
2. `02_launch_structural_context_ablation.py` launches the 8-target structural-context ablation.
3. `03_launch_multiround_evolution.py` launches 4-5 multi-round evolution traces.

Keep reusable analysis and figure-generation code in `scripts/benchmark/`.
Keep public, credential-free reproduction code in `public_release/scripts/`.
