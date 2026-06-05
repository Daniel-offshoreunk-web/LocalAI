"""Scan inference payloads for obviously dangerous patterns.

This is a shallow guard (regex + optional AST on extracted Python), not a
sandbox. It blocks common reverse-shell / subprocess patterns in prompts
before they reach Ollama.
"""

import ast
import json
import re
from typing import Any

# Patterns that should never appear in student prompts to the model.
_BLOCKED_RE = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bos\.system\s*\(",
        r"\bsubprocess\b",
        r"\bsocket\.socket\s*\(",
        r"\bpty\.spawn\b",
        r"\beval\s*\(",
        r"\bexec\s*\(",
        r"\b__import__\s*\(",
        r"\bimportlib\.import_module\b",
        r"\brequests\.(get|post|put|delete)\s*\(",
        r"\burllib\.request\b",
        r"\bwget\b|\bcurl\b",
        r"\bnc\s+-",
        r"\b/bin/(?:ba)?sh\b",
        r"\bchmod\s+[0-7]{3,4}\b",
        r"\brm\s+-rf\b",
    )
]

_PYTHON_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def _ast_violations(code: str) -> list[str]:
    violations: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in {"os", "subprocess", "socket", "pty"}:
                    violations.append(f"import:{alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.module.split(".")[0] in {
                "os",
                "subprocess",
                "socket",
                "pty",
            }:
                violations.append(f"import_from:{node.module}")
        elif isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in {"system", "popen", "exec", "eval", "compile"}:
                violations.append(f"call:{name}")
    return violations


def scan_text(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in _BLOCKED_RE:
        if pattern.search(text):
            hits.append(f"pattern:{pattern.pattern[:40]}")
    for block in _PYTHON_FENCE.findall(text):
        hits.extend(_ast_violations(block))
    return hits


def scan_chat_payload(raw_body: bytes) -> list[str]:
    """Inspect an OpenAI-style chat/completions JSON body."""
    try:
        payload = json.loads(raw_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ["invalid_json"]

    if not isinstance(payload, dict):
        return ["invalid_shape"]

    messages = payload.get("messages")
    if messages is None:
        return []

    if not isinstance(messages, list):
        return ["invalid_messages"]

    violations: list[str] = []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if isinstance(content, str):
            violations.extend(scan_text(content))
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text", "")
                    if isinstance(text, str):
                        violations.extend(scan_text(text))
    return violations
