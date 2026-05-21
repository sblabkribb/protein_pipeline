#!/usr/bin/env bash
set -Eeuo pipefail

repo_url="${DEPLOY_REPO_URL:-git@github.com:sblabkribb/protein_pipeline.git}"
target="${DEPLOY_TARGET:?DEPLOY_TARGET is required: dev, staging, or prod}"
sha="${DEPLOY_SHA:?DEPLOY_SHA is required}"

case "$target" in
  dev)
    deploy_path="/opt/protein_pipeline-dev"
    service_name="pipeline-mcp-dev.service"
    health_port="18087"
    ;;
  staging)
    deploy_path="/opt/protein_pipeline-staging"
    service_name="pipeline-mcp-staging.service"
    health_port="18085"
    ;;
  prod)
    deploy_path="/opt/protein_pipeline"
    service_name="pipeline-mcp.service"
    health_port="18080"
    ;;
  *)
    echo "Unsupported DEPLOY_TARGET: $target" >&2
    exit 2
    ;;
esac

if [[ ! -d "$deploy_path/.git" ]]; then
  mkdir -p "$(dirname "$deploy_path")"
  git clone "$repo_url" "$deploy_path"
fi

cd "$deploy_path"
git remote set-url origin "$repo_url"
git fetch --tags origin

dirty_status="$(git status --porcelain --untracked-files=no)"
if [[ -n "$dirty_status" ]]; then
  mapfile -t dirty_files < <(
    {
      git diff --name-only
      git diff --name-only --cached
    } | sort -u
  )

  safe_to_overwrite="true"
  for dirty_file in "${dirty_files[@]}"; do
    if [[ ! -f "$dirty_file" ]]; then
      safe_to_overwrite="false"
      break
    fi
    if ! git cat-file -e "${sha}:${dirty_file}" 2>/dev/null; then
      safe_to_overwrite="false"
      break
    fi
    if ! cmp -s "$dirty_file" <(git show "${sha}:${dirty_file}"); then
      safe_to_overwrite="false"
      break
    fi
  done

  if [[ "$safe_to_overwrite" != "true" ]]; then
    echo "Refusing to deploy over tracked local modifications in $deploy_path." >&2
    git status --short
    exit 3
  fi

  echo "Tracked local modifications already match ${sha}; continuing."
fi

git checkout --force "$sha"
git clean -fd

if [[ ! -x venv/bin/python3 ]]; then
  python3 -m venv venv
fi

venv/bin/python3 -m pip install --upgrade pip
venv/bin/python3 -m pip install -r pipeline-mcp/requirements.txt

if [[ -f frontend/package-lock.json ]]; then
  npm --prefix frontend ci
  npm --prefix frontend run build
fi

if [[ "$(id -u)" -eq 0 ]]; then
  systemctl restart "$service_name"
else
  sudo systemctl restart "$service_name"
fi

for attempt in {1..30}; do
  if curl -fsS "http://127.0.0.1:${health_port}/healthz"; then
    echo
    exit 0
  fi
  sleep 1
done

echo "Health check failed for ${service_name} on port ${health_port}." >&2
if command -v journalctl >/dev/null 2>&1; then
  journalctl -u "$service_name" -n 80 --no-pager >&2 || true
fi
exit 4
