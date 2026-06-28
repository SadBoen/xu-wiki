"""Node_List + Node_Report + Node_Entity — file-based upper layers (01-wiki-architecture.md).

List: comparison/aggregation over existing nodes. Stored as .md in nodes/list/.
Report: reasoning + conclusion + MANDATORY evidence chain (BAN-ARCH-5).
Entity: first-class named concept extracted from Page content. Body is the Agent's
  notes on the entity; source_page links back to the originating Page.
All three are .md-only (DESIGN-ARCH-1).
"""
from __future__ import annotations

import yaml

from ..utils import frontmatter as fm
from ..utils.response import error, success, warning
from ..utils.paths import atomic_write_text, gen_uid, now_ts, safe_slug, safe_node_path
from ..utils.wiki import find_node_md, resolve_wiki


def _split_uids(s: str) -> list[str]:
    return [u.strip() for u in s.split(",") if u.strip()]


def cmd_list(args) -> dict:
    if args.list_action == "create":
        return _list_create(args)
    if args.list_action == "show":
        return _list_show(args)
    if args.list_action == "modify":
        return _list_modify(args)
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

    try:
        if getattr(args, "node_path", ""):
            node_path = safe_node_path(args.node_path)
        else:
            node_path = safe_slug(args.title)
    except ValueError as e:
        return error(str(e), "BadNodePath")

    frontmatter = {
        "uid": uid,
        "title": args.title,
        "layer": "List",
        "dimension": args.dimension,
        "node_path": node_path,
        "split_index": 1,
        "parent_uid": uid,
        "created_at": ts,
        "updated_at": ts,
    }

    md_path = ctx.list_dir / f"{node_path}.md"
    body = yaml.dump(member_items, allow_unicode=True, default_flow_style=False, sort_keys=False)
    atomic_write_text(md_path, fm.render(frontmatter, body))  # type: ignore[arg-type]  # md_path set when frontmatter found

    return success(
        {"uid": uid, "layer": "List", "members": [m["uid"] for m in member_items],
         "dimension": args.dimension, "node_path": node_path},
        f"created Node_List {uid} with {len(member_items)} member(s)",
        hints=[f"read --uid {uid} to view; list show --uid {uid} for List presentation"],
    )


