# CATH classification inputs

`rapid_target_superfamily.json` maps each RAPID CATH target id to its
`C.A.T.H` homologous-superfamily code. It is derived from the CATH
`cath-domain-list.txt` release recorded in `cath-domain-list.txt.sha256`.

Regenerate with:

```bash
python3 scripts/transcoder/00_fetch_cath_classification.py
```

The 43 MB source list itself is gitignored; only the checksum and the derived
1,472-entry mapping are tracked.

## Measured grouping structure (2026-09-03)

All 1,472 RAPID targets were resolved. Grouping the mapping at each CATH level:

| Level | Groups | Largest group | Singletons |
|---|---|---|---|
| class `C` | 5 | 634 | 0 |
| architecture `C.A` | 43 | 290 | 13 |
| topology `C.A.T` | 1472 | 1 | 1472 |
| superfamily `C.A.T.H` | 1472 | 1 | 1472 |

The target set is already non-redundant at topology and superfamily level, so a
superfamily-holdout split is the *same partition* as leave-one-target-out.
Architecture (`C.A`, 43 groups) is the only coarser level that yields a
genuinely harder generalization test.
