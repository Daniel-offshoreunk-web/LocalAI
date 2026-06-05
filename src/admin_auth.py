"""Browser-friendly admin authentication (session cookie + optional header)."""

import secrets

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from .config import ADMIN_SECRET, ALLOW_INSECURE_DEFAULTS
from .db import get_db
from .rate_limit import client_ip
from .security import new_csrf_token, require_localhost
from .sessions import ensure_csrf_token, verify_form_csrf

ADMIN_SESSION_KEY = "admin_auth"
MIN_ADMIN_SECRET_LEN = 16


def admin_secret_configured() -> bool:
    return bool(ADMIN_SECRET)


def admin_secret_valid_length() -> bool:
    return len(ADMIN_SECRET) >= MIN_ADMIN_SECRET_LEN


def is_admin_session(request: Request) -> bool:
    return request.session.get(ADMIN_SESSION_KEY) is True


def establish_admin_session(request: Request) -> None:
    request.session.clear()
    request.session[ADMIN_SESSION_KEY] = True
    request.session["csrf_token"] = new_csrf_token()


def clear_admin_session(request: Request) -> None:
    request.session.clear()


def header_matches_admin_secret(request: Request) -> bool:
    if not ADMIN_SECRET:
        return False
    provided = request.headers.get("x-admin-secret", "")
    return secrets.compare_digest(provided, ADMIN_SECRET)


async def is_ip_blocked(request: Request) -> bool:
    db = await get_db()
    return await db.is_admin_ip_blocked(client_ip(request))


async def ensure_admin_access(request: Request) -> None:
    """Raise if the client may not use admin actions."""
    require_localhost(request)
    ip = client_ip(request)

    if not admin_secret_configured():
        if ALLOW_INSECURE_DEFAULTS:
            return
        raise HTTPException(
            status_code=503,
            detail="Admin panel is not configured (set ADMIN_SECRET).",
        )

    db = await get_db()
    if await db.is_admin_ip_blocked(ip) and not is_admin_session(request):
        raise HTTPException(
            status_code=403,
            detail="This address is permanently blocked after a failed login. "
            "Ask another administrator to unblock it.",
        )

    if is_admin_session(request) or header_matches_admin_secret(request):
        return

    raise HTTPException(status_code=401, detail="Admin sign-in required.")


async def redirect_if_unauthenticated(request: Request) -> RedirectResponse | None:
    try:
        await ensure_admin_access(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return RedirectResponse(url="/login", status_code=303)
        raise
    return None


def validate_submitted_admin_key(key: str) -> str | None:
    """Return an error message if the submitted key is invalid."""
    cleaned = key.strip()
    if len(cleaned) < MIN_ADMIN_SECRET_LEN:
        return f"Admin key must be at least {MIN_ADMIN_SECRET_LEN} characters."
    return None


async def attempt_admin_login(request: Request, submitted_key: str) -> str | None:
    """
    Verify admin key. Return None on success, or an error message for the login form.
    Permanently blocks the client IP after one failed attempt.
    """
    require_localhost(request)
    ip = client_ip(request)
    db = await get_db()

    if await db.is_admin_ip_blocked(ip):
        return (
            "This address is permanently blocked after a failed login. "
            "Ask another administrator to unblock it."
        )

    if not admin_secret_configured():
        if ALLOW_INSECURE_DEFAULTS:
            establish_admin_session(request)
            return None
        return "Admin panel is not configured."

    key_error = validate_submitted_admin_key(submitted_key)
    if key_error:
        await _block_failed_login(db, ip, key_error)
        return (
            "Incorrect admin key. This address is now permanently blocked. "
            "Ask another administrator to unblock it."
        )

    if not secrets.compare_digest(submitted_key.strip(), ADMIN_SECRET):
        await _block_failed_login(db, ip, "Invalid admin key")
        return (
            "Incorrect admin key. This address is now permanently blocked. "
            "Ask another administrator to unblock it."
        )

    establish_admin_session(request)
    await db.record_security_event(None, "admin_login_ok", ip)
    return None


async def _block_failed_login(db, ip: str, detail: str) -> None:
    await db.block_admin_ip(ip, detail[:500])
    await db.record_security_event(None, "admin_login_failed", ip)
