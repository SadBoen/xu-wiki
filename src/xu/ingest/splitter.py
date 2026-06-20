"""Page splitting (PRIN-ING-4) + noun extraction for IDF (PRIN-ING-9)."""
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
    for (a, b) in sections:
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
        chunk = lines[i:i + max_lines]
        if any(c.strip() for c in chunk):
            out.append("\n".join(chunk))
    return out


_NOUN_FLAGS = {"n", "nr", "ns", "nt", "nz", "nl", "ng", "eng"}
_LATIN_RE = re.compile(r"[A-Za-z0-9]{2,}")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")


def _bigrams(run: str) -> list[str]:
    """Slide a 2-char window over a CJK run (single char yields itself)."""
    if len(run) < 2:
        return [run]
    return [run[i:i + 2] for i in range(len(run) - 1)]


def extract_nouns(text: str) -> dict[str, int]:
    """Extract noun-like tokens with within-document counts.

    Uses jieba POS tagging when available; falls back to a tokenizer that
    splits Latin runs on word boundaries and CJK runs into overlapping
    bigrams. The bigram fallback keeps short Chinese query terms findable in
    the IDF table even when jieba is not installed (PRIN-ARCH-20).
    """
    counts: dict[str, int] = {}
    try:
        # CONST-ARCH-1: every CLI emits one 4-key JSON line; jieba's first-run
        # banner ("Building prefix dict...") writes directly to FDs 1/2 (bypassing
        # Python's sys.stdout) and would corrupt the JSON protocol. Suppress at
        # the file-descriptor level.
        import os
        _so = os.dup(1)
        _se = os.dup(2)
        _rnul = os.open(os.devnull, os.O_WRONLY)
        try:
            os.dup2(_rnul, 1)
            os.dup2(_rnul, 2)
            import jieba.posseg as pseg
            words_and_flags = list(pseg.cut(text))
        finally:
            os.dup2(_so, 1)
            os.dup2(_se, 2)
            os.close(_so)
            os.close(_se)
            os.close(_rnul)
        for word, flag in words_and_flags:
            w = word.strip().lower()
            if len(w) < 2:
                continue
            if flag in _NOUN_FLAGS:
                counts[w] = counts.get(w, 0) + 1
        if counts:
            return counts
    except Exception:
        pass
    # fallback tokenizer: Latin word runs + CJK bigrams
    lowered = text.lower()
    for tok in _LATIN_RE.findall(lowered):
        counts[tok] = counts.get(tok, 0) + 1
    for run in _CJK_RUN_RE.findall(lowered):
        for tok in _bigrams(run):
            counts[tok] = counts.get(tok, 0) + 1
    return counts
