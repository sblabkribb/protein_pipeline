# Paper-Curated CATH Subset

This directory contains the QC-filtered subset of the expanded CATH execution
archive that is suitable for manuscript-level analysis.

The raw archive contains 73 completed `cath_test_*` run directories. Some of
those runs completed at the orchestration level but did not produce valid
ProteinMPNN designs for the current pipeline input contract. Those cases are
detectable from the artifacts: `designs.fasta`/`designs_filtered.fasta` contain
fallback identifiers and, in some cases, invalid `X`-only sequences. They should
not be interpreted as low-quality designs or as valid pLDDT = 0 examples.

QC inclusion rule:

- run state is `completed`
- all three conservation tiers are present
- at least 100 non-fallback, amino-acid-only design sequences are present
- at least 100 positive pLDDT records are present

Current QC result:

- raw completed run directories: 73
- included publication-grade runs: 23
- excluded runs: 50
- curated design rows: 2,737
- mean pLDDT: 91.906
- maximum pLDDT: 97.889
- mean SoluProt: 0.615
- maximum SoluProt: 0.971

Files:

- `curated_dataset.csv`: per-design table for the included runs only
- `curated_per_target_summary.csv`: target-level summary for the included runs
- `curated_summary.json`: aggregate counts and included/excluded run IDs
- `run_qc_summary.csv`: QC metrics for all 73 completed run directories
- `excluded_runs.csv`: excluded runs and exclusion reasons
- `included_runs.txt`: run IDs retained for manuscript-level analysis
- `excluded_runs.txt`: run IDs excluded from manuscript-level analysis
