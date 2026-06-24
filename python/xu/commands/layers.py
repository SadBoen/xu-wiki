"""L2 Node_List + L3 Node_Report — DB-only upper layers (01-wiki-architecture.md).

L2 List: comparison/aggregation over existing nodes. Stored in SQLite (rel_md_path=NULL).
L3 Report: reasoning + conclusion + MANDATORY evidence chain (BAN-ARCH-5).
A Report with zero references is rejected (CONST-DOC-3).
Both are DB-only: body inlined in SQLite `nodes.body`, no .md file written (DESIGN-ARCH-1).
"""
from __future__ import annotations

import yaml

from ..utils import frontmatter as fm
from ..utils.response import error, success, warning
from ..utils.paths import gen_uid, now_ts, safe_slug
from ..utils.wiki import find_node_md, resolve_wiki


def _split_uids(s: str) -> list[str]:
    return [u.strip() for u in s.split(",") if u.strip()]


def cmd_list(args) -> dict:
    if args.list_action == "create":
        return _list_create(args)
    if args.list_action == "show":
        return _list_show(args)
    return error(f"unknown list action: {args.list_action}", "UnknownAction")


def _list_create(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    members = _split_uids(args.members)
    if not members:
        return error("a List needs at least one member (--members)", "EmptyList")

    member_items = []
    missing = []
    for m_uid in members:
        found = find_node_md(ctx, m_uid)
        if not found:
            missing.append(m_uid)
        else:
            mf, _ = found
            member_items.append({
                "uid": m_uid,
                "title": mf.get("title", ""),
                "layer": mf.get("layer", ""),
                "note": "",
            })
    if missing:
        return error(f"member node(s) not found: {missing}", "MemberNotFound",
                     data={"missing": missing})

    uid = gen_uid()
    ts = now_ts()

    body = yaml.dump(member_items, allow_unicode=True, default_flow_style=False, sort_keys=False)

    conn = ctx.connect()
    try:
        conn.execute(
            "INSERT INTO node_derived(uid, layer, title, dimension, attrs, "  _=""
            "created_at, updated_at, body) VALUES(?,?,?,?,?,?,?,?)",
            (
                uid,
                "List",
                args.title,
                args.dimension,
                None,            # attrs (reserved)
                ts,
                ts,
                body,            # inlined body
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return success(
        {"uid": uid, "layer": "List", "members": [m["uid"] for m in member_items],
         "dimension": args.dimension},
        f"created Node_List {uid} with {len(member_items)} member(s)",
        hints=[f"read --uid {uid} to view; list show --uid {uid} for L2 presentation"],
    )


def _list_show(args) -> dict:
    """Show List node from SQLite (DB-only, no .md file)."""
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    conn = ctx.connect()
    try:
        row = conn.execute(
            "SELECT uid, title, body, dimension FROM node_derived WHERE uid=? AND layer='List'",
            (args.uid,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return error(f"List not found: {args.uid}", "ListNotFound")

    dimension = row["dimension"] or ""

    members = []
    if row["body"]:
        try:
            members = yaml.safe_load(row["body"]) or []
        except yaml.YAMLError:
            members = []

    return success(
        {"uid": row["uid"], "title": row["title"], "dimension": dimension,
         "members": members, "member_count": len(members)},
        f"List {args.uid}: {len(members)} member(s)",
    )


def cmd_report(args) -> dict:
    if args.report_action == "create":
        return _report_create(args)
    if args.report_action == "show":
        return _report_show(args)
    return error(f"unknown report action: {args.report_action}", "UnknownAction")


def _report_create(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    refs = _split_uids(args.references)
    if not refs:
        return error(
            "a Report MUST cite at least one evidence node (BAN-ARCH-5, CONST-DOC-3)",
            "EmptyEvidence",
            hints=["L3 conclusions require an evidence chain; no naked reports"],
        )

    ref_meta = []
    missing = []
    for r_uid in refs:
        found = find_node_md(ctx, r_uid)
        if not found:
            missing.append(r_uid)
        else:
            rf, _ = found
            ref_meta.append({
                "uid": r_uid,
                "note": "",
                "title": rf.get("title", ""),
                "layer": rf.get("layer", ""),
            })
    if missing:
        return error(f"evidence node(s) not found: {missing}", "EvidenceNotFound",
                     data={"missing": missing})

    uid = gen_uid()
    ts = now_ts()

    # Store references inline in body YAML (evidence table removed)
    ref_yaml = yaml.dump(ref_meta, allow_unicode=True, default_flow_style=False, sort_keys=False)

    conn = ctx.connect()
    try:
        conn.execute(
            "INSERT INTO node_derived(uid, layer, title, dimension, attrs, "
            "created_at, updated_at, body) VALUES(?,?,?,?,?,?,?,?)",
            (
                uid,
                "Report",
                args.title,
                None,           # dimension (not used for Report)
                None,           # attrs (reserved)
                ts,
                ts,
                f"# Evidence\n\n{ref_yaml}\n\n# Body\n\n{args.body or ''}",
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return success(
        {"uid": uid, "layer": "Report", "references": [r["uid"] for r in ref_meta],
         "ref_count": len(ref_meta)},
        f"created Node_Report {uid} with {len(ref_meta)} evidence link(s)",
        hints=[f"read --uid {uid} to view; report show --uid {uid} for L3 presentation"],
    )


def _report_show(args) -> dict:
    """Show Report node from SQLite (DB-only, no .md file)."""
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    conn = ctx.connect()
    try:
        row = conn.execute(
            "SELECT uid, title, body FROM node_derived WHERE uid=? AND layer='Report'",
            (args.uid,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return error(f"Report not found: {args.uid}", "ReportNotFound")

    # References are inline in body YAML (evidence table removed)
    body = row["body"] or ""
    references = []
    if "# Evidence" in body:
        try:
            ev_start = body.index("# Evidence") + len("# Evidence")
            ev_end = body.index("# Body") if "# Body" in body else len(body)
            ev_yaml = body[ev_start:ev_end].strip()
            refs = yaml.safe_load(ev_yaml) or []
            references = [{"uid": r.get("uid", ""), "note": r.get("note", "")} for r in refs if isinstance(r, dict)]
        except (ValueError, yaml.YAMLError):
            pass

    data = {
        "uid": row["uid"],
        "title": row["title"],
        "body": body,
        "references": references,
        "evidence_count": len(references),
    }
    return success(data, f"Report {args.uid}: {len(references)} evidence link(s)")


# ─────────────────────────────────────────────────────────────────
# Entity (L2) — DB-only aggregation of entity attributes
# ─────────────────────────────────────────────────────────────────

def cmd_entity(args) -> dict:
    if args.entity_action == "create":
        return _entity_create(args)
    if args.entity_action == "show":
        return _entity_show(args)
    return error(f"unknown entity action: {args.entity_action}", "UnknownAction")


def _entity_create(args) -> dict:
    """Create a DB-only Entity node with YAML body."""
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    uid = getattr(args, "uid", None)
    if not uid:
        return error("Entity --uid is required", "MissingUID")

    title = getattr(args, "title", "")
    if not title:
        return error("Entity --title is required", "MissingTitle")

    # Parse attrs from YAML string
    attrs_str = getattr(args, "attrs", "") or ""
    try:
        attrs = yaml.safe_load(attrs_str) if attrs_str.strip() else {}
    except yaml.YAMLError as e:
        return error(f"Invalid --attrs YAML: {e}", "BadAttrs")

    body = yaml.dump(attrs, allow_unicode=True, default_flow_style=False, sort_keys=False)
    ts = now_ts()

    conn = ctx.connect()
    try:
        # Check if uid already exists
        existing = conn.execute("SELECT uid FROM nodes WHERE uid=?", (uid,)).fetchone()
        if existing:
            conn.close()
            return error(f"uid already exists: {uid}", "UIDExists")

        conn.execute(
            "INSERT INTO nodes(uid, layer, content_type, title, slug, "
            "rel_md_path, raw_path, content_hash, source_hash, active, attrs, "
            "created_at, updated_at, body) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                uid,
                "Entity",
                "entity",
                title,
                None,
                None,         # rel_md_path: DB-only, no .md file
                None,         # raw_path
                None,         # content_hash
                None,         # source_hash
                1,            # active
                None,         # attrs
                ts,
                ts,
                body,         # inlined body (YAML dict)
            ),
        )
        conn.commit()
    finally:
        conn.close()

    return success(
        {"uid": uid, "layer": "Entity", "title": title, "attrs": attrs},
        f"created Node_Entity {uid}",
        hints=[f"entity show --uid {uid} to view attributes"],
    )


def _entity_show(args) -> dict:
    """Show Entity node attributes as dict."""
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    conn = ctx.connect()
    try:
        row = conn.execute(
            "SELECT uid, title, body FROM nodes WHERE uid=? AND layer='Entity'",
            (args.uid,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return error(f"Entity not found: {args.uid}", "EntityNotFound")

    attrs = {}
    if row["body"]:
        try:
            attrs = yaml.safe_load(row["body"]) or {}
        except yaml.YAMLError:
            attrs = {"_raw": row["body"]}

    return success(
        {"uid": row["uid"], "title": row["title"], "attrs": attrs},
        f"Entity {args.uid}",
    )
