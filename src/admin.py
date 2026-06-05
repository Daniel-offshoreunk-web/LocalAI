import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .auth_store import generate_api_token
from .config import ADMIN_SECRET, ALLOW_INSECURE_DEFAULTS
from .db import get_db
from .orchestrator import get_orchestrator
from .security import require_admin_secret, sanitize_username

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="EPS Admin Control Panel", docs_url=None, redoc_url=None)


@app.middleware("http")
async def localhost_only(request: Request, call_next):
    from .security import require_localhost

    require_localhost(request)
    return await call_next(request)


@app.on_event("startup")
async def startup() -> None:
    if not ADMIN_SECRET and not ALLOW_INSECURE_DEFAULTS:
        raise RuntimeError(
            "Set ADMIN_SECRET before running the admin panel in production."
        )
    await get_db()


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    require_admin_secret(request)
    db = await get_db()
    pending = await db.list_by_status("pending")
    approved = await db.list_by_status("approved")
    recent = await db.list_recent(50)
    alerts = await db.list_security_events(30)
    return templates.TemplateResponse(
        request,
        "admin_dashboard.html",
        {
            "pending": pending,
            "approved": approved,
            "recent": recent,
            "alerts": alerts,
        },
    )


class DenyBody(BaseModel):
    reason: str | None = None


@app.post("/approve/{reg_id}")
async def approve_registration(reg_id: int, request: Request) -> RedirectResponse:
    require_admin_secret(request)
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
    reg_id: int, request: Request, body: DenyBody | None = None
) -> RedirectResponse:
    require_admin_secret(request)
    db = await get_db()
    row = await db.get_by_id(reg_id)
    if not row:
        raise HTTPException(status_code=404, detail="Registration not found.")
    if row["status"] != "pending":
        raise HTTPException(status_code=409, detail="Only pending rows can be denied.")
    reason = (body.reason if body and body.reason else "Denied by administrator")[:500]
    await db.set_status(reg_id, "denied", error_message=reason)
    return RedirectResponse(url="/", status_code=303)


@app.post("/stop/{reg_id}")
async def stop_workspace(reg_id: int, request: Request) -> RedirectResponse:
    require_admin_secret(request)
    db = await get_db()
    row = await db.get_by_id(reg_id)
    if not row:
        raise HTTPException(status_code=404, detail="Registration not found.")
    username = sanitize_username(row["username"])
    await get_orchestrator().stop_workspace(username)
    return RedirectResponse(url="/", status_code=303)
