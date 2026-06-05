#!/usr/bin/env bash
# One-command bootstrap: create .env if needed, then start the full stack.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FIRST_BOOT=0
if [[ ! -f .env ]]; then
  FIRST_BOOT=1
  echo "==> Creating .env from .env.example"
  cp .env.example .env
  chmod 600 .env
  ./scripts/generate-secrets.sh >> .env
  cat >> .env <<'EOF'
ALLOW_INSECURE_DEFAULTS=1
PUBLIC_BASE_URL=http://127.0.0.1:8000
SESSION_COOKIE_SECURE=0
WORKSPACE_IMAGE=eps-workspace:latest
WORKSPACE_GATEWAY_URL=http://gateway:8000
INFERENCE_URL=http://localai:8080
GUARDIAN_ENABLED=1
DOCKER_GID=${DOCKER_GID:-$(stat -c '%g' /var/run/docker.sock 2>/dev/null || echo 0)}
EOF
  echo "==> Wrote .env (dev defaults). Edit before production."
fi

# shellcheck disable=SC1091
source .env 2>/dev/null || true
export GATEWAY_PORT="${GATEWAY_PORT:-8000}"
export ADMIN_PORT="${ADMIN_PORT:-8888}"
export DOCKER_GID="${DOCKER_GID:-$(stat -c '%g' /var/run/docker.sock 2>/dev/null || getent group docker | cut -d: -f3 || echo 0)}"

"${ROOT}/scripts/free-ports.sh"

echo "==> Starting EPS Cloud Lab (LocalAI + gateway + admin + workspace image)"
docker compose up -d --build

echo ""
echo "Student portal:  http://127.0.0.1:${GATEWAY_PORT}"
echo "Admin panel:     http://127.0.0.1:${ADMIN_PORT}"
echo "Verify:          ./scripts/verify-install.sh"
echo ""
echo "Note: LocalAI may take several minutes on first boot while models preload."

if [[ "${FIRST_BOOT}" -eq 1 ]]; then
  echo ""
  echo "========================================================================"
  echo "  ADMIN CREDENTIALS — save securely; this block is shown once only"
  echo "========================================================================"
  echo "  X-Admin-Secret:  ${ADMIN_SECRET:-<unset>}"
  echo "  SESSION_SECRET:  ${SESSION_SECRET:-<unset>}"
  echo "  INFERENCE_API_KEY (LocalAI upstream): ${INFERENCE_API_KEY:-<unset>}"
  echo ""
  echo "  Example admin access:"
  echo "    curl -H \"X-Admin-Secret: ${ADMIN_SECRET}\" http://127.0.0.1:${ADMIN_PORT}/"
  echo "========================================================================"
fi
