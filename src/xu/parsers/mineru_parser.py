"""MinerU cloud parser (05-ingest.md code-fact reference).

Key resolution priority: argument > env MINERU_API_KEY > config.mineru.api_key.
Key missing → silent fallback (returns "") — this is by design (CONST-ING-1),
not a bug. NEVER hardcode the key here.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx"}
_API_BATCH_URLS = "https://mineru.net/api/v4/file-urls/batch"
_API_RESULTS = "https://mineru.net/api/v4/extract-results/batch"
_API_MAX_PAGES = 200
_API_MAX_SIZE_MB = 200
_POLL_INTERVAL = 3
_POLL_TIMEOUT = 600


def _resolve_mineru_key(api_key: str) -> str:
    if api_key:
        return api_key
    env_key = os.getenv("MINERU_API_KEY", "")
    if env_key:
        return env_key
    try:
        from ..utils.config import load_global_config
        cfg = load_global_config()
        return cfg.get("mineru", {}).get("api_key", "")
    except Exception:
        return ""


def mineru_parse(path: str, api_key: str = "") -> str:
    """Return parsed markdown, or "" to trigger fallback.

    This implementation resolves the key and gracefully returns "" whenever the
    key is missing or the service is unreachable, so the fallback chain takes over.
    """
    key = _resolve_mineru_key(api_key)
    if not key:
        return ""  # silent fallback — by design

    try:
        size_mb = os.path.getsize(path) / (1024 * 1024)
        if size_mb > _API_MAX_SIZE_MB:
            return ""
    except OSError:
        return ""

    # Network call is best-effort; any failure → fallback. We keep it minimal and
    # never block the test pipeline on external availability.
    try:
        return _do_mineru(path, key)
    except Exception:
        return ""


def _do_mineru(path: str, key: str) -> str:
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    filename = os.path.basename(path)
    body = json.dumps({
        "enable_formula": True,
        "enable_table": True,
        "files": [{"name": filename, "is_ocr": True}],
    }).encode("utf-8")
    req = urllib.request.Request(_API_BATCH_URLS, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    upload_url = data["data"]["file_urls"][0]
    batch_id = data["data"]["batch_id"]

    with open(path, "rb") as f:
        put = urllib.request.Request(upload_url, data=f.read(), method="PUT")
        urllib.request.urlopen(put, timeout=120)

    deadline = time.time() + _POLL_TIMEOUT
    while time.time() < deadline:
        time.sleep(_POLL_INTERVAL)
        poll = urllib.request.Request(
            f"{_API_RESULTS}?batch_id={batch_id}", headers=headers, method="GET"
        )
        with urllib.request.urlopen(poll, timeout=30) as resp:
            result = json.loads(resp.read())
        extract = result.get("data", {}).get("extract_result", [])
        if extract and extract[0].get("state") == "done":
            md_url = extract[0].get("full_zip_url") or extract[0].get("markdown_url")
            if md_url:
                with urllib.request.urlopen(md_url, timeout=60) as resp:
                    return resp.read().decode("utf-8", errors="replace")
            return ""
        if extract and extract[0].get("state") == "failed":
            return ""
    return ""
