"""Page splitting (PRIN-ING-4)."""

from __future__ import annotations

import re

from ..utils.constants import PAGE_SPLIT_LINES

_HEADER_RE = re.compile(r"^(#{1,6})\s+")


def split_pages(text: str, max_lines: int = PAGE_SPLIT_LINES) -> list[str]:
    """Split body into pages of ~max_lines (PRIN-ING-4).

    Decision tree (top-down, first match wins):
    1. Headers (# / ## / ### ...) are candidate cut points.
    2. Too-small sections merge upward by physical adjacency toward max_lines.
    3. No clear boundaries → hard-cut by line count.
    Remainder rule: every max_lines accumulated → cut; trailing remainder is its
    own page (floor division, no upward merge of the tail).
    """
    lines = text.splitlines()
    if not lines:
        return [text] if text.strip() else []
    if len(lines) <= max_lines:
        return ["\n".join(lines)]

    # Find header cut points
    header_idx = [i for i, ln in enumerate(lines) if _HEADER_RE.match(ln)]

    if not header_idx:
        return _hard_split(lines, max_lines)

    # Build sections from headers, then greedily merge to ~max_lines
    boundaries = sorted(set([0] + header_idx + [len(lines)]))
    sections: list[tuple[int, int]] = []
    for a, b in zip(boundaries, boundaries[1:]):
        if b > a:
            sections.append((a, b))

    pages: list[str] = []
    cur_start = sections[0][0]
    cur_end = cur_start
    for a, b in sections:
        seg_len = b - cur_start
        if seg_len >= max_lines and cur_end > cur_start:
            # flush accumulated, start fresh at this section
            pages.append("\n".join(lines[cur_start:cur_end]))
            cur_start = a
        cur_end = b
        if (cur_end - cur_start) >= max_lines:
            pages.append("\n".join(lines[cur_start:cur_end]))
            cur_start = cur_end
    if cur_end > cur_start:
        pages.append("\n".join(lines[cur_start:cur_end]))

    # Any page still > 2*max_lines (huge section, no inner headers) → hard split it
    final: list[str] = []
    for pg in pages:
        pls = pg.splitlines()
        if len(pls) > max_lines * 2:
            final.extend(_hard_split(pls, max_lines))
        else:
            final.append(pg)
    return [p for p in final if p.strip()]


def _hard_split(lines: list[str], max_lines: int) -> list[str]:
    out = []
    for i in range(0, len(lines), max_lines):
        chunk = lines[i : i + max_lines]
        if any(c.strip() for c in chunk):
            out.append("\n".join(chunk))
    return out
