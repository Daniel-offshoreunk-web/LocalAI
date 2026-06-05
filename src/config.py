import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# pilot | production — controls documented defaults; see docs/REPLICATE.md §7
DEPLOY_PROFILE = os.environ.get("DEPLOY_PROFILE", "pilot").lower()
if DEPLOY_PROFILE not in {"pilot", "production"}:
    raise ValueError(f"Invalid DEPLOY_PROFILE={DEPLOY_PROFILE!r}; use pilot or production")

DB_PATH = Path(os.environ.get("ORCHESTRATOR_DB", ROOT / "orchestrator.db"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
DOCKER_NETWORK = os.environ.get("DOCKER_NETWORK", "gateway_net")
WORKSPACE_IMAGE = os.environ.get("WORKSPACE_IMAGE", "codercom/code-server:latest")
TOKEN_PREFIX = "sk-eps-"
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "")
GATEWAY_HOST = os.environ.get("GATEWAY_HOST", "0.0.0.0")
GATEWAY_PORT = int(os.environ.get("GATEWAY_PORT", "8000"))
ADMIN_HOST = os.environ.get("ADMIN_HOST", "127.0.0.1")
ADMIN_PORT = int(os.environ.get("ADMIN_PORT", "8888"))
SESSION_SECRET = os.environ.get(
    "SESSION_SECRET",
    "change-me-before-production-use-a-long-random-string",
)
WORKSPACE_PORT = int(os.environ.get("WORKSPACE_PORT", "8080"))
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
DEFAULT_CHAT_MODEL = os.environ.get("DEFAULT_CHAT_MODEL", "llama3.1:8b")
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
