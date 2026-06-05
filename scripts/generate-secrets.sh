#!/usr/bin/env bash
# Append generated secrets to .env (run once during install).
set -euo pipefail
echo "SESSION_SECRET=$(openssl rand -hex 32)"
echo "ADMIN_SECRET=$(openssl rand -hex 32)"
echo "INFERENCE_API_KEY=$(openssl rand -hex 24)"
