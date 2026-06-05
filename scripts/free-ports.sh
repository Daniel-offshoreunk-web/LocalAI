#!/usr/bin/env bash
# Stop Docker containers publishing the given host ports (best-effort).
set -euo pipefail

free_port() {
  local port="$1"
  local cid name

  while IFS= read -r cid; do
    [[ -z "${cid}" ]] && continue
    name="$(docker inspect -f '{{.Name}}' "${cid}" 2>/dev/null | sed 's#^/##')"
    echo "==> Stopping ${name:-${cid}} (held port ${port})"
    docker stop "${cid}" >/dev/null || true
  done < <(docker ps -q --filter "publish=${port}" 2>/dev/null || true)
}

GATEWAY_PORT="${GATEWAY_PORT:-8000}"
ADMIN_PORT="${ADMIN_PORT:-8888}"

echo "==> Freeing ports ${GATEWAY_PORT} and ${ADMIN_PORT}"
free_port "${GATEWAY_PORT}"
free_port "${ADMIN_PORT}"

# Recycle a previous compose deployment of this project.
if docker compose ps -q 2>/dev/null | grep -q .; then
  echo "==> Stopping previous EPS Cloud Lab compose stack"
  docker compose down --remove-orphans >/dev/null 2>&1 || true
fi
