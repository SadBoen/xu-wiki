"""YAML frontmatter parsing / rendering for Node markdown files (PRIN-ARCH-15)."""

from __future__ import annotations

import yaml

_DELIM = "---"


def parse(text: str) -> tuple[dict, str]:
    """Split a markdown document into (frontmatter dict, body)."""
    if not text.startswith(_DELIM):
        return {}, text
    lines = text.splitlines()
    if not lines or lines[0].strip() != _DELIM:
        return {}, text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _DELIM:
            end = i
            break
    if end is None:
        return {}, text
    fm_text = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1 :])
    if body.startswith("\n"):
        body = body[1:]
    fm = yaml.safe_load(fm_text) or {}
    if not isinstance(fm, dict):
        fm = {}
    return fm, body


def render(frontmatter: dict, body: str) -> str:
    fm_text = yaml.safe_dump(frontmatter, allow_unicode=True, sort_keys=False).rstrip()
    return f"{_DELIM}\n{fm_text}\n{_DELIM}\n\n{body.rstrip()}\n"
