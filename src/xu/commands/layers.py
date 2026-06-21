"""L2 Node_List + L3 Node_Report — file-based upper layers (01-wiki-architecture.md).

L2 List: comparison/aggregation over existing nodes. Stored as .md in nodes/list/.
L3 Report: reasoning + conclusion + MANDATORY evidence chain (BAN-ARCH-5).
A Report with zero references is rejected (CONST-DOC-3).
Both are .md-only: body + frontmatter in nodes/list/|nodes/report/ (DESIGN-ARCH-1).
"""
from __future__ import annotations

import yaml

from ..utils import frontmatter as fm
from ..utils.response import error, success, warning
from ..utils.paths import atomic_write_text, gen_uid, now_ts
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

    frontmatter = {
        "uid": uid,
        "title": args.title,
        "layer": "List",
        "dimension": args.dimension,
        "created_at": ts,
        "updated_at": ts,
    }

    md_path = ctx.list_dir / f"{uid}.md"
    body = yaml.dump(member_items, allow_unicode=True, default_flow_style=False, sort_keys=False)
    atomic_write_text(md_path, fm.render(frontmatter, body))

    return success(
        {"uid": uid, "layer": "List", "members": [m["uid"] for m in member_items],
         "dimension": args.dimension},
        f"created Node_List {uid} with {len(member_items)} member(s)",
        hints=[f"nodes/list/{uid}.md"],
    )


def _list_show(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    md_path = ctx.list_dir / f"{args.uid}.md"
    if not md_path.exists():
        return error(f"List not found: {args.uid}", "ListNotFound")

    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception as e:
        return error(f"failed to read List file: {e}", "ReadError")

    frontmatter, body = fm.parse(text)
    members = []
    if body.strip():
        try:
            members = yaml.safe_load(body) or []
        except yaml.YAMLError:
            members = []

    return success(
        {"uid": frontmatter.get("uid"), "title": frontmatter.get("title"),
         "dimension": frontmatter.get("dimension", ""),
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

    frontmatter = {
        "uid": uid,
        "title": args.title,
        "layer": "Report",
        "references": ref_meta,
        "created_at": ts,
        "updated_at": ts,
    }

    md_path = ctx.report_dir / f"{uid}.md"
    atomic_write_text(md_path, fm.render(frontmatter, args.body or ""))

    return success(
        {"uid": uid, "layer": "Report", "references": [r["uid"] for r in ref_meta],
         "ref_count": len(ref_meta)},
        f"created Node_Report {uid} with {len(ref_meta)} evidence link(s)",
        hints=[f"nodes/report/{uid}.md"],
    )


def _report_show(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    md_path = ctx.report_dir / f"{args.uid}.md"
    if not md_path.exists():
        return error(f"Report not found: {args.uid}", "ReportNotFound")

    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception as e:
        return error(f"failed to read Report file: {e}", "ReadError")

    frontmatter, body = fm.parse(text)
    references = frontmatter.get("references", [])
    dangling = [r["uid"] for r in references if not find_node_md(ctx, r["uid"])]
    data = {"uid": frontmatter.get("uid"), "title": frontmatter.get("title"),
            "body": body,
            "references": references,
            "evidence_count": len(references)}
    if dangling:
        return warning(data, f"Report shown; {len(dangling)} dangling evidence ref(s)",
                       hints=[f"run doctor-report-evidence; dangling: {dangling}"])
    return success(data, f"Report {args.uid}: {len(references)} evidence link(s)")
