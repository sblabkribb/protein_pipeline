# RAPID Deployment Security

This document defines the boundary between the public RAPID source package and
hosted RAPID services.

## Environment Policy

Use separate deployment environments for development, staging, and production.

| Environment | Audience | Public URL policy | Recommended protection |
| --- | --- | --- | --- |
| `dev` | maintainers only | never publish | VPN, IP allowlist, or reverse-proxy auth |
| `staging` | maintainers and invited reviewers | never publish | reverse-proxy auth or institutional SSO |
| `production` | intended users | publish only when ready | app auth, quotas, monitoring, cost controls |

Development and staging routes should not appear in the manuscript, README,
paper supplement, or public GitHub release notes. Use them only for internal
validation.

## Reverse Proxy Requirements

Run the backend on loopback and expose it only through HTTPS:

```bash
PYTHONPATH=src python -m pipeline_mcp.http_server --host 127.0.0.1 --port 18080
```

Proxy `/api/*` and `/mcp` to the loopback backend. Protect those routes at the
reverse proxy if the application is not meant to be public.

For a minimal private staging route with Caddy basic auth:

```caddyfile
staging.example.org {
  encode zstd gzip
  basic_auth {
    reviewer <hashed-password>
  }

  handle /api/* {
    reverse_proxy 127.0.0.1:18085
  }
  handle /mcp* {
    reverse_proxy 127.0.0.1:18085
  }
  handle {
    root * /srv/protein_pipeline_staging
    try_files {path} /index.html
    file_server
  }
}
```

Use `caddy hash-password` to generate the password hash. For institutional
deployments, prefer OIDC or an existing `forward_auth` gateway over shared
passwords.

## Secrets

Keep these values out of Git and out of frontend bundles:

- `RUNPOD_API_KEY`
- RunPod endpoint IDs
- S3 access and secret keys
- OIDC client secrets
- local admin passwords
- provider bearer tokens such as `PROTEINMPNN_GPU_TOKEN` or
  `ESM_EMBEDDING_TOKEN`

Store them in the server-local `.env` file or GitHub Environment secrets. The
public `.env.example` file must contain placeholders only.

## Public Production Guardrails

Before a production URL is advertised, configure:

- authentication for the UI and API;
- job-level quotas or an approval gate for expensive GPU calls;
- CORS restricted to the production frontend origin;
- object-storage lifecycle rules for large outputs;
- log retention that does not expose sequences, credentials, or tokens;
- health checks for backend, frontend, and provider connectivity.

## Pre-Deploy Checklist

Run before every `deploy_from_github.sh`, on each target you are about to
deploy.

### 1. Check the target for local drift

```bash
for d in /opt/protein_pipeline /opt/protein_pipeline-staging /opt/protein_pipeline-dev; do
  echo "== $d ($(git -C "$d" rev-parse --short HEAD))"
  git -C "$d" status --porcelain --untracked-files=no
done
```

Every target should print nothing under its header. A line here means a
tracked file was edited on the server and never committed, and the change
exists in exactly one place.

Recover it before deploying — `git checkout --force` will overwrite it, and
the deploy will refuse to start in the meantime (`Refusing to deploy over
tracked local modifications`, exit 3). This is the only place the drift is
detected, so it is only caught when someone deploys.

This has happened. On 2026-09-02 `pipeline_mcp/s3.py` gained `list_runs`,
`pull_outputs` and `pull_summary` directly on production, and
`scripts/11_train_reward_model.py` was written there the same day. Neither
was committed. The drift sat for nine days because nobody deployed, and both
were found only while dry-running a deploy. The script was in no branch at
all, and `git clean -fd` would have deleted it.

### 2. Check what `git clean -fd` would remove

```bash
git -C "$TARGET" clean -nd
```

Anything listed is untracked and will be deleted. `frontend/pipeline_skill.zip`
is expected — the deploy regenerates it. Anything else needs a decision: commit
it, back it up, or confirm it is disposable.

Do not add `-x`. Without it, ignored files survive; with it, `cath_train/`,
`cath_val/` and `cath_test/` are deleted. Those directories hold 1,472 CATH
domain PDBs and are not reported as untracked only because `.gitignore`'s
`*.pdb` rule covers every file inside them.

### 3. Confirm large untracked data is archived elsewhere

Files too big for the tree belong in object storage with a manifest recording
bucket, key and sha256, and `.gitignore` should name them. See
`public_data/benchmark/reward_embeddings_archive.json` for the shape.

## Release Checklist

Before publishing a release package, run:

```bash
rg -n "(RUNPOD_API_KEY=.+|ENDPOINT_ID=.+|AWS_SECRET|SECRET_KEY=.+|PRIVATE KEY|\\bAKIA[0-9A-Z]{16}\\b)" .
find . -type d \( -name node_modules -o -name .pytest_cache -o -name __pycache__ -o -name dist \)
```

The first command should return only placeholders or documentation examples.
The second command should return no generated dependency/build/cache
directories.
