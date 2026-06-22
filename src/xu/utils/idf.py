"""IDF (Inverse Document Frequency) storage in idf.md.

idf.md lives at the wiki root. Format:
  nouns:
    <noun>: {freq: N, weight: W}
  updated_at: <timestamp>

Read: load_idf(ctx) → dict[noun, (freq, weight)]
Write: dump_idf(ctx, idf_dict)
Increment: increment_idf(ctx, nouns_dict) — add counts and rewrite
"""
from __future__ import annotations

from pathlib import Path

from ..utils.constants import IDF_CONSTANT
from ..utils.paths import now_ts


def _idf_path(ctx) -> Path:
    return ctx.root / "idf.md"


def load_idf(ctx) -> dict[str, tuple[int, float]]:
    """Load IDF noun table from idf.md. Returns {noun: (freq, weight)}."""
    p = _idf_path(ctx)
    if not p.exists():
        return {}
    try:
        import yaml
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        nouns = data.get("nouns", {})
        result = {}
        for noun, v in nouns.items():
            if isinstance(v, dict):
                result[noun] = (v.get("freq", 0), v.get("weight", 0.0))
            else:
                result[noun] = (0, 0.0)
        return result
    except Exception:
        return {}


def dump_idf(ctx, idf: dict[str, tuple[int, float]]) -> None:
    """Write IDF table to idf.md."""
    import yaml
    p = _idf_path(ctx)
    data = {
        "nouns": {noun: {"freq": freq, "weight": weight} for noun, (freq, weight) in idf.items()},
        "updated_at": now_ts(),
    }
    p.write_text(yaml.dump(data, allow_unicode=True), encoding="utf-8")


def increment_idf(ctx, nouns: dict[str, int]) -> None:
    """Add noun counts to IDF table and rewrite idf.md."""
    if not nouns:
        return
    idf = load_idf(ctx)
    ts = now_ts()
    for noun, cnt in nouns.items():
        freq, weight = idf.get(noun, (0, 0.0))
        new_freq = freq + cnt
        new_weight = IDF_CONSTANT / (new_freq + 1)
        idf[noun] = (new_freq, new_weight)
    dump_idf(ctx, idf)
