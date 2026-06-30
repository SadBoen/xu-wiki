"""ripgrep scanner with Python re fallback (DESIGN-ARCH-3, CONST-QRY-8)."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path


def _rg_available() -> bool:
    return shutil.which("rg") is not None


def scan(search_dir: Path, keywords: list[str], timeout: float = 10.0) -> dict:
    """Return {keyword: [{file, line, col, match, byte_offset}]} for all hits.

    Searches *.md files. Uses ripgrep when available, else Python re.
    """
    keywords = [k for k in keywords if k.strip()]
    if not keywords:
        return {}
    if _rg_available():
        try:
            return _scan_rg(search_dir, keywords, timeout)
        except Exception:
            return _scan_re(search_dir, keywords)
    return _scan_re(search_dir, keywords)


def _scan_rg(search_dir: Path, keywords: list[str], timeout: float) -> dict:
    results: dict[str, list] = {k: [] for k in keywords}
    for kw in keywords:
        cmd = [
            "rg",
            "--json",
            "--fixed-strings",
            "--ignore-case",
            "--type-add",
            "md:*.md",
            "-tmd",
            kw,
            str(search_dir),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            continue
        for line in proc.stdout.splitlines():
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") != "match":
                continue
            d = obj["data"]
            path = d["path"]["text"]
            line_no = d["line_number"]
            text = d["lines"]["text"]
            line_bytes = text.encode("utf-8")
            for sm in d.get("submatches", []):
                # rg reports byte offsets; convert to a CHARACTER offset so it
                # matches the Python-re fallback and the char-based slicer
                # (CONST-QRY-8 determinism on CJK text).
                byte_start = sm["start"]
                col_char = len(line_bytes[:byte_start].decode("utf-8", errors="ignore"))
                results[kw].append(
                    {
                        "file": path,
                        "line": line_no,
                        "col": col_char,
                        "match": sm["match"]["text"],
                        "line_text": text.rstrip("\n"),
                    }
                )
    return results


def _scan_re(search_dir: Path, keywords: list[str]) -> dict:
    results: dict[str, list] = {k: [] for k in keywords}
    patterns = {k: re.compile(re.escape(k), re.IGNORECASE) for k in keywords}
    for md in search_dir.rglob("*.md"):
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            for kw, pat in patterns.items():
                for m in pat.finditer(line):
                    results[kw].append(
                        {
                            "file": str(md),
                            "line": line_no,
                            "col": m.start(),
                            "match": m.group(0),
                            "line_text": line,
                        }
                    )
    return results
