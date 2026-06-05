"""Unified student input safety — static scanners plus optional guardian LLM."""

from fastapi import HTTPException

from .db import get_db
from .guardian_llm import guardian_check_text
from .prompt_guard import extract_chat_text, scan_chat_payload, scan_text


async def _record_block(username: str, detail: str) -> None:
    await get_db().record_security_event(username, "prompt_blocked", detail[:240])


async def enforce_text_safety(text: str, *, username: str) -> None:
    """Run regex/AST and guardian checks on a single message string."""
    violations = scan_text(text)
    if violations:
        await _record_block(username, ",".join(violations[:5]))
        raise HTTPException(status_code=400, detail="Message blocked by safety policy.")

    guardian_hit = await guardian_check_text(text)
    if guardian_hit:
        await _record_block(username, guardian_hit)
        raise HTTPException(status_code=400, detail="Message blocked by safety policy.")


async def enforce_payload_safety(raw_body: bytes, *, username: str) -> None:
    """Run all safety checks on an OpenAI-style chat/completions body."""
    violations = scan_chat_payload(raw_body)
    if violations:
        await _record_block(username, ",".join(violations[:5]))
        raise HTTPException(status_code=400, detail="Request blocked by safety policy.")

    combined = extract_chat_text(raw_body)
    if combined:
        guardian_hit = await guardian_check_text(combined)
        if guardian_hit:
            await _record_block(username, guardian_hit)
            raise HTTPException(status_code=400, detail="Request blocked by safety policy.")
