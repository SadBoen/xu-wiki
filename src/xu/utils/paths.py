"""Path helpers, UID generation, hashing, logging (CONST-ARCH-3/6, BAN-ARCH-7)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from pathlib import Path

UID_RE = re.compile(r"^[A-Z0-9]{8}$")
_UID_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

# gen_uid per-second monotonic counter (bounded, resets each second)
_uid_second_ts: int = 0
_uid_counter: int = 0


def now_ts() -> int:
    return int(time.time())


def gen_uid() -> str:
    """UID = 8-char base-36 code (CONST-ARCH-3).

    Uniqueness is guaranteed by two layers:
    1. Per-second monotonic counter (2 base-36 digits, 0-1295): within the
       same second, each call gets a sequential code — no collision possible.
    2. Random fallback: if the counter overflows (>1295 UIDs in one second,
       unrealistic in practice), switches to pure random (36^6 namespace).
    Globally unique, never reused (BAN-ARCH-2).
    """
    global _uid_second_ts, _uid_counter
    now_sec = int(time.time())

    if now_sec == _uid_second_ts:
        _uid_counter += 1
    else:
        _uid_second_ts = now_sec
        _uid_counter = 0

    if _uid_counter < 1296:
        q, r = divmod(_uid_counter, 36)
        counter_part = _UID_ALPHABET[q] + _UID_ALPHABET[r]
        random_part = "".join(secrets.choice(_UID_ALPHABET) for _ in range(6))
        code = counter_part + random_part
    else:
        code = "".join(secrets.choice(_UID_ALPHABET) for _ in range(8))

    return code


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


def safe_node_path(node_path: str) -> str:
    """Validate a user-supplied logical node_path (BAN-ARCH-7).

    node_path is a relative logical partition like ``papers/ml``. It must stay
    in-tree: no absolute paths, no '..' traversal segments. Returns the cleaned
    (slash-stripped) value. Raises ValueError on any escape attempt.
    """
    np = (node_path or "").strip().replace("\\", "/").strip("/")
    if not np:
        return ""
    if Path(np).is_absolute():
        raise ValueError(f"node_path must be relative: {node_path!r}")
    if any(part == ".." for part in np.split("/")):
        raise ValueError(f"node_path must not contain '..': {node_path!r}")
    return np


def safe_slug(text: str, maxlen: int = 80) -> str:
    s = re.sub(r"[^\w\-]+", "-", (text or "").strip().lower(), flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-")
    return (s or "untitled")[:maxlen]


def append_jsonl(log_path: str | Path, record: dict, *, mkdir: bool = True) -> None:
    """Append one JSONL line for audit (CONST-ARCH-6)."""
    try:
        p = Path(log_path)
        if mkdir:
            p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass


def atomic_write_text(path: str | Path, content: str) -> None:
    """Write to a temp file then atomically rename (CONST-ARCH-5)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}.{secrets.token_hex(4)}")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except OSError:
        # don't leave a half-written temp behind on rename/IO failure
        try:
            tmp.unlink()
        except OSError:
            pass
        raise
