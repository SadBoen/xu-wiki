"""Query engine: SQLite LIKE scan + slice + score + Fast Pass (T6).

Exports run_query() which takes a WikiContext and keyword args, returns
the same dict shape as cmd_query() in commands/query.py.
"""
from __future__ import annotations

import yaml
from pathlib import Path

from ..utils import frontmatter as fm
from ..utils.config import cfg_get
from ..utils.wiki import find_node_md
from ..utils.idf import load_idf
from ..ingest.relations_lru import list_relations, touch_relation
from .scanner import scan
from .slicing import make_slice, merge_slices


def run_query(
    ctx,
    *,
    core: list[str],
    expansion: list[str],
    top_k: int | None = None,
    include_inactive: bool = False,
    neighbors: bool = False,
) -> dict:
    """Three-layer retrieval: L1 scan + slice + score + Fast Pass.

    Returns dict with keys: related_nodes, fast_pass, total_hits,
    and optionally: body_map, list_hint, report_hint, neighbor_preview.
    """
    qcfg = ctx.config.get("query", {})
    soft = cfg_get(qcfg, "slice.soft_limit", 80)
    hard = cfg_get(qcfg, "slice.hard_limit", 150)
    radius = cfg_get(qcfg, "slice.merge_radius", 80)
    core_w = cfg_get(qcfg, "scoring.core_weight", 2000)
    exp_w = cfg_get(qcfg, "scoring.expansion_weight", 500)
    density = cfg_get(qcfg, "scoring.density_bonus", 1.5)
    top_k = top_k or cfg_get(qcfg, "top_k", 10)
    fp_k = cfg_get(qcfg, "fast_pass.k", 3.0)
    fp_low = cfg_get(qcfg, "fast_pass.low_hit", 3)
    timeout = cfg_get(qcfg, "timeout_seconds", 10)

    all_kw = core + expansion
    raw_hits = scan(ctx.page_dir, all_kw, timeout=timeout)

    # IDF weights
    idf_table = load_idf(ctx)
    idf_weight = {kw: idf_table.get(kw.lower(), (0, 0.0))[1] for kw in all_kw}

    # Group hits by file
    by_file: dict[str, list] = {}
    for kw, hits in raw_hits.items():
        for h in hits:
            by_file.setdefault(h["file"], []).append((kw, h))

    # Pre-load uid cache
    uid_cache: dict[str, dict] = {}
    for p in ctx.page_dir.rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            fd, _ = fm.parse(text)
            uid_cache[str(p)] = {
                "uid": fd.get("uid"),
                "title": fd.get("title"),
                "layer": fd.get("layer"),
                "active": fd.get("active", True),
            }
        except Exception:
            continue

    def lookup_node(file_path: str):
        return uid_cache.get(file_path)

    scored_blocks = []
    for file_path, kw_hits in by_file.items():
        node = lookup_node(file_path)
        if not node:
            continue
        if not node["active"] and not include_inactive:
            continue
        try:
            text = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        _, body = fm.parse(text)
        offset = text.find(body) if body else 0

        slices = []
        for kw, h in kw_hits:
            char_pos = _line_col_to_offset(text, h["line"], h["col"])
            if char_pos is None:
                continue
            if char_pos < offset:
                continue  # ignore frontmatter hits
            s, e, snippet = make_slice(text, char_pos, char_pos + len(h["match"]), soft, hard)
            slices.append({
                "start": s, "end": e, "text": snippet,
                "hits": {kw}, "line": h["line"],
            })

        merged = merge_slices(slices, radius, text)
        for blk in merged:
            score = _score_block(blk, core, expansion, core_w, exp_w, density, idf_weight, text)
            scored_blocks.append({
                "uid": node["uid"],
                "title": node["title"],
                "layer": node["layer"],
                "file": file_path,
                "line": blk["line"],
                "snippet": blk["text"].strip(),
                "matched": sorted(blk["hits"]),
                "score": round(score, 2),
            })

    scored_blocks.sort(key=lambda b: b["score"], reverse=True)
    top = scored_blocks[:top_k]

    # Fast Pass
    fast_pass = False
    body_map = {}
    if top:
        scores = [b["score"] for b in top]
        if len(top) <= fp_low:
            fast_pass = True
        else:
            mean = sum(scores) / len(scores)
            if scores[0] > mean * fp_k:
                fast_pass = True
        if fast_pass:
            seen = []
            for b in top:
                if b["uid"] in seen:
                    continue
                seen.append(b["uid"])
                body_map[b["uid"]] = _read_body(ctx, b["file"])
                if len(seen) >= 3:
                    break

    # L2/L3 hints
    hit_uids = [b["uid"] for b in top]
    list_hint, report_hint = _build_hints(ctx, hit_uids)

    # Neighbors
    neighbor_preview = None
    if neighbors and hit_uids:
        neighbor_preview = {}
        for uid in hit_uids[:5]:
            fm_node, _ = find_node_md(ctx, uid)
            if not fm_node:
                continue
            rels = list_relations(ctx, uid)
            neighbor_preview[uid] = rels
            for r in rels:
                touch_relation(ctx, uid, r["to_uid"])

    data = {
        "related_nodes": top,
        "fast_pass": fast_pass,
        "total_hits": len(scored_blocks),
    }
    if body_map:
        data["body_map"] = body_map
    if list_hint:
        data["list_hint"] = list_hint
    if report_hint:
        data["report_hint"] = report_hint
    if neighbor_preview is not None:
        data["neighbor_preview"] = neighbor_preview

    return data


