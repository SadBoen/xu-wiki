"""query / read / nodes commands (06-query.md).

query: three-layer retrieval. CLI does L1 (SQLite scan + slice + score + Fast Pass)
and returns L2/L3 hints. Zero LLM calls (PRIN-QRY-3).
read: single-node full body, from SQLite nodes.body (PRIN-QRY-6).
nodes: DB metadata query (read-only, SQLite only).
"""
from __future__ import annotations

import yaml

from ..ingest.relations_lru import list_relations, touch_relation
from ..query.scanner import scan
from ..query.slicing import make_slice, merge_slices
from ..utils.config import cfg_get
from ..utils.response import error, success, warning
from ..utils.wiki import resolve_wiki, WikiContext
from ..utils.idf import load_idf


def _split_kw(s: str) -> list[str]:
    return [k.strip() for k in s.split(",") if k.strip()]


def cmd_query(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    core = _split_kw(args.core)
    expansion = _split_kw(args.expansion)
    if not core and not expansion:
        return error("provide --core and/or --expansion keywords", "NoKeywords",
                     hints=["Agent does semantic grading; CLI ranks deterministically (PRIN-QRY-2)"])

    qcfg = ctx.config.get("query", {})
    soft = cfg_get(qcfg, "slice.soft_limit", 80)
    hard = cfg_get(qcfg, "slice.hard_limit", 150)
    radius = cfg_get(qcfg, "slice.merge_radius", 80)
    core_w = cfg_get(qcfg, "scoring.core_weight", 2000)
    exp_w = cfg_get(qcfg, "scoring.expansion_weight", 500)
    density = cfg_get(qcfg, "scoring.density_bonus", 1.5)
    top_k = args.top_k or cfg_get(qcfg, "top_k", 10)
    fp_k = cfg_get(qcfg, "fast_pass.k", 3.0)
    fp_low = cfg_get(qcfg, "fast_pass.low_hit", 3)
    timeout = cfg_get(qcfg, "timeout_seconds", 10)

    all_kw = core + expansion

    # SQLite-first scan (T6): scan ctx, not ctx.page_dir
    raw_hits = scan(ctx, all_kw, timeout=timeout)

    # IDF weights (PRIN-QRY-11)
    idf_table = load_idf(ctx)
    idf_weight = {}
    for kw in all_kw:
        freq, weight = idf_table.get(kw.lower(), (0, 0.0))
        idf_weight[kw] = weight

    # Group hits by uid (scanner now returns uid, not file path)
    by_uid: dict[str, list] = {}
    for kw, hits in raw_hits.items():
        for h in hits:
            by_uid.setdefault(h["uid"], []).append((kw, h))

    # uid -> node metadata cache from SQLite
    uid_cache: dict[str, dict] = _load_uid_cache(ctx)

    scored_blocks = []
    for uid, kw_hits in by_uid.items():
        node = uid_cache.get(uid)
        if not node:
            continue
        if not node["active"] and not args.include_inactive:
            continue
        body = node["body"]
        if not body:
            continue

        slices = []
        for kw, h in kw_hits:
            char_pos = h["char_pos"]
            s, e, snippet = make_slice(body, char_pos, char_pos + len(h["match"]), soft, hard)
            slices.append({"start": s, "end": e, "text": snippet, "hits": {kw}})

        merged = merge_slices(slices, radius, body)
        for blk in merged:
            score = _score_block(blk, core, expansion, core_w, exp_w, density, idf_weight, body)
            scored_blocks.append({
                "uid": node["uid"],
                "title": node["title"],
                "layer": node["layer"],
                "snippet": blk["text"].strip(),
                "matched": sorted(blk["hits"]),
                "score": round(score, 2),
            })

    scored_blocks.sort(key=lambda b: b["score"], reverse=True)
    top = scored_blocks[:top_k]

    # Fast Pass (PRIN-QRY-12, CONST-QRY-6)
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
                body_map[b["uid"]] = uid_cache.get(b["uid"], {}).get("body", "")
                if len(seen) >= 3:
                    break

    # L2/L3 hints (PRIN-QRY-1) + neighbors
    hit_uids = [b["uid"] for b in top]
    list_hint, report_hint, entity_hint = _build_hints(ctx, hit_uids)

    neighbor_preview = None
    if args.neighbors and hit_uids:
        neighbor_preview = {}
        for uid in hit_uids[:5]:
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
    if entity_hint:
        data["entity_hint"] = entity_hint
    if neighbor_preview is not None:
        data["neighbor_preview"] = neighbor_preview

    hints = []
    if top:
        hints.append("read --uid <uid> to fetch full body")
        if list_hint:
            hints.append("list show <uid> for L2 comparison")
        if report_hint:
            hints.append("report show <uid> for L3 conclusion + evidence")
        if entity_hint:
            hints.append("entity show <uid> for L2 entity attributes")
        hints.append("run post-query reflection (PRIN-CR-1): query for similar Report first, extend existing if found; otherwise LLM decides autonomously (no user approval needed)")
        hints.append("post-query reflection (PRIN-CR-1): query for similar List only if hits share a comparable dimension and no similar exists (secondary, opportunistic)")
    if not top:
        hints.append("no hits; try different keywords or check ingest")

    status = success if top else warning
    return status(data, f"{len(scored_blocks)} block(s) across {len(by_uid)} uid(s); "
                        f"fast_pass={fast_pass}", hints=hints)


def _load_uid_cache(ctx: WikiContext) -> dict[str, dict]:
    """Load uid -> {title, layer, active, body} from SQLite nodes table.

    For DB-only nodes (rel_md_path=NULL, body IS NOT NULL): body is in SQLite.
    For legacy nodes (rel_md_path!=NULL, body IS NULL): body is still in .md files;
    we read it from the filesystem as a fallback so search still works.
    """
    cache: dict[str, dict] = {}
    conn = ctx.connect()
    try:
        rows = conn.execute(
            "SELECT uid, title, layer, active, rel_md_path, body "
            "FROM nodes WHERE layer='Page' AND active=1"
        ).fetchall()
        for row in rows:
            body = row["body"]
            # Fallback: if body is NULL in DB, try reading from .md file
            if not body and row["rel_md_path"]:
                md_path = ctx.root / row["rel_md_path"]
                try:
                    text = md_path.read_text(encoding="utf-8", errors="replace")
                    from ..utils.frontmatter import parse as fm_parse
                    _, body = fm_parse(text)
                except Exception:
                    body = ""
            cache[row["uid"]] = {
                "title": row["title"],
                "layer": row["layer"],
                "active": row["active"],
                "body": body or "",
            }
    finally:
        conn.close()
    return cache


def _build_hints(ctx: WikiContext, hit_uids: list[str]) -> tuple[list, str | None, str | None]:
    """Find L2 Lists that have hit pages as members, L3 Reports citing them, and L2 Entities — via SQLite."""
    if not hit_uids:
        return [], None, None
    hit_set = set(hit_uids)
    list_hint = []
    report_ids = []

    conn = ctx.connect()
    try:
        # L2: list_members table
        rows = conn.execute(
            "SELECT DISTINCT list_uid FROM list_members WHERE member_uid IN ({})".format(
                ",".join("?" * len(hit_uids))
            ),
            hit_uids,
        ).fetchall()
        for row in rows:
            list_hint.append(row["list_uid"])

        # L3: evidence table
        rows = conn.execute(
            "SELECT DISTINCT report_uid FROM evidence WHERE ref_uid IN ({})".format(
                ",".join("?" * len(hit_uids))
            ),
            hit_uids,
        ).fetchall()
        for row in rows:
            report_ids.append(row["report_uid"])
    finally:
        conn.close()

    report_hint = None
    if report_ids:
        report_hint = f"{len(report_ids)} report(s) cite these pages: {', '.join(report_ids)}"

    # L2 Entity: multiple distinct titles suggest creating an Entity aggregation
    entity_hint = _build_entity_hint(ctx, hit_uids)

    return list_hint, report_hint, entity_hint


def _build_entity_hint(ctx: WikiContext, hit_uids: list[str]) -> str | None:
    """Suggest Entity creation when query hits multiple distinct entity-like nodes."""
    if len(hit_uids) < 2:
        return None

    conn = ctx.connect()
    try:
        rows = conn.execute(
            "SELECT DISTINCT title FROM nodes WHERE uid IN ({}) AND layer='Page'".format(
                ",".join("?" * len(hit_uids))
            ),
            hit_uids,
        ).fetchall()
    finally:
        conn.close()

    if len(rows) < 2:
        return None

    # Heuristic: if hits share a common pattern or are about the same topic,
    # suggest creating an Entity to aggregate
    titles = [r["title"] for r in rows]
    # Simple heuristic: if titles have significant overlap, suggest Entity
    return f"这个查询涉及多个实体（{', '.join(titles[:3])}{'...' if len(titles) > 3 else ''}），可以创建 Entity 页面聚合相关信息"


def _score_block(blk, core, expansion, core_w, exp_w, density, idf_weight, text) -> float:
    """score = (coverage + rarity) × density_bonus (PRIN-QRY-10)."""
    snippet = blk["text"]
    core_hits = sum(snippet.lower().count(k.lower()) for k in core)
    exp_hits = sum(snippet.lower().count(k.lower()) for k in expansion)
    coverage = core_w * core_hits + exp_w * exp_hits
    rarity = sum(idf_weight.get(k, 0.0) for k in blk["hits"])
    distinct = len(blk["hits"])
    bonus = density if distinct > 1 else 1.0
    return (coverage + rarity) * bonus


def cmd_read(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    conn = ctx.connect()
    try:
        row = conn.execute(
            "SELECT uid, title, layer, content_type, active, body "
            "FROM nodes WHERE uid=?", (args.uid,)
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return error(f"node not found: {args.uid}", "NodeNotFound")

    return success({
        "uid": row["uid"],
        "title": row["title"],
        "layer": row["layer"],
        "content_type": row["content_type"] or "article",
        "active": bool(row["active"]),
        "body": row["body"] or "",
        "patch_versions": [],
    }, f"read {row['layer']} node {args.uid}")


def cmd_nodes(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    conn = ctx.connect()
    try:
        query = "SELECT uid, title, layer, content_type, active, created_at FROM nodes"
        conditions = []
        params = []
        if args.layer:
            conditions.append("layer = ?")
            params.append(args.layer)
        if not args.include_inactive:
            conditions.append("active = 1")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC"

        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    results = [
        {
            "uid": row["uid"],
            "title": row["title"],
            "layer": row["layer"],
            "content_type": row["content_type"] or "article",
            "active": bool(row["active"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]
    return success({"nodes": results, "count": len(results)}, f"{len(results)} node(s)")
