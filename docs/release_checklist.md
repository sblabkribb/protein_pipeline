# Public Release Checklist

Before pushing this folder to GitHub:

1. Fill `CITATION.cff` with the final author list and manuscript title.
2. Choose and add a license file. Do not publish without an explicit license.
3. Confirm that no filled `.env` files are present.
4. Confirm that hosted `dev` and `staging` URLs are private. Do not include them
   in public docs, release notes, or manuscript files.
5. Confirm that `pipeline-mcp/models/experts/`, `outputs/`, `logs/`, `.venv/`,
   `frontend/dist/`, `.pytest_cache/`, `__pycache__/`, and `node_modules/` are
   absent or ignored.
6. Run a generated-file scan:

```bash
find . -type d \( -name node_modules -o -name .pytest_cache -o -name __pycache__ -o -name dist \)
```

The command should print no paths.

7. Run a secret/path scan:

```bash
rg -n "(RUNPOD_API_KEY=.+|ENDPOINT_ID=.+|AWS_SECRET|SECRET_KEY=.+|PRIVATE KEY|\\bAKIA[0-9A-Z]{16}\\b)" .
# 기관 고유 호스트·도메인은 scripts/.release_mask.local (git 무시) 에 두고
# scripts/make_release_archive.py 가 읽어서 가린다. 여기 적지 않는다.
rg -n "(rapid-dev|rapid-staging)" .
```

Also run your normal secret scanner, for example GitHub secret scanning,
Gitleaks, or TruffleHog.

The scan should return only placeholders or documentation examples.

8. Scan the benchmark data for internal worker addresses and worker-side paths.
   These appear in the `error` column of the structure-prediction grids and in a
   few backbone metadata files, left behind by failed worker calls:

```bash
python3 scripts/sanitize_public_data.py --check
```

   The command exits non-zero while any hit remains. Build the sanitised copy
   with `--out <dir>` and publish that copy, not the working tree. The
   substitution only touches rows whose `status` is not `ok`, which every loader
   skips, so analysis results are unchanged; this was verified by re-running the
   primary analysis on the sanitised grid.

9. Confirm that the inputs needed to re-run the analyses are actually included in
   the release. The repository treats `public_data/` as run artifacts, so the
   structure-prediction grid, the candidate list, the ProteinMPNN scores and the
   ESM-2 embedding cache must be added explicitly or shipped through a separate
   archive. See `docs/reproducibility.md` for the file list and sizes.

10. Check third-party licences for anything shipped or scripted. SoluProt is free
    for academic use only and its standalone package is **not** redistributed here —
    `scripts/score_soluprot.py` downloads nothing and expects the user to fetch it.
    The USEARCH binary it calls is public domain (CC0). Do not vendor either one.

11. Run the backend health check with a local `.env`.
12. Run `bash scripts/reproduce_paper_tables_figures.sh`. It re-runs every
    analysis from the stored grid and compares all numbers against the committed
    results; a non-zero exit means a mismatch.
13. Verify that `manuscript/` and `figures/` match the paper draft.
14. Tag a release and archive the exact released package.
15. Create an immutable data/software DOI if the manuscript requires one.


## Handling addresses that are already pushed

The scans above cover the working tree. They do not rewrite history. If an
internal address has already reached a remote branch, treat it as a separate
decision and do not rewrite published history on your own:

1. Establish whether the repository is public or private, and which branches
   carry the string. `git branch -r --contains <commit>` tells you whether a
   commit reached a remote at all.
2. Judge the exposure. A worker hostname behind a firewall is a different
   problem from a leaked credential, and the two call for different urgency.
3. If the value is only an internal address, the cheapest safe route is usually
   to sanitise the working tree, land that as an ordinary commit, and leave the
   old objects in place — rewriting history breaks collaborators' clones, tags
   and open pull requests.
4. If a credential leaked, rotate it first. Rewriting history does not undo the
   exposure.
5. For the manuscript release specifically, consider publishing from a clean
   history — a fresh repository or an orphan branch containing only the code,
   data and documents the paper needs. That avoids rewriting anything while
   still giving reviewers a repository with no internal references.

Known state at the time of writing: `origin/main` is clean. `origin/develop`
carries the address in `public_data/benchmark/gate0/wave_03_results.json` and
`public_data/benchmark/gate0/backbones/mpnn_encoder.meta.json`, and
`origin/rapid/gate0-allocation-holdout` carries it in
`scripts/11_train_reward_model.py`.
