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
from ..utils.wiki import find_node_md, resolve_wiki, write_node_frontmatter



def _split_kw(s: str) -> list[str]:
    return [k.strip() for k in s.split(",") if k.strip()]


def _build_reflection(ctx, keywords: list[str], top_blocks: list[dict]) -> dict:
    """Search derived layers for existing Entity/List/Report nodes matching keywords.

    Mirrors Rust branch reflection logic (query.rs build_reflection).
    Returns suggestions for Entity extraction, List creation, and Report creation.
    """
    timeout = cfg_get(ctx.config.get("query", {}), "timeout_seconds", 10)

    existing_entities: list[dict] = []
    existing_lists: list[dict] = []
    existing_reports: list[dict] = []

    for subdir, collection in [
        (ctx.entity_dir, existing_entities),
        (ctx.list_dir, existing_lists),
        (ctx.report_dir, existing_reports),
    ]:
        if not subdir.is_dir():
            continue
        hits = scan(subdir, keywords, timeout=timeout)
        seen: set[str] = set()
        for kw, kw_hits in hits.items():
            for h in kw_hits:
                try:
                    text = Path(h["file"]).read_text(encoding="utf-8", errors="replace")
                    fd, _ = fm.parse(text)
                    uid = fd.get("uid", "")
                    if uid in seen:
                        continue
                    seen.add(uid)
                    collection.append({
                        "uid": uid,
                        "title": fd.get("title", ""),
                    })
                except Exception:
                    continue

    has_pages = any(b["layer"] == "Page" for b in top_blocks)

    if has_pages and not existing_entities:
        hint = f"{len(top_blocks)} page(s) found – consider extracting entities with: xu entity-create --wiki <w> --title <name> --source-page <uid>"
    elif len(top_blocks) >= 2 and not existing_lists:
        hint = "multiple results share a theme – consider: xu list-create"
    else:
        hint = ""

    return {
        "existing_entities": existing_entities,
        "existing_lists": existing_lists,
        "existing_reports": existing_reports,
        "suggest_extract_entities": has_pages and len(existing_entities) == 0,
        "suggest_create_list": len(top_blocks) >= 2 and len(existing_lists) == 0,
        "suggest_create_report": len(top_blocks) >= 3 and len(existing_reports) == 0,
        "hint": hint,
    }


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
    slice_chars = cfg_get(qcfg, "slice.chars", 50)
    radius = cfg_get(qcfg, "slice.merge_radius", 80)
    top_blocks = cfg_get(qcfg, "blocks", 50)
    uid_batch = cfg_get(qcfg, "uid_batch", 30)
    max_rounds = cfg_get(qcfg, "max_rounds", 5)
    query_max_expand = cfg_get(qcfg, "query_max_expand", 10)
    timeout = cfg_get(qcfg, "timeout_seconds", 10)

    raw_hits = scan(ctx.nodes_dir, keywords, timeout=timeout)

    by_file: dict[str, list] = {}
    for kw, hits in raw_hits.items():
        for h in hits:
            by_file.setdefault(h["file"], []).append((kw, h))

    uid_cache: dict[str, dict] = {}
    for subdir in (ctx.page_dir, ctx.entity_dir, ctx.list_dir, ctx.report_dir):
        if not subdir.is_dir():
            continue
        for p in subdir.rglob("*.md"):
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
    layer_bonus = {"Page": 0, "Entity": 2, "List": 1, "Report": 3}

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
        body_offset = text.find(body) if body else 0

        title_hits = sum(1 for _, h in kw_hits
                         if _line_col_to_offset(text, h["line"], h["col"]) is not None
                         and _line_col_to_offset(text, h["line"], h["col"]) < body_offset)
        total_hits = len(kw_hits)
        body_hit_count = total_hits - title_hits

        slices = []
        for kw, h in kw_hits:
            char_pos = _line_col_to_offset(text, h["line"], h["col"])
            if char_pos is None:
                continue
            if char_pos < body_offset:
                continue
            s, e, snippet = make_slice(text, char_pos, char_pos + len(h["match"]),
                                        slice_chars, slice_chars)
            slices.append({"start": s, "end": e, "text": snippet,
                           "hits": {kw}, "line": h["line"]})

        merged = merge_slices(slices, radius, text)
        layer = node["layer"]
        bonus = layer_bonus.get(layer, 0)
        for blk in merged:
            score = _score_block(blk, keywords, title_hits, body_hit_count, bonus)
            scored_blocks.append({
                "uid": node["uid"],
                "title": node["title"],
                "layer": layer,
                "node_path": node["node_path"],
                "file": file_path,
                "line": blk["line"],
                "text": blk["text"].strip(),
                "matched": sorted(blk["hits"]),
                "score": round(score, 2),
            })

    scored_blocks.sort(key=lambda b: b["score"], reverse=True)
    top = scored_blocks[:top_blocks]

    reflection = _build_reflection(ctx, keywords, top)

    return success(
        {
            "blocks": top,
            "total_hits": len(scored_blocks),
            "block_count": len(top),
            "uid_batch": uid_batch,
            "max_rounds": max_rounds,
            "query_max_expand": query_max_expand,
            "reflection": reflection,
        },
        f"{len(scored_blocks)} block(s); returning top {len(top)}",
        hints=[
            f"pick up to {uid_batch} UIDs from blocks, call xu expand --wiki {args.wiki} --uids <uids> (max {query_max_expand} per call)",
            "Path A: re-call xu query with new keywords",
            "Path B: expand UIDs to traverse relation edges",
        ],
    )


