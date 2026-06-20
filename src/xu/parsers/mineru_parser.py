"""MinerU cloud parser (05-ingest.md code-fact reference).

Key resolution priority: argument > env MINERU_API_KEY > config.mineru.api_key.
Key missing → silent fallback (returns "") — this is by design (CONST-ING-1),
not a bug. NEVER hardcode the key here.
"""
from __future__ import annotations

import http.client
import io
import json
import os
import time
import urllib.request
import urllib.parse
import zipfile

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".ppt", ".doc", ".xls", ".xlsx"}
_API_BATCH_URLS = "https://mineru.net/api/v4/file-urls/batch"
_API_RESULTS = "https://mineru.net/api/v4/extract-results/batch/{batch_id}"
_API_MAX_PAGES = 200
_API_MAX_SIZE_MB = 200
_MODEL_VERSION = "vlm"
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
    """Real MinerU v4 batch flow: request upload URL → PUT file → poll batch
    results → download result ZIP → return full.md content.

    Matches the official Precision Extract API (api/v4/file-urls/batch +
    api/v4/extract-results/batch/{batch_id}).
    """
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    filename = os.path.basename(path)

    # 1. request a presigned upload URL (batch). is_ocr per-file; model_version outer.
    body = json.dumps({
        "enable_formula": True,
        "enable_table": True,
        "model_version": _MODEL_VERSION,
        "files": [{"name": filename, "is_ocr": True}],
    }).encode("utf-8")
    req = urllib.request.Request(_API_BATCH_URLS, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    if data.get("code") != 0:
        return ""
    upload_url = data["data"]["file_urls"][0]
    batch_id = data["data"]["batch_id"]

    # 2. PUT the raw bytes to the presigned URL via http.client.
    #    urllib.request uses chunked transfer encoding by default, but OSS
    #    presigned URLs require an explicit Content-Length header — without it
    #    the signature does not cover the body and OSS returns 403.
    #    We also stream the file in chunks to avoid reading a large PDF
    #    entirely into memory.
    parsed = urllib.parse.urlparse(upload_url)
    conn = http.client.HTTPSConnection(parsed.netloc, timeout=120)
    try:
        file_size = os.path.getsize(path)
        with open(path, "rb") as f:
            chunk_size = 64 * 1024  # 64 KB chunks
            conn.connect()
            conn.putrequest("PUT", parsed.path)
            conn.putheader("Content-Length", str(file_size))
            conn.endheaders()
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                conn.send(chunk)
            resp = conn.getresponse()
            if resp.status not in (200, 201):
                raise RuntimeError(f"OSS PUT failed: {resp.status} {resp.reason}")
    finally:
        conn.close()

    # 3. poll batch results until this file's state is done/failed
    deadline = time.time() + _POLL_TIMEOUT
    poll_url = _API_RESULTS.format(batch_id=batch_id)
    while time.time() < deadline:
        time.sleep(_POLL_INTERVAL)
        poll = urllib.request.Request(poll_url, headers=headers, method="GET")
        with urllib.request.urlopen(poll, timeout=30) as resp:
            result = json.loads(resp.read())
        if result.get("code") != 0:
            continue
        extract = result.get("data", {}).get("extract_result", [])
        if not extract:
            continue
        entry = extract[0]
        state = entry.get("state")
        if state == "done":
            zip_url = entry.get("full_zip_url")
            return _download_full_md(zip_url) if zip_url else ""
        if state == "failed":
            return ""
    return ""


def _download_full_md(zip_url: str) -> str:
    """Download the result ZIP and return the content of full.md."""
    try:
        with urllib.request.urlopen(zip_url, timeout=120) as resp:
            blob = resp.read()
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = zf.namelist()
            target = "full.md" if "full.md" in names else next(
                (n for n in names if n.endswith(".md")), None
            )
            if not target:
                return ""
            return zf.read(target).decode("utf-8", errors="replace")
    except Exception:
        return ""
