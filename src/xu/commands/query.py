"""query / expand / read / nodes commands (06-query.md).

query: CLI searches keywords → returns top N indexed blocks (uid/title/layer/position/text).
       LLM decides next step (conclude / Path A new keywords / Path B follow relations).
expand: CLI fetches body + relations for specific UIDs (Path B).
read: single-node full body, applying patches.
nodes: DB metadata query (read-only, no ripgrep).
CLI never generates summaries (PRIN-QRY-15).
"""
from __future__ import annotations

import yaml
from pathlib import Path

from ..ingest.relations_lru import list_relations, touch_relation
from ..query.scanner import scan
from ..query.slicing import make_slice, merge_slices
from ..utils import frontmatter as fm
from ..utils.config import cfg_get
from ..utils.response import error, success, warning
from ..utils.wiki import find_node_md, resolve_wiki
from ..utils.idf import load_idf


def _split_kw(s: str) -> list[str]:
    return [k.strip() for k in s.split(",") if k.strip()]


def cmd_query(args) -> dict:
    """Search wiki: return top N blocks with full index (uid/title/layer/position/text).

    LLM generates keywords → CLI searches → LLM picks UIDs for expand (Path B).
    """
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    keywords = _split_kw(args.keywords)
    if not keywords:
        return error("provide --keywords", "NoKeywords")

    qcfg = ctx.config.get("query", {})
    soft = cfg_get(qcfg, "slice.soft_limit", 80)
    hard = cfg_get(qcfg, "slice.hard_limit", 150)
    radius = cfg_get(qcfg, "slice.merge_radius", 80)
    core_w = cfg_get(qcfg, "scoring.core_weight", 2000)
    density = cfg_get(qcfg, "scoring.density_bonus", 1.5)
    top_blocks = cfg_get(qcfg, "blocks", 50)
    timeout = cfg_get(qcfg, "timeout_seconds", 10)

    raw_hits = scan(ctx.nodes_dir, keywords, timeout=timeout)

    idf_table = load_idf(ctx)
    idf_weight = {}
    for kw in keywords:
        freq, weight = idf_table.get(kw.lower(), (0, 0.0))
        idf_weight[kw] = weight

    by_file: dict[str, list] = {}
    for kw, hits in raw_hits.items():
        for h in hits:
            by_file.setdefault(h["file"], []).append((kw, h))

    uid_cache: dict[str, dict] = {}
    for subdir in (ctx.page_dir, ctx.entity_dir, ctx.list_dir, ctx.report_dir):
        if not subdir.is_dir():
            continue
        for p in subdir.glob("*.md"):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                fd, _ = fm.parse(text)
                uid_cache[str(p)] = {
                    "uid": fd.get("uid"),
                    "title": fd.get("title"),
                    "layer": fd.get("layer", "Page"),
                    "active": fd.get("active", True),
                    "node_path": fd.get("node_path", ""),
                }
            except Exception:
                continue

    scored_blocks = []
    for file_path, kw_hits in by_file.items():
        node = uid_cache.get(file_path)
        if not node:
            continue
        if not node["active"] and not args.include_inactive:
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
                continue
            s, e, snippet = make_slice(text, char_pos, char_pos + len(h["match"]), soft, hard)
            slices.append({"start": s, "end": e, "text": snippet,
                           "hits": {kw}, "line": h["line"]})

        merged = merge_slices(slices, radius, text)
        for blk in merged:
            score = _score_block(blk, keywords, core_w, density, idf_weight, text)
            scored_blocks.append({
                "uid": node["uid"],
                "title": node["title"],
                "layer": node["layer"],
                "node_path": node["node_path"],
                "file": file_path,
                "line": blk["line"],
                "text": blk["text"].strip(),
                "matched": sorted(blk["hits"]),
                "score": round(score, 2),
            })

    scored_blocks.sort(key=lambda b: b["score"], reverse=True)
    top = scored_blocks[:top_blocks]

    return success(
        {
            "blocks": top,
            "total_hits": len(scored_blocks),
            "block_count": len(top),
        },
        f"{len(scored_blocks)} block(s); returning top {len(top)}",
    )


def cmd_expand(args) -> dict:
    """Fetch body + relations for specific UIDs. Used by Path B.

    LLM picks UIDs → CLI returns full body text (no summary) + relations list.
    """
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    uids = _split_kw(args.uids)
    if not uids:
        return error("provide --uids", "NoUIDs")

    nodes_root = ctx.nodes_dir
    result: dict = {}

    for uid in uids:
        for p in nodes_root.rglob("*.md"):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                fd, body = fm.parse(text)
                if fd.get("uid") != uid:
                    continue
                rels = list_relations(fd, uid)
                for r in rels:
                    touch_relation(fd, uid, r["to_uid"])
                _write_node_fm(ctx, uid, fd)
                result[uid] = {
                    "uid": uid,
                    "title": fd.get("title", ""),
                    "layer": fd.get("layer", "Page"),
                    "body": body,
                    "relations": rels,
                }
                break
            except Exception:
                continue
        if uid not in result:
            result[uid] = {"uid": uid, "error": "not found"}

    found = {u: v for u, v in result.items() if "error" not in v}
    return success(
        {"nodes": result, "found": len(found), "requested": len(uids)},
        f"expanded {len(found)}/{len(uids)} UID(s)",
    )


def _score_block(blk, keywords, core_w, density, idf_weight, text) -> float:
    """score = (coverage + rarity) × density_bonus (PRIN-QRY-10)."""
    snippet = blk["text"]
    hits = sum(snippet.lower().count(k.lower()) for k in keywords)
    coverage = core_w * hits
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


def _write_node_fm(ctx, uid: str, fm_node: dict) -> None:
    """Find node .md by uid and rewrite its frontmatter, preserving body."""
    nodes_root = ctx.nodes_dir
    if not nodes_root.is_dir():
        return
    for p in nodes_root.rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            parsed, body = fm.parse(text)
            if parsed.get("uid") == uid:
                p.write_text(fm.render(fm_node, body), encoding="utf-8")
                return
        except Exception:
            continue


def cmd_read(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    found = find_node_md(ctx, args.uid)
    if found:
        fm_dict, body = found
        return success(
            {"uid": fm_dict.get("uid"), "title": fm_dict.get("title"),
             "layer": fm_dict.get("layer"), "content_type": fm_dict.get("content_type", "article"),
             "node_path": fm_dict.get("node_path", ""), "active": fm_dict.get("active", True),
             "body": body, "patch_versions": []},
            f"read {fm_dict.get('layer')} node {args.uid}",
        )
    return error(f"node not found: {args.uid}", "NodeNotFound")


def cmd_nodes(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    nodes_root = ctx.nodes_dir
    results = []
    if nodes_root.is_dir():
        for p in nodes_root.rglob("*.md"):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                fm_dict, _ = fm.parse(text)
                if args.layer and fm_dict.get("layer") != args.layer:
                    continue
                if not args.include_inactive and not fm_dict.get("active", True):
                    continue
                results.append({
                    "uid": fm_dict.get("uid"),
                    "title": fm_dict.get("title"),
                    "layer": fm_dict.get("layer"),
                    "content_type": fm_dict.get("content_type", "article"),
                    "node_path": fm_dict.get("node_path", ""),
                    "active": fm_dict.get("active", True),
                    "created_at": fm_dict.get("created_at", 0),
                })
            except Exception:
                continue
    results.sort(key=lambda n: n.get("created_at", 0), reverse=True)
    return success({"nodes": results, "count": len(results)}, f"{len(results)} node(s)")