def _score_block(blk, core, expansion, core_w, exp_w, density, idf_weight, text) -> float:
    """score = (coverage + rarity) × density_bonus."""
    snippet = blk["text"]
    core_hits = sum(snippet.lower().count(k.lower()) for k in core)
    exp_hits = sum(snippet.lower().count(k.lower()) for k in expansion)
    coverage = core_w * core_hits + exp_w * exp_hits
    rarity = sum(idf_weight.get(k, 0.0) for k in blk["hits"])
    distinct = len(blk["hits"])
    bonus = density if distinct > 1 else 1.0
    return (coverage + rarity) * bonus


def _line_col_to_offset(text: str, line: int, col: int) -> int | None:
    cur_line = 1
    offset = 0
    for ln in text.splitlines(keepends=True):
        if cur_line == line:
            return offset + col
        offset += len(ln)
        cur_line += 1
    return None


def _read_body(ctx, file_path: str) -> str:
    try:
        text = Path(file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    _, body = fm.parse(text)
    return body


def _build_hints(ctx, hit_uids: list[str]) -> tuple[list, str | None]:
    """Find L2 Lists referencing hit pages, and L3 Reports citing them."""
    if not hit_uids:
        return [], None
    hit_set = set(hit_uids)
    list_hint = []
    report_ids = []

    list_dir = ctx.list_dir
    if list_dir.is_dir():
        for p in list_dir.glob("*.md"):
            try:
                fm_dict, body = fm.parse(p.read_text(encoding="utf-8", errors="replace"))
                members = []
                if body.strip():
                    try:
                        members = yaml.safe_load(body) or []
                    except yaml.YAMLError:
                        members = []
                if any(isinstance(m, dict) and m.get("uid") in hit_set for m in members):
                    list_hint.append(fm_dict.get("uid", p.stem))
            except Exception:
                continue

    report_dir = ctx.report_dir
    if report_dir.is_dir():
        for p in report_dir.glob("*.md"):
            try:
                fm_dict, _ = fm.parse(p.read_text(encoding="utf-8", errors="replace"))
                refs = fm_dict.get("references", [])
                if any(r.get("uid") in hit_set for r in refs):
                    report_ids.append(fm_dict.get("uid", p.stem))
            except Exception:
                continue

    report_hint = None
    if report_ids:
        report_hint = f"{len(report_ids)} report(s) cite these pages: {', '.join(report_ids)}"
    return list_hint, report_hint
