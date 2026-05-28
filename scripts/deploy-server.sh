#!/usr/bin/env bash
set -Eeuo pipefail

# Deploy admin-platform to a Docker host over SSH.
#
# Defaults target the company server requested by the project owner.
# Override with environment variables when needed:
#   SSH_USER=root SSH_KEY=~/.ssh/id_rsa ./scripts/deploy-server.sh
#   DEPLOY_HOST=10.0.1.42 DEPLOY_DIR=/opt/admin-platform BRANCH=main ./scripts/deploy-server.sh

DEPLOY_HOST="${DEPLOY_HOST:-10.0.1.42}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/admin-platform}"
BRANCH="${BRANCH:-main}"
REPO_URL="${REPO_URL:-$(git config --get remote.origin.url 2>/dev/null || true)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker/docker-compose.yml}"
SSH_USER="${SSH_USER:-}"
SSH_PORT="${SSH_PORT:-22}"
SSH_KEY="${SSH_KEY:-}"
SKIP_PULL="${SKIP_PULL:-0}"
PUBLIC_HOST="${PUBLIC_HOST:-$DEPLOY_HOST}"

if [[ -z "$REPO_URL" ]]; then
  echo "REPO_URL is empty. Set REPO_URL=https://... before running." >&2
  exit 1
fi

target="$DEPLOY_HOST"
if [[ -n "$SSH_USER" ]]; then
  target="${SSH_USER}@${DEPLOY_HOST}"
fi

ssh_args=(-p "$SSH_PORT")
if [[ -n "$SSH_KEY" ]]; then
  ssh_args+=(-i "$SSH_KEY")
fi

echo "Deploy target: $target"
echo "Deploy dir:    $DEPLOY_DIR"
echo "Branch:        $BRANCH"
echo "Repo:          $REPO_URL"
echo

ssh "${ssh_args[@]}" "$target" bash -s -- \
  "$DEPLOY_DIR" \
  "$REPO_URL" \
  "$BRANCH" \
  "$COMPOSE_FILE" \
  "$SKIP_PULL" \
  "$PUBLIC_HOST" <<'REMOTE_SCRIPT'
set -Eeuo pipefail

deploy_dir="$1"
repo_url="$2"
branch="$3"
compose_file="$4"
skip_pull="$5"
public_host="$6"

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

docker_cmd() {
  if docker "$@" >/dev/null 2>&1; then
    docker "$@"
    return
  fi

  if command -v sudo >/dev/null 2>&1; then
    sudo docker "$@"
    return
  fi

  docker "$@"
}

compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
    return
  fi

  if command -v sudo >/dev/null 2>&1 && sudo docker compose version >/dev/null 2>&1; then
    sudo docker compose "$@"
    return
  fi

  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
    return
  fi

  echo "Missing Docker Compose. Install Docker Compose v2 or docker-compose." >&2
  exit 1
}

wait_http() {
  local url="$1"
  local label="$2"
  local attempts="${3:-40}"

  for _ in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$label is ready: $url"
      return 0
    fi
    sleep 3
  done

  echo "$label did not become ready: $url" >&2
  return 1
}

require_cmd git
require_cmd docker
require_cmd curl

if [[ ! -d "$deploy_dir/.git" ]]; then
  echo "Cloning repository..."
  mkdir -p "$(dirname "$deploy_dir")"
  git clone --branch "$branch" "$repo_url" "$deploy_dir"
fi

cd "$deploy_dir"

if [[ "$skip_pull" != "1" ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Remote worktree is dirty. Commit/stash server-side changes or run with SKIP_PULL=1." >&2
    git status --short
    exit 1
  fi

  echo "Fetching latest code..."
  git fetch origin "$branch"
  git checkout "$branch"
  git pull --ff-only origin "$branch"
else
  echo "SKIP_PULL=1, using existing server checkout."
fi

if [[ ! -f "$compose_file" ]]; then
  echo "Compose file not found: $compose_file" >&2
  exit 1
fi

echo "Building and starting containers..."
compose_cmd -f "$compose_file" up -d --build

echo "Container status:"
compose_cmd -f "$compose_file" ps

echo "Running health checks..."
wait_http "http://127.0.0.1:8081/health" "Python backend"
wait_http "http://127.0.0.1/" "Frontend"

echo
echo "Deployment complete."
echo "Frontend: http://${public_host}/"
echo "Gateway:  http://${public_host}:8080/"
REMOTE_SCRIPT
