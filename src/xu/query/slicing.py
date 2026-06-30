"""Elastic slicing + neighborhood merge (DESIGN-ARCH-6/7, PRIN-QRY-8/9)."""

from __future__ import annotations

_HIGH_PUNCT = "。？！.?!\n"
_LOW_PUNCT = "，,;；"


def make_slice(
    text: str, hit_start: int, hit_end: int, soft_limit: int, hard_limit: int
) -> tuple[int, int, str]:
    """Expand a hit [start,end) into a slice bounded by soft/hard limits.

    Prefer high-priority punctuation within soft limit; low-priority next;
    hard limit forces truncation (PRIN-QRY-8).
    """
    n = len(text)
    left = _expand_left(text, hit_start, soft_limit, hard_limit)
    right = _expand_right(text, hit_end, soft_limit, hard_limit)
    left = max(0, left)
    right = min(n, right)
    return left, right, text[left:right]


def _expand_left(text: str, pos: int, soft: int, hard: int) -> int:
    soft_bound = max(0, pos - soft)
    hard_bound = max(0, pos - hard)
    # search backward within soft window for high punct
    for i in range(pos - 1, soft_bound - 1, -1):
        if text[i] in _HIGH_PUNCT:
            return i + 1
    for i in range(pos - 1, soft_bound - 1, -1):
        if text[i] in _LOW_PUNCT:
            return i + 1
    return hard_bound


def _expand_right(text: str, pos: int, soft: int, hard: int) -> int:
    n = len(text)
    soft_bound = min(n, pos + soft)
    hard_bound = min(n, pos + hard)
    for i in range(pos, soft_bound):
        if text[i] in _HIGH_PUNCT:
            return i + 1
    for i in range(pos, soft_bound):
        if text[i] in _LOW_PUNCT:
            return i + 1
    return hard_bound


def merge_slices(
    slices: list[dict], radius: int, text: str | None = None
) -> list[dict]:
    """Merge same-file slices whose physical distance < radius (PRIN-QRY-9).

    Each slice dict: {start, end, text, hits:set, line}. Returns merged blocks.
    When `text` (the full document) is provided, a merged block's `text` is
    re-sliced from [start, end] so the context block actually spans the merged
    region (otherwise scoring & snippets would only see the first slice).
    """
    if not slices:
        return []
    ordered = sorted(slices, key=lambda s: s["start"])
    merged = [dict(ordered[0])]
    merged[0]["hits"] = set(ordered[0]["hits"])
    for s in ordered[1:]:
        last = merged[-1]
        if s["start"] - last["end"] < radius:
            # overlap or close → merge into one context block
            last["end"] = max(last["end"], s["end"])
            last["hits"] |= set(s["hits"])
            if text is not None:
                last["text"] = text[last["start"] : last["end"]]
        else:
            nb = dict(s)
            nb["hits"] = set(s["hits"])
            merged.append(nb)
    return merged
