"""MinerU cloud parser (05-ingest.md code-fact reference).

Key resolution priority: argument > env MINERU_API_KEY > config.mineru.api_key.
Key missing → silent fallback (returns "") — this is by design (CONST-ING-1),
not a bug. NEVER hardcode the key here.
"""

from __future__ import annotations

import io
import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error
import zipfile

import requests

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".ppt", ".doc", ".xls", ".xlsx"}
_API_BATCH_URLS = "https://mineru.net/api/v4/file-urls/batch"
_API_RESULTS = "https://mineru.net/api/v4/extract-results/batch/{batch_id}"
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


def mineru_available() -> bool:
    """True if any MinerU key source is configured (arg, env, or config)."""
    return bool(_resolve_mineru_key(""))


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

    try:
        return _do_mineru(path, key)
    except Exception as e:
        raise RuntimeError(f"[mineru] {e}") from e


def _do_mineru(path: str, key: str) -> str:
    """MinerU v4 batch flow: request upload URL → PUT file → poll → download result ZIP.

    Raises RuntimeError on API errors (401, 403, timeout, etc.) so the parse
    chain surfaces the failure reason instead of silently falling back.
    """
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    filename = os.path.basename(path)

    # Step 1: request a presigned upload URL
    body = json.dumps(
        {
            "enable_formula": True,
            "enable_table": True,
            "files": [{"name": filename, "is_ocr": True}],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        _API_BATCH_URLS, data=body, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"[mineru] HTTP {e.code}: {e.read()[:500].decode(errors='replace')}"
        )
    except urllib.error.URLError as e:
        raise RuntimeError(f"[mineru] network error: {e}")

    if data.get("code") != 0:
        raise RuntimeError(
            f"[mineru] API error: code={data.get('code')} msg={data.get('msg')}"
        )
    upload_url = data["data"]["file_urls"][0]
    batch_id = data["data"]["batch_id"]

    # Step 2: PUT file bytes to the presigned OSS URL via requests
    # (requests handles presigned URL signing correctly; http.client manual
    # putrequest/putheader/send produces a signature mismatch and always returns 403)
    with open(path, "rb") as f:
        file_bytes = f.read()
    try:
        resp = requests.put(upload_url, data=file_bytes, timeout=120)
        if resp.status_code not in (200, 201):
            raise RuntimeError(
                f"[mineru] OSS PUT failed: HTTP {resp.status_code} {resp.reason}: "
                f"{resp.text[:500]}"
            )
    except requests.RequestException as e:
        raise RuntimeError(f"[mineru] OSS PUT network error: {e}") from e

    # Step 3: poll until done/failed
    deadline = time.time() + _POLL_TIMEOUT
    poll_url = _API_RESULTS.format(batch_id=batch_id)
    while time.time() < deadline:
        time.sleep(_POLL_INTERVAL)
        poll = urllib.request.Request(poll_url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(poll, timeout=30) as resp:
                result = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue  # not ready yet
            raise RuntimeError(f"[mineru] HTTP {e.code} polling results")
        except urllib.error.URLError as e:
            raise RuntimeError(f"[mineru] network error polling: {e}")
        if result.get("code") != 0:
            raise RuntimeError(f"[mineru] poll API error: {result.get('msg')}")
        extract = result.get("data", {}).get("extract_result", [])
        if not extract:
            continue
        entry = extract[0]
        state = entry.get("state")
        if state == "done":
            zip_url = entry.get("full_zip_url")
            if not zip_url:
                raise RuntimeError("[mineru] done but no zip URL")
            return _download_full_md(zip_url)
        if state == "failed":
            raise RuntimeError(
                f"[mineru] processing failed: {entry.get('err_msg', '?')}"
            )
    raise RuntimeError(f"[mineru] poll timeout after {_POLL_TIMEOUT}s")


def _download_full_md(zip_url: str) -> str:
    """Download the result ZIP and return the content of full.md."""
    try:
        with urllib.request.urlopen(zip_url, timeout=120) as resp:
            blob = resp.read()
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            names = zf.namelist()
            target = (
                "full.md"
                if "full.md" in names
                else next((n for n in names if n.endswith(".md")), None)
            )
            if not target:
                raise RuntimeError("[mineru] no .md file found in result zip")
            return zf.read(target).decode("utf-8", errors="replace")
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError(f"[mineru] zip download/decode error: {e}") from e
