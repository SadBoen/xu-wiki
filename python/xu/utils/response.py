"""4-key JSON response protocol (CONST-ARCH-1).

Every CLI command returns {status, data, message, hints}.
- success: fully succeeded
- warning: partially succeeded (e.g. SHA256 dup, partial relations)
- error: fully failed (data.error_class for classification)
"""
from __future__ import annotations

import json
import sys
from typing import Any


def make_response(
    status: str,
    data: Any = None,
    message: str = "",
    hints: list[str] | None = None,
) -> dict:
    assert status in ("success", "warning", "error"), f"bad status: {status}"
    return {
        "status": status,
        "data": data if data is not None else {},
        "message": message,
        "hints": hints or [],
    }


def success(data: Any = None, message: str = "", hints: list[str] | None = None) -> dict:
    return make_response("success", data, message, hints)


def warning(data: Any = None, message: str = "", hints: list[str] | None = None) -> dict:
    return make_response("warning", data, message, hints)


def error(
    message: str = "",
    error_class: str = "GenericError",
    data: dict | None = None,
    hints: list[str] | None = None,
) -> dict:
    payload = dict(data or {})
    payload.setdefault("error_class", error_class)
    return make_response("error", payload, message, hints)


def emit(response: dict, exit_code: int | None = None) -> int:
    """Print a 4-key response as JSON to stdout and return an exit code."""
    sys.stdout.write(json.dumps(response, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    if exit_code is None:
        exit_code = 0 if response["status"] in ("success", "warning") else 1
    return exit_code
