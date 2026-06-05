import re
import secrets
from typing import Mapping

from fastapi import HTTPException, Request

from .config import ADMIN_SECRET, ADMIN_TRUST_DOCKER_BRIDGE, TOKEN_PREFIX

_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,30}[a-z0-9]$")
_CONTAINER_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$")

HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    }
)


def sanitize_username(raw: str) -> str:
    username = raw.strip().lower()
    if not _USERNAME_RE.fullmatch(username):
        raise HTTPException(
            status_code=400,
            detail="Username must be 3-32 chars: lowercase letters, digits, hyphen, underscore.",
        )
    return username


def container_name(username: str) -> str:
    name = f"eps-ws-{username}"
    if not _CONTAINER_NAME_RE.fullmatch(name):
        raise HTTPException(status_code=400, detail="Invalid workspace identity.")
    return name


def parse_bearer_token(authorization: str | None) -> str:
    """Extract and format-check a Bearer API token (DB lookup is separate)."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token.")
    token = authorization.removeprefix("Bearer ").strip()
    if not token.startswith(TOKEN_PREFIX) or len(token) < len(TOKEN_PREFIX) + 16:
        raise HTTPException(status_code=401, detail="Invalid API token.")
    body = token[len(TOKEN_PREFIX) :]
    if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", body):
        raise HTTPException(status_code=401, detail="Malformed API token.")
    return token


def validate_proxy_path(path: str) -> str:
    """Reject path traversal before forwarding to a student workspace container."""
    if not path:
        return ""
    if "\x00" in path or ".." in path or path.startswith(("/", "\\")):
        raise HTTPException(status_code=400, detail="Invalid path.")
    return path.lstrip("/")


def sanitize_display_name(raw: str) -> str | None:
    name = raw.strip()[:64]
    if not name:
        return None
    if not re.fullmatch(r"[\w .'-]{1,64}", name, re.UNICODE):
        raise HTTPException(status_code=400, detail="Invalid display name.")
    return name


def filter_proxy_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {
        k: v
        for k, v in headers.items()
        if k.lower() not in HOP_BY_HOP
    }


def is_localhost(host: str | None) -> bool:
    if not host:
        return False
    bare = host.split("%", 1)[0]
    if bare in {"127.0.0.1", "localhost", "::1", "[::1]"}:
        return True
    if bare.startswith("127."):
        return True
    return False


def is_docker_bridge(host: str | None) -> bool:
    if not host or not ADMIN_TRUST_DOCKER_BRIDGE:
        return False
    bare = host.split("%", 1)[0]
    if bare.startswith("172.") or bare.startswith("10."):
        return True
    return bare.startswith("192.168.")

def is_trusted_admin_client(host: str | None) -> bool:
    return is_localhost(host) or is_docker_bridge(host)


def require_localhost(request: Request) -> None:
    client = request.client
    if client is None or not is_trusted_admin_client(client.host):
        raise HTTPException(status_code=403, detail="Admin access is localhost-only.")


def require_admin_secret(request: Request) -> None:
    require_localhost(request)
    if not ADMIN_SECRET:
        return
    provided = request.headers.get("x-admin-secret", "")
    if not secrets.compare_digest(provided, ADMIN_SECRET):
        raise HTTPException(status_code=401, detail="Invalid admin credentials.")


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)
