"""Path helpers, UID generation, hashing, logging (CONST-ARCH-3/6, BAN-ARCH-7)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path

UID_RE = re.compile(r"^\d{4}-[A-Z0-9]{8}$")
_UID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def now_ts() -> int:
    return int(time.time())


def current_year() -> int:
    return time.gmtime().tm_year


def gen_uid(year: int | None = None) -> str:
    """UID = year prefix + 8-char uppercase alnum short code (CONST-ARCH-3).

    Globally unique, never reused (BAN-ARCH-2). 36^8 namespace.
    """
    yr = year or current_year()
    code = "".join(secrets.choice(_UID_ALPHABET) for _ in range(8))
    return f"{yr}-{code}"


def is_valid_uid(uid: str) -> bool:
    return bool(UID_RE.match(uid or ""))


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_within(root: str | Path, candidate: str | Path) -> Path:
    """Resolve candidate and assert it stays inside root (BAN-ARCH-7).

    Resolves symlinks and '..' segments. Raises ValueError on escape.
    """
    root_resolved = Path(root).resolve()
    cand_resolved = (root_resolved / candidate).resolve() if not Path(candidate).is_absolute() else Path(candidate).resolve()
    try:
        cand_resolved.relative_to(root_resolved)
    except ValueError:
        raise ValueError(f"path escapes wiki root: {candidate}")
    return cand_resolved


def safe_slug(text: str, maxlen: int = 80) -> str:
    s = re.sub(r"[^\w\-]+", "-", (text or "").strip().lower(), flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-")
    return (s or "untitled")[:maxlen]


def append_jsonl(log_path: str | Path, record: dict) -> None:
    """Append one JSONL line for audit (CONST-ARCH-6)."""
    try:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def atomic_write_text(path: str | Path, content: str) -> None:
    """Write to a temp file then atomically rename (CONST-ARCH-5)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{secrets.token_hex(4)}")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
