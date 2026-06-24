"""doc_parser — thin wrapper around markitdown for Rust via pyo3.

No business logic. Pure library interface.
Supports: .pdf .docx .pptx .html .htm
Returns empty string on failure (caller decides fallback strategy).
"""
from __future__ import annotations

import os
from pathlib import Path


SUPPORTED = {".pdf", ".docx", ".pptx", ".html", ".htm"}


def can_parse(path: str) -> bool:
    """Return True if the file extension is supported."""
    return Path(path).suffix.lower() in SUPPORTED


def parse_document(path: str) -> str:
    """Parse a document and return its text content as markdown.

    Returns empty string on any error. The caller handles fallback.
    """
    p = Path(path)
    if not p.is_file():
        return ""
    try:
        from markitdown import MarkItDown

        md = MarkItDown()
        result = md.convert(str(p))
        content = result.text_content or ""
        return content.strip()
    except Exception:
        return ""


def get_document_text(path: str) -> str:
    """Alias for parse_document for backward compatibility."""
    return parse_document(path)
