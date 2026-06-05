#!/bin/bash
# Writes ~/.continue/config.yaml from deploy-time env, then starts code-server.
set -euo pipefail

: "${EPS_GATEWAY_URL:?EPS_GATEWAY_URL is required}"
: "${EPS_API_TOKEN:?EPS_API_TOKEN is required}"

MODEL="${EPS_CHAT_MODEL:-llama-3.2-3b-instruct:q4_k_m}"
TEMPLATE="/etc/eps/continue/config.yaml.template"
CONFIG_DIR="/home/coder/.continue"
CONFIG="${CONFIG_DIR}/config.yaml"

mkdir -p "${CONFIG_DIR}"
sed \
  -e "s|__GATEWAY_URL__|${EPS_GATEWAY_URL}|g" \
  -e "s|__API_KEY__|${EPS_API_TOKEN}|g" \
  -e "s|__CHAT_MODEL__|${MODEL}|g" \
  "${TEMPLATE}" > "${CONFIG}"
chmod 600 "${CONFIG}"

exec /usr/bin/code-server --auth none --bind-addr 0.0.0.0:8080 "$@"
