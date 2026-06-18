"""L2 Node_List + L3 Node_Report — DB-only upper layers (01-wiki-architecture.md).

L2 List: comparison/aggregation over existing nodes. DB-only (no .md).
L3 Report: reasoning + conclusion + MANDATORY evidence chain (BAN-ARCH-5).
A Report with zero references is rejected (CONST-DOC-3).
Both are DB-only: rel_md_path stays NULL; body lives in `digest`/attrs (PRIN-ARCH-4/5).
"""
from __future__ import annotations

import json

from ..utils.response import error, success, warning
from ..utils.paths import gen_uid, now_ts
from ..utils.wiki import resolve_wiki


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

    conn = ctx.connect()
    try:
        missing = [m for m in members
                   if not conn.execute("SELECT 1 FROM nodes WHERE uid=?", (m,)).fetchone()]
        if missing:
            return error(f"member node(s) not found: {missing}", "MemberNotFound",
                         data={"missing": missing})

        uid = gen_uid()
        ts = now_ts()
        attrs = json.dumps({"dimension": args.dimension}, ensure_ascii=False)
        conn.execute(
            "INSERT INTO nodes(uid, layer, template, title, node_path, slug, "
            "rel_md_path, raw_path, content_hash, source_hash, active, digest, "
            "attrs, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,NULL,NULL,NULL,NULL,1,?,?,?,?)",
            (uid, "List", "table", args.title, args.node_path.strip("/"),
             None, args.dimension, attrs, ts, ts),
        )
        for pos, m in enumerate(members):
            conn.execute(
                "INSERT INTO list_members(list_uid, member_uid, position) VALUES(?,?,?)",
                (uid, m, pos),
            )
        conn.commit()
        return success(
            {"uid": uid, "layer": "List", "members": members, "dimension": args.dimension},
            f"created Node_List {uid} with {len(members)} member(s) (DB-only)",
            hints=["list show <uid> to view the comparison"],
        )
    except Exception as e:
        conn.rollback()
        return error(f"list create failed, rolled back: {e}", type(e).__name__)
    finally:
        conn.close()


def _list_show(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    conn = ctx.connect()
    try:
        row = conn.execute("SELECT * FROM nodes WHERE uid=? AND layer='List'",
                           (args.uid,)).fetchone()
        if not row:
            return error(f"List not found: {args.uid}", "ListNotFound")
        node = dict(row)
        members = conn.execute(
            "SELECT lm.member_uid, lm.position, n.title, n.layer, n.digest "
            "FROM list_members lm LEFT JOIN nodes n ON n.uid = lm.member_uid "
            "WHERE lm.list_uid=? ORDER BY lm.position",
            (args.uid,),
        ).fetchall()
        attrs = json.loads(node.get("attrs") or "{}")
        return success(
            {"uid": node["uid"], "title": node["title"],
             "dimension": attrs.get("dimension", node.get("digest")),
             "members": [dict(m) for m in members], "member_count": len(members)},
            f"List {args.uid}: {len(members)} member(s)",
        )
    finally:
        conn.close()


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

    conn = ctx.connect()
    try:
        missing = [r for r in refs
                   if not conn.execute("SELECT 1 FROM nodes WHERE uid=?", (r,)).fetchone()]
        if missing:
            return error(f"evidence node(s) not found: {missing}", "EvidenceNotFound",
                         data={"missing": missing})

        uid = gen_uid()
        ts = now_ts()
        attrs = json.dumps({"body": args.body}, ensure_ascii=False)
        conn.execute(
            "INSERT INTO nodes(uid, layer, template, title, node_path, slug, "
            "rel_md_path, raw_path, content_hash, source_hash, active, digest, "
            "attrs, created_at, updated_at) "
            "VALUES(?,?,?,?,?,NULL,NULL,NULL,NULL,NULL,1,?,?,?,?)",
            (uid, "Report", "article", args.title, args.node_path.strip("/"),
             args.body[:200], attrs, ts, ts),
        )
        for r in refs:
            conn.execute(
                "INSERT INTO evidence(report_uid, ref_uid, note) VALUES(?,?,'')",
                (uid, r),
            )
        conn.commit()
        return success(
            {"uid": uid, "layer": "Report", "references": refs, "ref_count": len(refs)},
            f"created Node_Report {uid} with {len(refs)} evidence link(s) (DB-only)",
            hints=["report show <uid> to view conclusion + evidence chain"],
        )
    except Exception as e:
        conn.rollback()
        return error(f"report create failed, rolled back: {e}", type(e).__name__)
    finally:
        conn.close()


def _report_show(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    conn = ctx.connect()
    try:
        row = conn.execute("SELECT * FROM nodes WHERE uid=? AND layer='Report'",
                           (args.uid,)).fetchone()
        if not row:
            return error(f"Report not found: {args.uid}", "ReportNotFound")
        node = dict(row)
        evidence = conn.execute(
            "SELECT e.ref_uid, e.note, n.title, n.layer FROM evidence e "
            "LEFT JOIN nodes n ON n.uid = e.ref_uid WHERE e.report_uid=?",
            (args.uid,),
        ).fetchall()
        attrs = json.loads(node.get("attrs") or "{}")
        # warn if any evidence dangles (M5 doctor also catches this)
        dangling = [dict(e)["ref_uid"] for e in evidence if e["title"] is None]
        data = {"uid": node["uid"], "title": node["title"],
                "body": attrs.get("body", ""),
                "evidence": [dict(e) for e in evidence],
                "evidence_count": len(evidence)}
        if dangling:
            return warning(data, f"Report shown; {len(dangling)} dangling evidence ref(s)",
                           hints=[f"run doctor-report-evidence; dangling: {dangling}"])
        return success(data, f"Report {args.uid}: {len(evidence)} evidence link(s)")
    finally:
        conn.close()
