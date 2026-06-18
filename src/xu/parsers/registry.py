"""Parser plugins + fallback chain (PRIN-ING-5, CONST-ING-1).

Each parser exposes:  name, can_parse(path) -> bool, parse(path, **kw) -> str|None
Fallback chains are grouped by format; failure auto-falls-back; tail is a
"store-without-parsing" safety net. "Must have a parse result to enter Phase 2"
is unbreakable (PRIN-ING-5): a fully empty result rejects Phase 2.
"""
from __future__ import annotations

from pathlib import Path


class ParseResult:
    def __init__(self, text: str, parser: str, ok: bool = True):
        self.text = text or ""
        self.parser = parser
        self.ok = ok and bool(text and text.strip())


# ---- MinerU primary (cloud API; silent fallback if key missing) ----
class MinerUParser:
    name = "mineru"
    SUPPORTED = {".pdf", ".docx", ".pptx"}

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() in self.SUPPORTED

    def parse(self, path: Path, **kw) -> ParseResult | None:
        from ..parsers.mineru_parser import mineru_parse
        text = mineru_parse(str(path), api_key=kw.get("mineru_key", ""))
        if text and text.strip():
            return ParseResult(text, self.name)
        return None  # silent fallback (CONST-ING-1) — by design, not a bug


# ---- markitdown local fallback (offline, no API) ----
class MarkitdownParser:
    name = "markitdown"
    SUPPORTED = {".pdf", ".docx", ".pptx", ".xlsx", ".html", ".htm", ".csv"}

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() in self.SUPPORTED

    def parse(self, path: Path, **kw) -> ParseResult | None:
        try:
            from markitdown import MarkItDown
            md = MarkItDown()
            r = md.convert(str(path))
            return ParseResult(r.text_content, self.name)
        except Exception:
            return None


# ---- plain text / markdown / csv ----
class TextParser:
    name = "text"
    SUPPORTED = {".txt", ".md", ".markdown", ".csv", ".log", ".json", ".yaml", ".yml"}

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() in self.SUPPORTED

    def parse(self, path: Path, **kw) -> ParseResult | None:
        try:
            return ParseResult(path.read_text(encoding="utf-8", errors="replace"), self.name)
        except Exception:
            return None


# ---- image fallback (description placeholder; vision/ocr would slot here) ----
class ImageParser:
    name = "image-fallback"
    SUPPORTED = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}

    def can_parse(self, path: Path) -> bool:
        return path.suffix.lower() in self.SUPPORTED

    def parse(self, path: Path, **kw) -> ParseResult | None:
        # No vision/ocr engine wired in this build; emit a minimal descriptor so
        # the image is still traceable. Real deploy slots vision(主)→ocr(次) here.
        from ..utils.paths import sha256_file
        try:
            size = path.stat().st_size
            digest = sha256_file(path)[:16]
        except OSError:
            return None
        text = (
            f"# Image: {path.name}\n\n"
            f"- filename: {path.name}\n"
            f"- size_bytes: {size}\n"
            f"- sha256_prefix: {digest}\n\n"
            f"_No vision/OCR engine configured; stored as image descriptor._\n"
        )
        return ParseResult(text, self.name)


# Fallback chains grouped by format (PRIN-ING-5 default chain).
_RICHDOC = [MinerUParser(), MarkitdownParser()]
_SPREADSHEET = [MarkitdownParser()]
_IMAGE = [ImageParser()]
_TEXT = [TextParser()]


def _chain_for(path: Path) -> list:
    ext = path.suffix.lower()
    if ext in {".pdf", ".docx", ".pptx"}:
        return _RICHDOC
    if ext in {".xlsx", ".xls"}:
        return _SPREADSHEET
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff"}:
        return _IMAGE
    if ext in {".txt", ".md", ".markdown", ".csv", ".log", ".json", ".yaml", ".yml", ".html", ".htm"}:
        # html best handled by markitdown; csv/text by TextParser
        if ext in {".html", ".htm"}:
            return [MarkitdownParser(), TextParser()]
        return _TEXT
    return [MarkitdownParser(), TextParser()]  # generic best-effort


def parse_file(path: str | Path, **kw) -> ParseResult:
    """Run the fallback chain. Returns a ParseResult; .ok=False means rejected."""
    p = Path(path)
    chain = _chain_for(p)
    attempts = []
    for parser in chain:
        if not parser.can_parse(p):
            continue
        try:
            res = parser.parse(p, **kw)
        except Exception as e:
            attempts.append(f"{parser.name}: {e}")
            continue
        if res and res.ok:
            return res
        attempts.append(f"{parser.name}: empty")
    # All failed — reject Phase 2 (PRIN-ING-5)
    return ParseResult("", "none", ok=False)
