# Public Release Checklist

Before pushing this folder to GitHub:

1. Fill `CITATION.cff` with the final author list and manuscript title.
2. Choose and add a license file. Do not publish without an explicit license.
3. Confirm that no filled `.env` files are present.
4. Confirm that `pipeline-mcp/models/experts/`, `outputs/`, `logs/`, `.venv/`,
   and `node_modules/` are absent or ignored.
5. Run a secret/path scan:

```bash
rg -n "PRIVATE_HOST_PATTERN|PRIVATE_IP_PATTERN|ORIGINAL_CHECKOUT_PATH" .
```

Also run your normal secret scanner, for example GitHub secret scanning,
Gitleaks, or TruffleHog.

The scan should return only placeholders or documentation examples.

6. Run the backend health check with a local `.env`.
7. Run `bash scripts/reproduce_paper_tables_figures.sh`.
8. Tag a release and archive the exact released package.
9. Create an immutable data/software DOI if the manuscript requires one.
