"""query / read / nodes commands.

query: keyword scan → slice → merge → score → return snippets.
  Zero LLM calls. Scoring = core_hits×3 + expansion_hits×1.
read: single-node full body from SQLite.
nodes: DB metadata query (read-only).
"""
from __future__ import annotations

import yaml

from ..ingest.relations_lru import list_relations, touch_relation
from ..query.scanner import scan
from ..query.slicing import make_slice, merge_slices
from ..utils.config import cfg_get
from ..utils.response import error, success, warning
from ..utils.wiki import resolve_wiki, WikiContext


def _split_kw(s: str) -> list[str]:
    return [k.strip() for k in s.split(",") if k.strip()]


def _score_snippet(snippet: str, core: list[str], expansion: list[str]) -> int:
    """Simple hit-count scoring: core×3 + expansion×1."""
    lower = snippet.lower()
    core_hits = sum(lower.count(k.lower()) for k in core)
    exp_hits = sum(lower.count(k.lower()) for k in expansion)
    return core_hits * 3 + exp_hits


def cmd_query(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    core = _split_kw(args.core)
    expansion = _split_kw(args.expansion)
    if not core and not expansion:
        return error("provide --core and/or --expansion keywords", "NoKeywords",
                     hints=["Agent grades keywords from user intent; CLI only matches"])

    qcfg = ctx.config.get("query", {})
    snippet_radius = cfg_get(qcfg, "snippet_radius", 50)
    merge_radius = cfg_get(qcfg, "merge_radius", 80)
    snippet_max = args.top_k or cfg_get(qcfg, "snippet_max", 50)

    all_kw = core + expansion

    # Scan node_page.body for keyword hits
    raw_hits = scan(ctx, all_kw)

    # Load uid → {title, layer, body} cache
    uid_cache = _load_uid_cache(ctx)

    # Group hits by uid, score, collect snippets
    scored_blocks = []
    for kw, hits in raw_hits.items():
        for h in hits:
            uid = h["uid"]
            node = uid_cache.get(uid)
            if not node:
                continue
            body = node.get("body", "")
            if not body:
                continue

            cp = h["char_pos"]
            match_len = len(h["match"])
            # Take snippet_radius chars before and after the match
            start = max(0, cp - snippet_radius)
            end = min(len(body), cp + match_len + snippet_radius)
            snippet = body[start:end]

            score = _score_snippet(snippet, core, expansion)
            if score == 0:
                continue

            scored_blocks.append({
                "uid": uid,
                "title": node["title"],
                "layer": node["layer"],
                "score": score,
                "snippet": snippet.strip(),
                "matched": [kw],
            })

    # Merge nearby blocks within same uid (distance < merge_radius)
    merged = _merge_by_uid(scored_blocks, merge_radius)

    # Sort by score desc, take top snippet_max
    merged.sort(key=lambda b: b["score"], reverse=True)
    top = merged[:snippet_max]

    # L2/L3 hints
    hit_uids = list({b["uid"] for b in top})
    list_hint, report_hint = _build_hints(ctx, hit_uids)

    # Neighbors if requested
    neighbor_preview = None
    if getattr(args, "neighbors", False) and hit_uids:
        neighbor_preview = {}
        for uid in hit_uids[:5]:
            rels = list_relations(ctx, uid)
            neighbor_preview[uid] = rels
            for r in rels:
                touch_relation(ctx, uid, r["to_uid"])

    data = {
        "related_nodes": top,
        "total_hits": len(merged),
    }
    if list_hint:
        data["list_hint"] = list_hint
    if report_hint:
        data["report_hint"] = report_hint
    if neighbor_preview is not None:
        data["neighbor_preview"] = neighbor_preview

    hints = []
    if top:
        hints.append("read --uid <uid> to fetch full body if needed")
        if list_hint:
            hints.append("list show <uid> for L2 comparison")
        if report_hint:
            hints.append("report show <uid> for L3 conclusion")
    if not top:
        hints.append("no hits; try different keywords")

    status_fn = success if top else warning
    return status_fn(data, f"{len(top)} snippet(s) from {len(hit_uids)} node(s)",
                     hints=hints)


def _merge_by_uid(blocks: list[dict], radius: int) -> list[dict]:
    """Within each uid, merge blocks whose start positions are close."""
    if not blocks:
        return []
    # Group by uid, keeping original order
    by_uid: dict[str, list[dict]] = {}
    for b in blocks:
        by_uid.setdefault(b["uid"], []).append(b)

    merged = []
    for uid, blks in by_uid.items():
        blks.sort(key=lambda x: x.get("pos", 0) if "pos" in x else 0)
        if not blks:
            continue
        cur = dict(blks[0])
        cur["matched"] = list(cur.get("matched", []))
        for nxt in blks[1:]:
            # Simple merge: concatenate snippets if they overlap or are close
            cur_snippet = cur["snippet"]
            nxt_snippet = nxt["snippet"]
            # If they share keywords and are from the same uid, merge
            cur["snippet"] = cur_snippet + "\n..." + nxt_snippet
            cur["score"] = max(cur["score"], nxt["score"])
            cur["matched"].extend(nxt.get("matched", []))
        cur["matched"] = list(set(cur["matched"]))
        merged.append(cur)
    return merged


def _load_uid_cache(ctx: WikiContext) -> dict[str, dict]:
    """Load uid -> {title, layer, body} from node_page."""
    cache: dict[str, dict] = {}
    conn = ctx.connect()
    try:
        rows = conn.execute(
            "SELECT uid, title, body FROM node_page WHERE active=1"
        ).fetchall()
        for row in rows:
            cache[row["uid"]] = {
                "title": row["title"],
                "layer": "Page",
                "body": row["body"] or "",
            }
    finally:
        conn.close()
    return cache


def _build_hints(ctx: WikiContext, hit_uids: list[str]) -> tuple[list, str | None]:
    """Find Lists/Reports referencing hit pages via node_derived."""
    if not hit_uids:
        return [], None
    list_hint = []
    report_ids = []

    conn = ctx.connect()
    try:
        # Scan node_derived body for UID references
        rows = conn.execute(
            "SELECT uid, title, layer, body FROM node_derived"
        ).fetchall()
        for row in rows:
            body = row["body"] or ""
            for uid in hit_uids:
                if uid in body:
                    if row["layer"] == "List":
                        list_hint.append({"uid": row["uid"], "title": row["title"]})
                    elif row["layer"] == "Report":
                        report_ids.append(row["uid"])
                    break
    finally:
        conn.close()

    report_hint = None
    if report_ids:
        report_hint = f"{len(report_ids)} report(s) cite these pages: {', '.join(report_ids)}"

    return list_hint, report_hint


def cmd_read(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    conn = ctx.connect()
    try:
        # Try node_page first
        row = conn.execute(
            "SELECT uid, title, content_type, active, body FROM node_page WHERE uid=?",
            (args.uid,)
        ).fetchone()
        layer = "Page"
        if not row:
            row = conn.execute(
                "SELECT uid, title, layer, active, body FROM node_derived WHERE uid=?",
                (args.uid,)
            ).fetchone()
            layer = row["layer"] if row else "Page"
    finally:
        conn.close()

    if not row:
        return error(f"node not found: {args.uid}", "NodeNotFound")

    return success({
        "uid": row["uid"],
        "title": row["title"],
        "layer": layer,
        "content_type": row["content_type"] if "content_type" in row.keys() else "article",
        "active": bool(row["active"]),
        "body": row["body"] or "",
    }, f"read {layer} node {args.uid}")


def cmd_nodes(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    conn = ctx.connect()
    try:
        results = []
        # node_page
        rows = conn.execute(
            "SELECT uid, title, 'Page' as layer, content_type, active, created_at "
            "FROM node_page WHERE active=1 ORDER BY created_at DESC"
        ).fetchall()
        for row in rows:
            results.append({
                "uid": row["uid"], "title": row["title"], "layer": "Page",
                "content_type": row["content_type"] or "article",
                "active": bool(row["active"]), "created_at": row["created_at"],
            })
        # node_derived
        rows = conn.execute(
            "SELECT uid, title, layer, active, created_at FROM node_derived "
            "WHERE 1=1 ORDER BY created_at DESC"
        ).fetchall()
        for row in rows:
            results.append({
                "uid": row["uid"], "title": row["title"], "layer": row["layer"],
                "content_type": "article",
                "active": bool(row["active"]), "created_at": row["created_at"],
            })
    finally:
        conn.close()

    return success({"nodes": results, "count": len(results)},
                   f"{len(results)} node(s)")
