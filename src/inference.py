"""Shared Ollama inference path — all security checks run here once."""

import json
import logging

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from .config import OLLAMA_URL, RATE_LIMIT_CHAT_PER_MIN
from .db import get_db
from .prompt_guard import scan_chat_payload
from .rate_limit import client_ip, get_rate_limiter
from .security import filter_proxy_headers, parse_bearer_token

logger = logging.getLogger(__name__)


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

    violations = scan_chat_payload(raw_body)
    if violations:
        await get_db().record_security_event(
            row["username"],
            "prompt_blocked",
            ",".join(violations[:5])[:240],
        )
        raise HTTPException(status_code=400, detail="Request blocked by safety policy.")


async def proxy_chat_completions(
    request: Request,
    raw_body: bytes,
    *,
    token: str | None = None,
    row: dict | None = None,
) -> Response:
    """Proxy to Ollama after auth, rate limits, and prompt guard."""
    if row is None:
        if not token:
            token = parse_bearer_token(request.headers.get("authorization"))
        row = await _resolve_token_row(token)

    await enforce_inference_limits(request, raw_body, row=row)

    headers = filter_proxy_headers(request.headers)
    url = f"{OLLAMA_URL}/v1/chat/completions"

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
            logger.warning("ollama unreachable: %s", exc)
            raise HTTPException(
                status_code=503, detail="Inference backend unreachable."
            ) from exc


async def complete_user_message(request: Request, message: str, *, row: dict) -> str:
    """Browser-safe chat helper — returns assistant text only."""
    payload = {
        "model": row.get("model") or None,
        "messages": [{"role": "user", "content": message}],
        "stream": False,
    }
    from .config import DEFAULT_CHAT_MODEL

    payload["model"] = DEFAULT_CHAT_MODEL
    raw_body = json.dumps(payload).encode()
    await enforce_inference_limits(request, raw_body, row=row)

    headers = filter_proxy_headers({"Content-Type": "application/json"})
    url = f"{OLLAMA_URL}/v1/chat/completions"
    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        try:
            upstream = await client.post(url, headers=headers, content=raw_body)
        except httpx.RequestError as exc:
            logger.warning("ollama unreachable: %s", exc)
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
