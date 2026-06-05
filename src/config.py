import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# pilot | production — controls documented defaults; see docs/REPLICATE.md §7
DEPLOY_PROFILE = os.environ.get("DEPLOY_PROFILE", "pilot").lower()
if DEPLOY_PROFILE not in {"pilot", "production"}:
    raise ValueError(f"Invalid DEPLOY_PROFILE={DEPLOY_PROFILE!r}; use pilot or production")

DB_PATH = Path(os.environ.get("ORCHESTRATOR_DB", ROOT / "orchestrator.db"))
# OpenAI-compatible inference backend — LocalAI (default :8080) or any /v1 peer.
# OLLAMA_URL is kept for older .env files; INFERENCE_URL wins when both are set.
INFERENCE_URL = (
    os.environ.get("INFERENCE_URL")
    or os.environ.get("OLLAMA_URL")
    or "http://127.0.0.1:8080"
).rstrip("/")
# Server-side key for upstream LocalAI (LOCALAI_API_KEY alias). Never shown to students.
INFERENCE_API_KEY = os.environ.get("INFERENCE_API_KEY") or os.environ.get(
    "LOCALAI_API_KEY", ""
)
# Deprecated alias — use INFERENCE_URL in new deployments.
OLLAMA_URL = INFERENCE_URL
DOCKER_NETWORK = os.environ.get("DOCKER_NETWORK", "gateway_net")
WORKSPACE_IMAGE = os.environ.get("WORKSPACE_IMAGE", "eps-workspace:latest")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
# URL reachable from workspace containers (Continue calls the gateway from the IDE host).
WORKSPACE_GATEWAY_URL = (
    os.environ.get("WORKSPACE_GATEWAY_URL")
    or PUBLIC_BASE_URL
    or "http://gateway:8000"
).rstrip("/")
TOKEN_PREFIX = "sk-eps-"
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "")
GATEWAY_HOST = os.environ.get("GATEWAY_HOST", "0.0.0.0")
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "8000"))
ADMIN_HOST = os.environ.get("ADMIN_HOST", "127.0.0.1")
ADMIN_PORT = int(os.environ.get("ADMIN_PORT", "8888"))
# Compose publishes admin on 127.0.0.1; container sees the docker bridge IP.
ADMIN_TRUST_DOCKER_BRIDGE = os.environ.get("ADMIN_TRUST_DOCKER_BRIDGE", "0") == "1"
SESSION_SECRET = os.environ.get(
    "SESSION_SECRET",
    "change-me-before-production-use-a-long-random-string",
)
WORKSPACE_PORT = int(os.environ.get("WORKSPACE_PORT", "8080"))
DEFAULT_CHAT_MODEL = os.environ.get(
    "DEFAULT_CHAT_MODEL", "llama-3.2-3b-instruct:q4_k_m"
)
# Small-model guardian (>=1B) reviews student text after regex/AST scanners.
GUARDIAN_ENABLED = os.environ.get("GUARDIAN_ENABLED", "1") == "1"
GUARDIAN_MODEL = os.environ.get(
    "GUARDIAN_MODEL", "llama-3.2-1b-instruct:q4_k_m"
)
GUARDIAN_TIMEOUT = float(os.environ.get("GUARDIAN_TIMEOUT", "20"))
GUARDIAN_MAX_CHARS = int(os.environ.get("GUARDIAN_MAX_CHARS", "6000"))
# When 1, allow requests through if the guardian model is unreachable.
GUARDIAN_FAIL_OPEN = os.environ.get("GUARDIAN_FAIL_OPEN", "1") == "1"
MAX_REQUEST_BODY_BYTES = int(os.environ.get("MAX_REQUEST_BODY_BYTES", str(1024 * 1024)))
RATE_LIMIT_CHAT_PER_MIN = int(os.environ.get("RATE_LIMIT_CHAT_PER_MIN", "20"))
RATE_LIMIT_LOGIN_WINDOW = int(os.environ.get("RATE_LIMIT_LOGIN_WINDOW", "10"))
RATE_LIMIT_REGISTER_PER_HOUR = int(os.environ.get("RATE_LIMIT_REGISTER_PER_HOUR", "5"))
# Set ALLOW_INSECURE_DEFAULTS=1 only on local dev machines.
ALLOW_INSECURE_DEFAULTS = os.environ.get("ALLOW_INSECURE_DEFAULTS", "0") == "1"
# Anonymous API registration is off by default (use web signup).
DISABLE_API_REGISTER = os.environ.get("DISABLE_API_REGISTER", "1") == "1"
SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "0") == "1"
_DEFAULT_SESSION = "change-me-before-production-use-a-long-random-string"
INSECURE_SESSION_SECRET = SESSION_SECRET == _DEFAULT_SESSION
