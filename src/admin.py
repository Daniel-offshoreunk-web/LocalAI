import logging
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from .admin_auth import (
    MIN_ADMIN_SECRET_LEN,
    admin_secret_valid_length,
    attempt_admin_login,
    clear_admin_session,
    ensure_admin_access,
    is_admin_session,
    is_ip_blocked,
    redirect_if_unauthenticated,
)
from .auth_store import generate_api_token
from .config import (
    ADMIN_SECRET,
    ALLOW_INSECURE_DEFAULTS,
    SESSION_COOKIE_SECURE,
    SESSION_SECRET,
)
from .db import get_db
from .orchestrator import get_orchestrator
from .security import require_localhost, sanitize_username
from .sessions import ensure_csrf_token, verify_form_csrf

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="EPS Admin Control Panel", docs_url=None, redoc_url=None)

app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    session_cookie="eps_admin_session",
    max_age=60 * 60 * 4,
    same_site="strict",
    https_only=SESSION_COOKIE_SECURE,
)


@app.middleware("http")
async def localhost_only(request: Request, call_next):
    require_localhost(request)
    return await call_next(request)


@app.on_event("startup")
async def startup() -> None:
    if not ADMIN_SECRET and not ALLOW_INSECURE_DEFAULTS:
        raise RuntimeError(
            "Set ADMIN_SECRET before running the admin panel in production."
        )
    if ADMIN_SECRET and not admin_secret_valid_length():
        raise RuntimeError(
            f"ADMIN_SECRET must be at least {MIN_ADMIN_SECRET_LEN} characters."
        )
    await get_db()


@app.get("/login", response_model=None)
async def login_page(request: Request) -> HTMLResponse | RedirectResponse:
    if is_admin_session(request):
        return RedirectResponse(url="/", status_code=303)
    blocked = await is_ip_blocked(request)
    return templates.TemplateResponse(
        request,
        "admin_login.html",
        {
            "error": None,
            "blocked": blocked,
            "csrf_token": ensure_csrf_token(request),
            "min_key_len": MIN_ADMIN_SECRET_LEN,
        },
    )


@app.post("/login", response_model=None)
async def login_submit(
    request: Request,
    admin_key: str = Form(...),
    csrf_token: str = Form(""),
) -> HTMLResponse | RedirectResponse:
    verify_form_csrf(request, csrf_token)
    if is_admin_session(request):
        return RedirectResponse(url="/", status_code=303)

    error = await attempt_admin_login(request, admin_key)
    if error is None:
        return RedirectResponse(url="/", status_code=303)

    blocked = await is_ip_blocked(request)
    return templates.TemplateResponse(
        request,
        "admin_login.html",
        {
            "error": error,
            "blocked": blocked,
            "csrf_token": ensure_csrf_token(request),
            "min_key_len": MIN_ADMIN_SECRET_LEN,
        },
        status_code=403 if blocked else 401,
    )


@app.post("/logout")
async def logout(request: Request, csrf_token: str = Form("")) -> RedirectResponse:
    verify_form_csrf(request, csrf_token)
    clear_admin_session(request)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/", response_model=None)
async def dashboard(request: Request) -> HTMLResponse | RedirectResponse:
    redirect = await redirect_if_unauthenticated(request)
    if redirect is not None:
        return redirect

    db = await get_db()
    pending = await db.list_by_status("pending")
    approved = await db.list_by_status("approved")
    recent = await db.list_recent(50)
    alerts = await db.list_security_events(30)
    blocked_ips = await db.list_blocked_admin_ips()
    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        {
            "pending": pending,
            "approved": approved,
            "recent": recent,
            "alerts": alerts,
            "blocked_ips": blocked_ips,
            "csrf_token": ensure_csrf_token(request),
        },
    )


@app.post("/approve/{reg_id}")
async def approve_registration(
    reg_id: int,
    request: Request,
    csrf_token: str = Form(""),
) -> RedirectResponse:
    await ensure_admin_access(request)
    verify_form_csrf(request, csrf_token)
    db = await get_db()
    row = await db.get_by_id(reg_id)
    if not row:
        raise HTTPException(status_code=404, detail="Registration not found.")
    if row["status"] not in {"pending", "approved", "failed"}:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot deploy while status is {row['status']}.",
        )

    username = sanitize_username(row["username"])
    api_token = row.get("api_token")
    if not api_token:
        api_token = generate_api_token()
        await db.set_api_token(reg_id, api_token)

    await db.set_status(reg_id, "approved")
    orchestrator = get_orchestrator()
    try:
        result = await orchestrator.deploy_workspace(username, api_token=api_token)
        await db.set_status(
            reg_id,
            "deployed",
            container_name=result["container_name"],
        )
    except HTTPException as exc:
        await db.set_status(
            reg_id,
            "failed",
            error_message=str(exc.detail),
        )
        raise
    except Exception as exc:
        logger.exception("deploy failed for %s", username)
        await db.set_status(reg_id, "failed", error_message=str(exc))
        raise HTTPException(status_code=503, detail="Deployment failed.") from exc

    return RedirectResponse(url="/", status_code=303)


@app.post("/deny/{reg_id}")
async def deny_registration(
    reg_id: int,
    request: Request,
    csrf_token: str = Form(""),
) -> RedirectResponse:
    await ensure_admin_access(request)
    verify_form_csrf(request, csrf_token)
    db = await get_db()
    row = await db.get_by_id(reg_id)
    if not row:
        raise HTTPException(status_code=404, detail="Registration not found.")
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail="Only pending rows can be denied.")
    reason = "Denied by administrator"
    await db.set_status(reg_id, "denied", error_message=reason)
    return RedirectResponse(url="/", status_code=303)


@app.post("/stop/{reg_id}")
async def stop_workspace(
    reg_id: int,
    request: Request,
    csrf_token: str = Form(""),
) -> RedirectResponse:
    await ensure_admin_access(request)
    verify_form_csrf(request, csrf_token)
    db = await get_db()
    row = await db.get_by_id(reg_id)
    if not row:
        raise HTTPException(status_code=404, detail="Registration not found.")
    username = sanitize_username(row["username"])
    await get_orchestrator().stop_workspace(username)
    return RedirectResponse(url="/", status_code=303)


@app.post("/unblock-ip")
async def unblock_ip(
    request: Request,
    ip: str = Form(...),
    csrf_token: str = Form(""),
) -> RedirectResponse:
    await ensure_admin_access(request)
    verify_form_csrf(request, csrf_token)
    clean = ip.strip()
    if not clean:
        raise HTTPException(status_code=400, detail="IP address required.")
    db = await get_db()
    if await db.unblock_admin_ip(clean):
        await db.record_security_event(None, "admin_ip_unblocked", clean)
    return RedirectResponse(url="/", status_code=303)
