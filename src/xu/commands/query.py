"""query / read / nodes commands (06-query.md).

query: three-layer retrieval. CLI does L1 (ripgrep + slice + score + Fast Pass)
and returns L2/L3 hints. Zero LLM calls (PRIN-QRY-3).
read: single-node full body, applying patches for L1 (PRIN-QRY-6).
nodes: DB metadata query (read-only, no ripgrep).
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
    raw_hits = scan(ctx.page_dir, all_kw, timeout=timeout)

    # IDF weights (PRIN-QRY-11, BAN-QRY-5: must come from IDF table)
    conn = ctx.connect()
    idf_weight = {}
    for kw in all_kw:
        row = conn.execute("SELECT weight FROM idf WHERE noun=?", (kw.lower(),)).fetchone()
        idf_weight[kw] = row["weight"] if row else 0.0

    # Group hits by file, build slices
    by_file: dict[str, list] = {}
    for kw, hits in raw_hits.items():
        for h in hits:
            by_file.setdefault(h["file"], []).append((kw, h))

    # Map md file -> uid (skip inactive nodes)
    uid_cache: dict[str, dict] = {}

    def lookup_node(file_path: str) -> dict | None:
        if file_path in uid_cache:
            return uid_cache[file_path]
        try:
            rel = str(Path(file_path).resolve().relative_to(ctx.root.resolve()))
        except ValueError:
            return None
        row = conn.execute(
            "SELECT uid, title, layer, active, node_path FROM nodes WHERE rel_md_path=?", (rel,)
        ).fetchone()
        info = dict(row) if row else None
        uid_cache[file_path] = info
        return info

    scored_blocks = []
    for file_path, kw_hits in by_file.items():
        node = lookup_node(file_path)
        if not node:
            continue
        if not node["active"] and not args.include_inactive:
            continue  # BAN-QRY-4
        try:
            text = Path(file_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        _, body = fm.parse(text)
        offset = text.find(body) if body else 0

        slices = []
        for kw, h in kw_hits:
            # locate the hit char offset within full text via line+col
            char_pos = _line_col_to_offset(text, h["line"], h["col"])
            if char_pos is None:
                continue
            if char_pos < offset:
                continue  # ignore frontmatter hits; only body counts (PRIN-QRY-7)
            s, e, snippet = make_slice(text, char_pos, char_pos + len(h["match"]), soft, hard)
            slices.append({"start": s, "end": e, "text": snippet,
                           "hits": {kw}, "line": h["line"]})

        merged = merge_slices(slices, radius, text)
        for blk in merged:
            score = _score_block(blk, core, expansion, core_w, exp_w, density, idf_weight, text)
            scored_blocks.append({
                "uid": node["uid"], "title": node["title"], "layer": node["layer"],
                "node_path": node["node_path"], "file": file_path,
                "line": blk["line"], "snippet": blk["text"].strip(),
                "matched": sorted(blk["hits"]), "score": round(score, 2),
            })

    conn_for_hints = conn
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
                body_map[b["uid"]] = _read_body(ctx, b["file"])
                if len(seen) >= 3:
                    break

    # L2/L3 hints (PRIN-QRY-1) + neighbors (M3)
    hit_uids = [b["uid"] for b in top]
    list_hint, report_hint = _build_hints(ctx, hit_uids)

    neighbor_preview = None
    if args.neighbors and hit_uids:
        neighbor_preview = {}
        for uid in hit_uids[:5]:
            rels = list_relations(conn_for_hints, uid)
            neighbor_preview[uid] = rels
            # query hit touches relations forward (PRIN-QRY-13)
            for r in rels:
                touch_relation(conn_for_hints, uid, r["to_uid"])
        conn_for_hints.commit()

    conn.close()

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

    hints = []
    if top:
        hints.append("read --uid <uid> to fetch full body")
        if list_hint:
            hints.append("list show <uid> for L2 comparison")
        if report_hint:
            hints.append("report show <uid> for L3 conclusion + evidence")
        hints.append("consider: propose report create if hits form an evidence chain (PRIN-CR-1 primary bias)")
        hints.append("consider: propose list create if hits share a comparable dimension (PRIN-CR-1 secondary, opportunistic)")
    if not top:
        hints.append("no hits; try different keywords or check ingest")

    status = success if top else warning
    return status(data, f"{len(scored_blocks)} block(s) across {len(by_file)} file(s); "
                        f"fast_pass={fast_pass}", hints=hints)


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
    """Find L2 Lists referencing hit pages, and L3 Reports citing them — via filesystem scan."""
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


def cmd_read(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    conn = ctx.connect()
    try:
        row = conn.execute("SELECT * FROM nodes WHERE uid=?", (args.uid,)).fetchone()
        if row:
            node = dict(row)
            body = ""
            if node["rel_md_path"]:
                md_path = ctx.root / node["rel_md_path"]
                if md_path.exists():
                    text = md_path.read_text(encoding="utf-8", errors="replace")
                    _, body = fm.parse(text)
            else:
                body = ""
            patches = conn.execute(
                "SELECT version, op, author, created_at FROM patches WHERE page_uid=? ORDER BY version",
                (args.uid,),
            ).fetchall()
            return success(
                {"uid": node["uid"], "title": node["title"], "layer": node["layer"],
                 "content_type": node["content_type"], "node_path": node["node_path"],
                 "active": bool(node["active"]), "body": body,
                 "patch_versions": [dict(p) for p in patches]},
                f"read {node['layer']} node {args.uid}",
            )
    finally:
        conn.close()

    # L2/L3: not in SQLite — look up via filesystem
    found = find_node_md(ctx, args.uid)
    if found:
        fm_dict, body = found
        return success(
            {"uid": fm_dict.get("uid"), "title": fm_dict.get("title"),
             "layer": fm_dict.get("layer"), "content_type": fm_dict.get("content_type", "article"),
             "node_path": "", "active": True, "body": body,
             "patch_versions": []},
            f"read {fm_dict.get('layer')} node {args.uid}",
        )

    return error(f"node not found: {args.uid}", "NodeNotFound")


def cmd_nodes(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    conn = ctx.connect()
    try:
        sql = "SELECT uid, layer, content_type, title, node_path, active, created_at FROM nodes"
        clauses = []
        params = []
        if args.layer:
            clauses.append("layer=?")
            params.append(args.layer)
        if not args.include_inactive:
            clauses.append("active=1")
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC"
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        return success({"nodes": rows, "count": len(rows)}, f"{len(rows)} node(s)")
    finally:
        conn.close()