def cmd_expand(args) -> dict:
    """Fetch body + relations for specific UIDs. Used by Path B.

    LLM picks UIDs → CLI returns full body text (no summary) + filtered relations list.
    --relation-names filters to specific directions; --limit caps total relations per UID.
    """
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    uids = _split_kw(args.uids)
    if not uids:
        return error("provide --uids", "NoUIDs")

    qcfg = ctx.config.get("query", {})
    query_max_expand = cfg_get(qcfg, "query_max_expand", 10)
    if len(uids) > query_max_expand:
        uids = uids[:query_max_expand]

    rel_names_filter = None
    if getattr(args, "relation_names", None):
        rel_names_filter = set(_split_kw(args.relation_names))
    limit = getattr(args, "limit", None)

    nodes_root = ctx.nodes_dir
    result: dict = {}

    for uid in uids:
        for p in nodes_root.rglob("*.md"):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                fd, body = fm.parse(text)
                if fd.get("uid") != uid:
                    continue
                all_rels = list_relations(fd, uid)
                if rel_names_filter:
                    all_rels = [r for r in all_rels if r.get("relation_name") in rel_names_filter]
                if limit:
                    all_rels = all_rels[:limit]
                for r in all_rels:
                    touch_relation(fd, uid, r["to_uid"])
                write_node_frontmatter(ctx, uid, fd)
                result[uid] = {
                    "uid": uid,
                    "title": fd.get("title", ""),
                    "layer": fd.get("layer", "Page"),
                    "content_type": fd.get("content_type", "article"),
                    "body": body,
                    "relations": all_rels,
                }
                break
            except Exception:
                continue
        if uid not in result:
            result[uid] = {"uid": uid, "error": "not found"}

    found = {u: v for u, v in result.items() if "error" not in v}
    max_rounds = cfg_get(qcfg, "max_rounds", 5)
    return success(
        {"nodes": result, "found": len(found), "requested": len(uids)},
        f"expanded {len(found)}/{len(uids)} UID(s) (max {query_max_expand} per call, max {max_rounds} rounds total)",
        hints=[f"pick UIDs from these bodies and expand again (max {query_max_expand} per call); Path B: use --relation-names to narrow direction"],
    )


def _score_block(blk, keywords, title_hits, body_hit_count, layer_bonus) -> float:
    """score = title_hits × 5 + body_hit_count + layer_bonus (additive, small)."""
    return title_hits * 5 + body_hit_count + layer_bonus


def _line_col_to_offset(text: str, line: int, col: int) -> int | None:
    cur_line = 1
    offset = 0
    for ln in text.splitlines(keepends=True):
        if cur_line == line:
            return offset + col
        offset += len(ln)
        cur_line += 1
    return None


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
