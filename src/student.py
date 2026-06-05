"""Browser-facing student routes (signup, dashboard, cloud IDE proxy)."""

import logging
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .auth_store import generate_api_token, hash_password
from .config import RATE_LIMIT_LOGIN_WINDOW
from .db import get_db
from .inference import complete_user_message
from .orchestrator import get_orchestrator
from .rate_limit import client_ip, get_rate_limiter
from .security import sanitize_display_name, sanitize_username, validate_proxy_path
from .sessions import (
    ensure_csrf_token,
    get_session_username,
    login_user,
    logout_user,
    require_session_username,
    verify_form_csrf,
)
from .workspace_proxy import proxy_http, proxy_websocket

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

router = APIRouter()


def _page(request: Request, row: dict | None, **extra) -> dict:
    return {
        "request": request,
        "user": row,
        "logged_in": row is not None,
        "status": row["status"] if row else None,
        "csrf_token": ensure_csrf_token(request),
        **extra,
    }


@router.get("/", response_model=None)
async def home(request: Request):
    username = get_session_username(request)
    if username:
        return RedirectResponse(url="/dashboard", status_code=302)
    return templates.TemplateResponse(
        request,
        "student_home.html",
        _page(request, None, error=None, mode="login"),
    )


@router.post("/signup", response_model=None)
async def signup(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    display_name: str = Form(""),
    csrf_token: str = Form(""),
):
    verify_form_csrf(request, csrf_token)

    limiter = get_rate_limiter()
    if not await limiter.allow(
        f"signup:{client_ip(request)}", limit=5, window_seconds=3600.0
    ):
        return templates.TemplateResponse(
            request,
            "student_home.html",
            _page(request, None, error="Too many sign-up attempts. Try later.", mode="signup"),
            status_code=429,
        )

    if password != password_confirm:
        return templates.TemplateResponse(
            request,
            "student_home.html",
            _page(request, None, error="Passwords do not match.", mode="signup"),
            status_code=400,
        )
    try:
        clean = sanitize_username(username)
        pwd_hash = hash_password(password)
        name = sanitize_display_name(display_name)
    except (HTTPException, ValueError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
        return templates.TemplateResponse(
            request,
            "student_home.html",
            _page(request, None, error=detail, mode="signup"),
            status_code=400,
        )

    db = await get_db()
    existing = await db.get_by_username(clean)
    if existing and existing["status"] not in {"denied"}:
        if existing.get("password_hash"):
            return templates.TemplateResponse(
                request,
                "student_home.html",
                _page(request, None, error="That username is already taken.", mode="signup"),
                status_code=409,
            )

    token = generate_api_token()
    await db.create_student_account(clean, pwd_hash, token, name)
    login_user(request, clean)
    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/login", response_model=None)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(""),
):
    verify_form_csrf(request, csrf_token)

    limiter = get_rate_limiter()
    if not await limiter.allow(
        f"login:{client_ip(request)}",
        limit=RATE_LIMIT_LOGIN_WINDOW,
        window_seconds=900.0,
    ):
        return templates.TemplateResponse(
            request,
            "student_home.html",
            _page(request, None, error="Too many login attempts. Wait 15 minutes.", mode="login"),
            status_code=429,
        )

    try:
        clean = sanitize_username(username)
    except HTTPException as exc:
        return templates.TemplateResponse(
            request,
            "student_home.html",
            _page(request, None, error=exc.detail, mode="login"),
            status_code=400,
        )

    db = await get_db()
    row = await db.verify_login(clean, password)
    if not row:
        await db.record_security_event(clean, "login_failed", client_ip(request))
        return templates.TemplateResponse(
            request,
            "student_home.html",
            _page(request, None, error="Invalid username or password.", mode="login"),
            status_code=401,
        )
    login_user(request, clean)
    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/logout")
async def logout(request: Request, csrf_token: str = Form("")) -> RedirectResponse:
    verify_form_csrf(request, csrf_token)
    logout_user(request)
    return RedirectResponse(url="/", status_code=303)


@router.get("/dashboard", response_model=None)
async def dashboard(request: Request):
    username = require_session_username(request)
    row = await get_db().get_by_username(username)
    if not row:
        logout_user(request)
        return RedirectResponse(url="/", status_code=303)
    return templates.TemplateResponse(
        request,
        "student_dashboard.html",
        _page(request, row),
    )


class AiChatBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)


@router.post("/app/ai/chat")
async def student_ai_chat(request: Request, body: AiChatBody) -> JSONResponse:
    header_csrf = request.headers.get("x-csrf-token")
    verify_form_csrf(request, header_csrf)
    username = require_session_username(request)
    row = await get_db().get_by_username(username)
    if not row or row["status"] != "deployed":
        raise HTTPException(
            status_code=403,
            detail="Your cloud lab must be approved before using the AI assistant.",
        )

    reply = await complete_user_message(request, body.message, row=row)
    return JSONResponse({"reply": reply})


async def _require_deployed_lab(request: Request) -> str:
    username = require_session_username(request)
    row = await get_db().get_by_username(username)
    if not row or row["status"] != "deployed":
        raise HTTPException(
            status_code=403,
            detail="Your cloud lab is not ready yet. Check the dashboard.",
        )
    await get_orchestrator().ensure_running(username)
    return username


@router.api_route(
    "/lab",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
@router.api_route(
    "/lab/",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
@router.api_route(
    "/lab/{path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
)
async def lab_http(request: Request, path: str = ""):
    username = await _require_deployed_lab(request)
    safe_path = validate_proxy_path(path)
    return await proxy_http(request, username, safe_path)


@router.websocket("/lab")
@router.websocket("/lab/")
@router.websocket("/lab/{path:path}")
async def lab_websocket(websocket: WebSocket, path: str = "") -> None:
    session = websocket.scope.get("session") or {}
    username = session.get("username")
    if not username:
        await websocket.close(code=4401)
        return
    row = await get_db().get_by_username(username)
    if not row or row["status"] != "deployed":
        await websocket.close(code=4403)
        return
    safe_path = validate_proxy_path(path)
    await proxy_websocket(websocket, username, safe_path)
