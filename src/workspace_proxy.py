import asyncio
import logging
from typing import AsyncIterator

import httpx
import websockets
from fastapi import Request, WebSocket, WebSocketDisconnect
from starlette.responses import Response, StreamingResponse

from .config import WORKSPACE_PORT
from .security import container_name, filter_proxy_headers, validate_proxy_path

logger = logging.getLogger(__name__)

_WS_SKIP_HEADERS = frozenset(
    {"host", "connection", "upgrade", "sec-websocket-key", "sec-websocket-version"}
)


def upstream_http(username: str, path: str = "") -> str:
    base = container_name(username)
    suffix = path.lstrip("/")
    url = f"http://{base}:{WORKSPACE_PORT}/"
    if suffix:
        url = f"{url}{suffix}"
    return url


def upstream_ws(username: str, path: str = "") -> str:
    http_url = upstream_http(username, path)
    return "ws" + http_url[4:]


async def proxy_http(
    request: Request, username: str, path: str = ""
) -> Response:
    path = validate_proxy_path(path)
    url = upstream_http(username, path)
    if request.url.query:
        url = f"{url}?{request.url.query}"

    headers = filter_proxy_headers(request.headers)
    body = await request.body()
    timeout = httpx.Timeout(120.0, connect=15.0)

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        try:
            upstream = await client.request(
                request.method,
                url,
                headers=headers,
                content=body if body else None,
            )
        except httpx.RequestError as exc:
            logger.warning("workspace proxy failed for %s: %s", username, exc)
            return Response(
                content="Your cloud lab is starting or offline. Try again in a minute.",
                status_code=503,
                media_type="text/plain",
            )

    if upstream.status_code in {301, 302, 303, 307, 308}:
        location = upstream.headers.get("location", "")
        if location.startswith("/"):
            location = f"/lab{location}"
        headers_out = dict(upstream.headers)
        headers_out["location"] = location
        return Response(
            status_code=upstream.status_code,
            headers=headers_out,
        )

    hop = {
        "content-encoding",
        "content-length",
        "transfer-encoding",
        "connection",
    }
    out_headers = {
        k: v
        for k, v in upstream.headers.items()
        if k.lower() not in hop
    }

    async def stream_body() -> AsyncIterator[bytes]:
        async for chunk in upstream.aiter_bytes():
            yield chunk

    return StreamingResponse(
        stream_body(),
        status_code=upstream.status_code,
        headers=out_headers,
        media_type=upstream.headers.get("content-type"),
    )


async def proxy_websocket(
    client: WebSocket, username: str, path: str = ""
) -> None:
    path = validate_proxy_path(path)
    target = upstream_ws(username, path)
    if client.url.query:
        target = f"{target}?{client.url.query}"

    await client.accept()
    extra_headers = [
        (k, v)
        for k, v in client.headers.items()
        if k.lower() not in _WS_SKIP_HEADERS
    ]

    try:
        async with websockets.connect(
            target,
            additional_headers=extra_headers,
            max_size=None,
            open_timeout=20,
        ) as upstream:

            async def client_to_upstream() -> None:
                try:
                    while True:
                        message = await client.receive()
                        if message["type"] == "websocket.disconnect":
                            break
                        if "text" in message:
                            await upstream.send(message["text"])
                        elif "bytes" in message:
                            await upstream.send(message["bytes"])
                except WebSocketDisconnect:
                    pass

            async def upstream_to_client() -> None:
                try:
                    async for payload in upstream:
                        if isinstance(payload, str):
                            await client.send_text(payload)
                        else:
                            await client.send_bytes(payload)
                except websockets.ConnectionClosed:
                    pass

            await asyncio.gather(client_to_upstream(), upstream_to_client())
    except Exception as exc:
        logger.warning("websocket proxy %s: %s", username, exc)
        if client.client_state.name == "CONNECTED":
            await client.close(code=1011)
