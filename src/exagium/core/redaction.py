from __future__ import annotations

import re
from typing import Any

_SECRET_KEY = re.compile(
    r"(?:api[_-]?key|authorization|credential|password|secret|token)$",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(?i)(bearer\s+)[a-z0-9._~+/=-]{8,}")
_ASSIGNMENT = re.compile(r"(?i)(api[_-]?key|password|secret|token)(\s*[:=]\s*)([^\s,;]+)")


def redact_text(value: str) -> str:
    value = _BEARER.sub(r"\1[REDACTED]", value)
    return _ASSIGNMENT.sub(r"\1\2[REDACTED]", value)


def redact(value: Any, *, key: str | None = None) -> Any:
    if key and _SECRET_KEY.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {item_key: redact(item, key=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value