def _list_show(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    frontmatter, body = None, ""
    for p in ctx.list_dir.glob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
            fm_dict, bd = fm.parse(text)
            if fm_dict.get("uid") == args.uid:
                frontmatter, body = fm_dict, bd
                break
        except Exception:
            continue
    if frontmatter is None:
        return error(f"List not found: {args.uid}", "ListNotFound")
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


def _list_modify(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    md_path = None
    frontmatter, body = None, ""
    for p in ctx.list_dir.glob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
            fm_dict, bd = fm.parse(text)
            if fm_dict.get("uid") == args.uid:
                frontmatter, body = fm_dict, bd
                md_path = p
                break
        except Exception:
            continue
    if frontmatter is None:
        return error(f"List not found: {args.uid}", "ListNotFound")

    if args.title:
        frontmatter["title"] = args.title
    if getattr(args, "dimension", None):
        frontmatter["dimension"] = args.dimension
    if getattr(args, "members", None):
        member_uids = _split_uids(args.members)
        member_items = []
        missing = []
        for m_uid in member_uids:
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
        frontmatter["members"] = member_items
        body = yaml.dump(member_items, allow_unicode=True, default_flow_style=False, sort_keys=False)
    frontmatter["updated_at"] = now_ts()

    atomic_write_text(md_path, fm.render(frontmatter, body))  # type: ignore[arg-type]  # md_path set when frontmatter found
    return success(
        {"uid": args.uid, "layer": "List"},
        f"modified List {args.uid}",
    )


def cmd_report(args) -> dict:
    if args.report_action == "create":
        return _report_create(args)
    if args.report_action == "show":
        return _report_show(args)
    if args.report_action == "modify":
        return _report_modify(args)
    return error(f"unknown report action: {args.report_action}", "UnknownAction")


# ---------------------------------------------------------------------------
# Entity
# ---------------------------------------------------------------------------

def cmd_entity(args) -> dict:
    if args.entity_action == "create":
        return _entity_create(args)
    if args.entity_action == "show":
        return _entity_show(args)
    if args.entity_action == "modify":
        return _entity_modify(args)
    return error(f"unknown entity action: {args.entity_action}", "UnknownAction")


def _entity_create(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    if not args.title:
        return error("Entity needs a --title", "MissingTitle")

    source_page_uid = None
    if getattr(args, "source_page", None):
        found = find_node_md(ctx, args.source_page)
        if not found:
            return error(f"source_page node not found: {args.source_page}", "MemberNotFound",
                         data={"missing": [args.source_page]})
        source_page_uid = args.source_page

    uid = gen_uid()
    ts = now_ts()

    try:
        if getattr(args, "node_path", ""):
            node_path = safe_node_path(args.node_path)
        else:
            node_path = safe_slug(args.title)
    except ValueError as e:
        return error(str(e), "BadNodePath")

    frontmatter = {
        "uid": uid,
        "title": args.title,
        "layer": "Entity",
        "node_path": node_path,
        "source_page": source_page_uid,
        "split_index": 1,
        "parent_uid": uid,
        "created_at": ts,
        "updated_at": ts,
    }

    md_path = ctx.entity_dir / f"{node_path}.md"
    atomic_write_text(md_path, fm.render(frontmatter, args.body or ""))

    hints = [f"read --uid {uid} to view"]
    if source_page_uid:
        hints.append(f"expand --wiki {args.wiki} --uids {source_page_uid} to review source")
    return success(
        {"uid": uid, "layer": "Entity", "source_page": source_page_uid,
         "node_path": node_path},
        f"created Node_Entity {uid}",
        hints=hints,
    )


def _entity_show(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    frontmatter, body = None, ""
    for p in ctx.entity_dir.glob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
            fm_dict, bd = fm.parse(text)
            if fm_dict.get("uid") == args.uid:
                frontmatter, body = fm_dict, bd
                break
        except Exception:
            continue
    if frontmatter is None:
        return error(f"Entity not found: {args.uid}", "EntityNotFound")

    return success(
        {"uid": frontmatter.get("uid"), "title": frontmatter.get("title"),
         "source_page": frontmatter.get("source_page"),
         "node_path": frontmatter.get("node_path", ""),
         "body": body},
        f"Entity {args.uid}",
    )


def _entity_modify(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    md_path = None
    frontmatter, body = None, ""
    for p in ctx.entity_dir.glob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
            fm_dict, bd = fm.parse(text)
            if fm_dict.get("uid") == args.uid:
                frontmatter, body = fm_dict, bd
                md_path = p
                break
        except Exception:
            continue
    if frontmatter is None:
        return error(f"Entity not found: {args.uid}", "EntityNotFound")

    if args.title:
        frontmatter["title"] = args.title
    if getattr(args, "body", None) is not None:
        body = args.body
    frontmatter["updated_at"] = now_ts()

    atomic_write_text(md_path, fm.render(frontmatter, body))  # type: ignore[arg-type]  # md_path set when frontmatter found
    return success(
        {"uid": args.uid, "layer": "Entity"},
        f"modified Entity {args.uid}",
    )


def _report_create(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    refs = _split_uids(args.references)
    if not refs:
        return error(
            "a Report MUST cite at least one evidence node (BAN-ARCH-5, CONST-DOC-3)",
            "EmptyEvidence",
            hints=["Report conclusions require an evidence chain; no naked reports"],
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

    try:
        if getattr(args, "node_path", ""):
            node_path = safe_node_path(args.node_path)
        else:
            node_path = safe_slug(args.title)
    except ValueError as e:
        return error(str(e), "BadNodePath")

    frontmatter = {
        "uid": uid,
        "title": args.title,
        "layer": "Report",
        "references": ref_meta,
        "node_path": node_path,
        "split_index": 1,
        "parent_uid": uid,
        "created_at": ts,
        "updated_at": ts,
    }

    md_path = ctx.report_dir / f"{node_path}.md"
    atomic_write_text(md_path, fm.render(frontmatter, args.body or ""))

    return success(
        {"uid": uid, "layer": "Report", "references": [r["uid"] for r in ref_meta],
         "ref_count": len(ref_meta)},
        f"created Node_Report {uid} with {len(ref_meta)} evidence link(s)",
        hints=[f"read --uid {uid} to view; report show --uid {uid} for Report presentation"],
    )


def _report_show(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    frontmatter, body = None, ""
    for p in ctx.report_dir.glob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
            fm_dict, bd = fm.parse(text)
            if fm_dict.get("uid") == args.uid:
                frontmatter, body = fm_dict, bd
                break
        except Exception:
            continue
    if frontmatter is None:
        return error(f"Report not found: {args.uid}", "ReportNotFound")
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


def _report_modify(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    md_path = None
    frontmatter, body = None, ""
    for p in ctx.report_dir.glob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
            fm_dict, bd = fm.parse(text)
            if fm_dict.get("uid") == args.uid:
                frontmatter, body = fm_dict, bd
                md_path = p
                break
        except Exception:
            continue
    if frontmatter is None:
        return error(f"Report not found: {args.uid}", "ReportNotFound")

    if args.title:
        frontmatter["title"] = args.title
    if getattr(args, "body", None) is not None:
        body = args.body
    if getattr(args, "references", None):
        ref_uids = _split_uids(args.references)
        if not ref_uids:
            return error("Report needs at least one evidence node", "EmptyEvidence",
                         hints=["Report conclusions require an evidence chain; no naked reports"])
        ref_meta = []
        missing = []
        for r_uid in ref_uids:
            found = find_node_md(ctx, r_uid)
            if not found:
                missing.append(r_uid)
            else:
                rf, _ = found
                ref_meta.append({
                    "uid": r_uid,
                    "title": rf.get("title", ""),
                    "layer": rf.get("layer", ""),
                    "note": "",
                })
        if missing:
            return error(f"evidence node(s) not found: {missing}", "EvidenceNotFound",
                         data={"missing": missing})
        frontmatter["references"] = ref_meta
    frontmatter["updated_at"] = now_ts()

    atomic_write_text(md_path, fm.render(frontmatter, body))  # type: ignore[arg-type]  # md_path set when frontmatter found
    return success(
        {"uid": args.uid, "layer": "Report"},
        f"modified Report {args.uid}",
    )
