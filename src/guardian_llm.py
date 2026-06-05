"""Secondary safety filter — small LocalAI model classifies student input."""

import json
import logging
import re

import httpx

from .config import (
    GUARDIAN_ENABLED,
    GUARDIAN_FAIL_OPEN,
    GUARDIAN_MAX_CHARS,
    GUARDIAN_MODEL,
    GUARDIAN_TIMEOUT,
    INFERENCE_API_KEY,
    INFERENCE_URL,
)
logger = logging.getLogger(__name__)


def _guardian_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if INFERENCE_API_KEY:
        headers["Authorization"] = f"Bearer {INFERENCE_API_KEY}"
    return headers

_SYSTEM_PROMPT = """You are a school computer-science lab safety filter.
Classify the student message as SAFE or UNSAFE.

UNSAFE: malware, exploits, reverse shells, credential theft, harassment, instructions to bypass security or cheat on graded work, destructive system commands.
SAFE: normal programming help, debugging, algorithms, syntax, project questions.

Reply with exactly one line:
SAFE
or
UNSAFE: brief reason"""

_UNSAFE_RE = re.compile(r"^\s*UNSAFE\b", re.IGNORECASE)


async def guardian_check_text(text: str) -> str | None:
    """Return a violation label if the guardian model flags the text, else None."""
    if not GUARDIAN_ENABLED:
        return None

    snippet = text.strip()
    if not snippet:
        return None
    if len(snippet) > GUARDIAN_MAX_CHARS:
        snippet = snippet[:GUARDIAN_MAX_CHARS]

    payload = {
        "model": GUARDIAN_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": snippet},
        ],
        "temperature": 0.0,
        "max_tokens": 64,
        "stream": False,
    }

    url = f"{INFERENCE_URL}/v1/chat/completions"
    headers = _guardian_headers()
    timeout = httpx.Timeout(GUARDIAN_TIMEOUT, connect=5.0)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            upstream = await client.post(
                url, headers=headers, content=json.dumps(payload).encode()
            )
    except httpx.RequestError as exc:
        logger.warning("guardian model unreachable: %s", exc)
        return "guardian_unavailable" if not GUARDIAN_FAIL_OPEN else None

    if upstream.status_code >= 400:
        logger.warning(
            "guardian model error status=%s body=%s",
            upstream.status_code,
            upstream.text[:200],
        )
        return "guardian_error" if not GUARDIAN_FAIL_OPEN else None

    try:
        data = upstream.json()
        verdict = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
    except (json.JSONDecodeError, TypeError, IndexError):
        return "guardian_parse_error" if not GUARDIAN_FAIL_OPEN else None

    if _UNSAFE_RE.match(verdict):
        reason = verdict.split(":", 1)[1].strip() if ":" in verdict else verdict
        return f"guardian:{reason[:120]}"

    if verdict.upper().startswith("SAFE"):
        return None

    logger.warning("guardian ambiguous verdict: %r", verdict[:80])
    return "guardian_ambiguous" if not GUARDIAN_FAIL_OPEN else None
