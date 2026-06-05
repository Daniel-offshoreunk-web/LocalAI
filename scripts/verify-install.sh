#!/usr/bin/env bash
# Post-install smoke test. Run from repo root with services up.
set -euo pipefail

GATEWAY="${GATEWAY_URL:-http://127.0.0.1:8000}"
ADMIN="${ADMIN_URL:-http://127.0.0.1:8888}"

echo "==> Health"
curl -sf "${GATEWAY}/health" | grep -q healthy && echo "  gateway OK"

echo "==> Student portal"
code=$(curl -s -o /dev/null -w "%{http_code}" "${GATEWAY}/")
[[ "$code" == "200" ]] && echo "  portal OK ($code)"

echo "==> Admin (localhost)"
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  source .env 2>/dev/null || true
fi
if [[ -n "${ADMIN_SECRET:-}" ]]; then
  code=$(curl -s -o /dev/null -w "%{http_code}" -H "X-Admin-Secret: ${ADMIN_SECRET}" "${ADMIN}/")
  [[ "$code" == "200" ]] && echo "  admin OK ($code)" || echo "  admin returned $code (is admin service running?)"
else
  echo "  skip admin (set ADMIN_SECRET in .env)"
fi

echo "==> LocalAI inference"
INFERENCE="${INFERENCE_URL:-${OLLAMA_URL:-http://127.0.0.1:8080}}"
if curl -sf "${INFERENCE}/readyz" >/dev/null 2>&1; then
  echo "  localai readyz OK (${INFERENCE})"
elif curl -sf "${INFERENCE}/v1/models" >/dev/null 2>&1; then
  echo "  localai /v1/models OK (${INFERENCE})"
else
  echo "  inference unreachable at ${INFERENCE}"
  echo "  start LocalAI: docker run -p 8080:8080 localai/localai:latest-aio-cpu"
fi

echo "==> Docker"
docker info >/dev/null 2>&1 && echo "  docker OK"

echo "Done."
