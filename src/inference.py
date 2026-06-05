"""Shared inference path — all security checks run here once before upstream proxy.

Students and IDE extensions authenticate to *this* gateway (sessions / sk-eps- tokens).
After rate limits and prompt guard pass, requests are forwarded to LocalAI's
OpenAI-compatible API (/v1/chat/completions). The upstream API key stays server-side.
"""

import json
import logging

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from .config import DEFAULT_CHAT_MODEL, INFERENCE_API_KEY, INFERENCE_URL, RATE_LIMIT_CHAT_PER_MIN
from .db import get_db
from .rate_limit import client_ip, get_rate_limiter
from .safety import enforce_payload_safety
from .security import filter_proxy_headers, parse_bearer_token

logger = logging.getLogger(__name__)

# Client credentials must not leak to LocalAI — gateway auth is a separate layer.
_UPSTREAM_STRIP_AUTH = frozenset(
    {"authorization", "x-api-key", "xi-api-key", "cookie", "x-csrf-token"}
)


def _chat_completions_url() -> str:
    return f"{INFERENCE_URL}/v1/chat/completions"


def build_upstream_headers(client_headers: dict[str, str] | None = None) -> dict[str, str]:
    """Headers for LocalAI: hop-by-hop stripped, student auth replaced with server key."""
    filtered = filter_proxy_headers(client_headers or {})
    upstream = {
        k: v
        for k, v in filtered.items()
        if k.lower() not in _UPSTREAM_STRIP_AUTH
    }
    if INFERENCE_API_KEY:
        upstream["Authorization"] = f"Bearer {INFERENCE_API_KEY}"
    if "content-type" not in {k.lower() for k in upstream}:
        upstream["Content-Type"] = "application/json"
    return upstream


async def _resolve_token_row(token: str) -> dict:
    row = await get_db().get_by_api_token(token)
    if not row:
        raise HTTPException(status_code=401, detail="Invalid API token.")
    if row["status"] not in {"deployed", "approved"}:
        raise HTTPException(status_code=403, detail="Account not approved for AI access.")
    return row


async def enforce_inference_limits(request: Request, raw_body: bytes, *, row: dict) -> None:
    limiter = get_rate_limiter()
    ip_key = f"ip:{client_ip(request)}"
    user_key = f"user:{row['username']}"

    if not await limiter.allow(ip_key, limit=30, window_seconds=60.0):
        raise HTTPException(status_code=429, detail="Too many requests from this network.")
    if not await limiter.allow(
        user_key, limit=RATE_LIMIT_CHAT_PER_MIN, window_seconds=60.0
    ):
        raise HTTPException(status_code=429, detail="AI rate limit exceeded. Try again shortly.")

    await enforce_payload_safety(raw_body, username=row["username"])


async def proxy_chat_completions(
    request: Request,
    raw_body: bytes,
    *,
    token: str | None = None,
    row: dict | None = None,
) -> Response:
    """Proxy to LocalAI after gateway auth, rate limits, and prompt guard."""
    if row is None:
        if not token:
            token = parse_bearer_token(request.headers.get("authorization"))
        row = await _resolve_token_row(token)

    await enforce_inference_limits(request, raw_body, row=row)

    headers = build_upstream_headers(dict(request.headers))
    url = _chat_completions_url()

    wants_stream = False
    if request.headers.get("content-type", "").startswith("application/json"):
        try:
            payload = json.loads(raw_body)
            wants_stream = bool(payload.get("stream"))
        except (json.JSONDecodeError, TypeError):
            pass

    timeout = httpx.Timeout(120.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            if wants_stream:
                req = client.build_request(
                    "POST", url, headers=headers, content=raw_body
                )
                upstream = await client.send(req, stream=True)
                if upstream.status_code >= 400:
                    body = await upstream.aread()
                    await upstream.aclose()
                    return Response(
                        content=body,
                        status_code=upstream.status_code,
                        media_type=upstream.headers.get("content-type"),
                    )

                async def stream_body():
                    try:
                        async for chunk in upstream.aiter_bytes():
                            yield chunk
                    finally:
                        await upstream.aclose()

                return StreamingResponse(
                    stream_body(),
                    status_code=upstream.status_code,
                    media_type=upstream.headers.get(
                        "content-type", "text/event-stream"
                    ),
                )

            upstream = await client.post(url, headers=headers, content=raw_body)
            return Response(
                content=upstream.content,
                status_code=upstream.status_code,
                media_type=upstream.headers.get("content-type"),
            )
        except httpx.RequestError as exc:
            logger.warning("inference backend unreachable (%s): %s", INFERENCE_URL, exc)
            raise HTTPException(
                status_code=503, detail="Inference backend unreachable."
            ) from exc


async def complete_user_message(request: Request, message: str, *, row: dict) -> str:
    """Browser-safe chat helper — returns assistant text only."""
    payload = {
        "model": DEFAULT_CHAT_MODEL,
        "messages": [{"role": "user", "content": message}],
        "stream": False,
    }
    raw_body = json.dumps(payload).encode()
    await enforce_inference_limits(request, raw_body, row=row)

    headers = build_upstream_headers({"Content-Type": "application/json"})
    url = _chat_completions_url()
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        try:
            upstream = await client.post(url, headers=headers, content=raw_body)
        except httpx.RequestError as exc:
            logger.warning("inference backend unreachable (%s): %s", INFERENCE_URL, exc)
            raise HTTPException(
                status_code=503, detail="Inference backend unreachable."
            ) from exc

    if upstream.status_code >= 400:
        raise HTTPException(status_code=502, detail="AI request failed.")

    data = upstream.json()
    return (
        data.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "No response.")
    )
