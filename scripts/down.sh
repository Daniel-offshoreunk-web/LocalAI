#!/usr/bin/env bash
# Stop the EPS Cloud Lab stack and student workspace containers.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

REMOVE_VOLUMES=0

usage() {
  cat <<'EOF'
Usage: ./scripts/down.sh [OPTIONS]

Stop the compose stack (LocalAI, gateway, admin) and any running eps-ws-* workspaces.

Options:
  --volumes, -v   Also remove compose volumes (orchestrator DB, LocalAI models).
                  Destructive — only use when resetting the lab.
  -h, --help      Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --volumes | -v)
      REMOVE_VOLUMES=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

# shellcheck disable=SC1091
source .env 2>/dev/null || true
export GATEWAY_PORT="${GATEWAY_PORT:-8000}"
export ADMIN_PORT="${ADMIN_PORT:-8888}"

stop_workspaces() {
  local cid name
  while IFS= read -r cid; do
    [[ -z "${cid}" ]] && continue
    name="$(docker inspect -f '{{.Name}}' "${cid}" 2>/dev/null | sed 's#^/##')"
    echo "==> Stopping ${name:-${cid}}"
    docker stop "${cid}" >/dev/null || true
  done < <(docker ps -q --filter "name=eps-ws-" 2>/dev/null || true)
}

if docker ps -q --filter "name=eps-ws-" 2>/dev/null | grep -q .; then
  echo "==> Stopping student workspaces"
  stop_workspaces
else
  echo "==> No running student workspaces"
fi

if docker compose ps -q 2>/dev/null | grep -q .; then
  echo "==> Stopping EPS Cloud Lab compose stack"
  if [[ "${REMOVE_VOLUMES}" -eq 1 ]]; then
    docker compose down --remove-orphans -v
    echo "==> Removed compose volumes (eps-data, localai-models)"
  else
    docker compose down --remove-orphans
  fi
else
  echo "==> Compose stack is not running"
  if [[ "${REMOVE_VOLUMES}" -eq 1 ]]; then
    docker compose down --remove-orphans -v >/dev/null 2>&1 || true
  fi
fi

echo ""
echo "EPS Cloud Lab stopped."
echo "Start again:     ./scripts/up.sh"
if [[ "${REMOVE_VOLUMES}" -eq 0 ]]; then
  echo "Data preserved:  orchestrator DB and LocalAI models volumes kept."
fi
