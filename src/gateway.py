"""Public gateway (port 8000): student portal, inference proxy, health."""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from .config import (
    ALLOW_INSECURE_DEFAULTS,
    DISABLE_API_REGISTER,
    INSECURE_SESSION_SECRET,
    SESSION_COOKIE_SECURE,
    SESSION_SECRET,
)
from .db import get_db
from .http_middleware import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from .inference import proxy_chat_completions
from .rate_limit import client_ip, get_rate_limiter
from .security import sanitize_username
from .student import router as student_router

logger = logging.getLogger(__name__)

app = FastAPI(title="EPS Secure Gateway", docs_url=None, redoc_url=None)

# Order: last added runs first — sessions must run before our headers middleware.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="eps_session",
    max_age=60 * 60 * 8,
    same_site="lax",
    https_only=SESSION_COOKIE_SECURE,
)

app.include_router(student_router)


@app.on_event("startup")
async def startup() -> None:
    if INSECURE_SESSION_SECRET and not ALLOW_INSECURE_DEFAULTS:
        raise RuntimeError(
            "Refusing to start: set SESSION_SECRET env var before production use."
        )
    await get_db()
    logger.info("gateway startup complete (insecure_defaults=%s)", ALLOW_INSECURE_DEFAULTS)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "gateway": "operational"}


class RegisterBody(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)


@app.post("/v1/register")
async def register_workspace(request: Request, body: RegisterBody) -> JSONResponse:
    """Machine-facing registration — disabled by default; use the web signup."""
    if DISABLE_API_REGISTER:
        raise HTTPException(status_code=404, detail="Not found.")

    limiter = get_rate_limiter()
    if not await limiter.allow(
        f"register:{client_ip(request)}", limit=5, window_seconds=3600.0
    ):
        raise HTTPException(status_code=429, detail="Too many registration attempts.")

    username = sanitize_username(body.username)
    db = await get_db()
    existing = await db.get_by_username(username)
    if existing:
        status = existing["status"]
        if status in {"pending", "approved"}:
            return JSONResponse(
                status_code=202,
                content={
                    "username": username,
                    "status": status,
                    "message": "Registration already queued for admin approval.",
                },
            )
        if status == "deployed":
            raise HTTPException(
                status_code=409,
                detail="Workspace already provisioned for this user.",
            )
    row = await db.enqueue_registration(username)
    return JSONResponse(
        status_code=202,
        content={
            "id": row["id"],
            "username": username,
            "status": row["status"],
            "message": "Registration pending. An administrator must approve deployment.",
        },
    )


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    raw_body = await request.body()
    return await proxy_chat_completions(request, raw_body)
