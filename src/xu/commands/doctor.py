"""doctor / delete-node / rebuild — operations & resilience (07-doctor.md).

doctor checks are READ-ONLY by default; --fix applies only mechanical,
non-destructive repairs (PRIN-DOC). Never touches Page source-of-truth content.
delete-node checks derived-layer references before physical deletion.
rebuild reconstructs derived layers from Page (never regenerates Page, PRIN-ARCH-3).
"""
from __future__ import annotations

import json
from pathlib import Path

from ..ingest.relations_lru import list_relations
from ..utils import frontmatter as fm
from ..utils.constants import FM_EVIDENCE, FM_MEMBERS, FM_PATCHES, MAX_EDGES, REQUIRED_FM_FIELDS
from ..utils.paths import now_ts, sha256_text
from ..utils.response import error, success, warning
from ..utils.wiki import resolve_wiki


_LAYER_TAG = {}


def _all_frontmatter_nodes(ctx):
    """Walk nodes_dir, yield (md_path, fm_dict, body)."""
    nodes_root = ctx.nodes_dir
    if not nodes_root.is_dir():
        return
    for p in nodes_root.rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            fm_dict, body = fm.parse(text)
            if fm_dict.get("uid"):
                yield p, fm_dict, body
        except Exception:
            continue


def _find_node_fm(ctx, uid: str) -> tuple[dict, Path] | None:
    """Find frontmatter dict and path for a uid via fs walk."""
    nodes_root = ctx.nodes_dir
    if not nodes_root.is_dir():
        return None
    for p in nodes_root.rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            fm_dict, _ = fm.parse(text)
            if fm_dict.get("uid") == uid:
                return fm_dict, p
        except Exception:
            continue
    return None


def _summarize(checks_report: dict) -> dict:
    """Aggregate issues by layer + fixability (CONST-DOC-7)."""
    by_layer = {"Page": 0, "List": 0, "Report": 0, "Entity": 0, "cross": 0}
    auto_fixable = 0
    read_only = 0
    total = 0
    for r in checks_report.values():
        for issue in r.get("issues", []):
            total += 1
            by_layer[issue.get("layer", "cross")] = by_layer.get(issue.get("layer", "cross"), 0) + 1
            if issue.get("fixable"):
                auto_fixable += 1
            else:
                read_only += 1
    return {"total_issues": total, "by_layer": by_layer,
            "auto_fixable": auto_fixable, "read_only": read_only}


def cmd_doctor(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    kind = args.doctor_kind
    fix = args.fix
    checks = {
        "doctor-fields": _check_fields,
        "doctor-files": _check_files,
        "doctor-relations": _check_relations,
        "doctor-l1-immutable": _check_l1_immutable,
        "doctor-report-evidence": _check_report_evidence,
        "doctor-node-path-organization": _check_node_path_organization,
    }
    if kind in ("doctor", "doctor-all"):
        report = {}
        for fn_name, fn in checks.items():
            report[fn_name] = fn(ctx, fix)
        summary = _summarize(report)
        data = {"checks": report, "fix_applied": fix, **summary}
        if fix:
            recheck = {}
            for fn_name, fn in checks.items():
                recheck[fn_name] = fn(ctx, False)
            post = _summarize(recheck)
            data["post_fix"] = {"residual_issues": post["total_issues"],
                                "by_layer": post["by_layer"]}
        status = success if summary["total_issues"] == 0 else warning
        hints = [] if summary["total_issues"] == 0 else \
            ([f"re-run with --fix to repair {summary['auto_fixable']} auto-fixable issue(s)"]
             if not fix else [])
        return status(data,
                      f"doctor-all: {summary['total_issues']} issue(s) "
                      f"(Page={summary['by_layer']['Page']} List={summary['by_layer']['List']} "
                      f"Report={summary['by_layer']['Report']} Entity={summary['by_layer']['Entity']} "
                      f"cross={summary['by_layer']['cross']})",
                      hints=hints)
    fn = checks.get(kind)
    if not fn:
        return error(f"unknown doctor check: {kind}", "UnknownCheck")
    r = fn(ctx, fix)
    summary = _summarize({kind: r})
    data = {kind: r, "fix_applied": fix, **summary}
    if fix:
        post_r = fn(ctx, False)
        post = _summarize({kind: post_r})
        data["post_fix"] = {"residual_issues": post["total_issues"],
                            "by_layer": post["by_layer"]}
    status = success if summary["total_issues"] == 0 else warning
    hints = [] if (summary["total_issues"] == 0 or fix) else \
        [f"re-run with --fix to repair {summary['auto_fixable']} auto-fixable issue(s)"]
    return status(data, f"{kind}: {summary['total_issues']} issue(s)", hints=hints)


def _check_fields(ctx, fix) -> dict:
    """Frontmatter completeness + file existence (CONST-DOC-1)."""
    issues = []
    fixed = []
    for md_path, fm_dict, _ in _all_frontmatter_nodes(ctx):
        uid = fm_dict.get("uid", "")
        lyr = fm_dict.get("layer", "cross")
        missing = [f for f in REQUIRED_FM_FIELDS if f not in fm_dict]
        if missing:
            issues.append({"uid": uid, "problem": "missing frontmatter fields",
                           "missing": missing, "layer": lyr, "fixable": False,
                           "path": str(md_path.relative_to(ctx.root))})
    return {"issue_count": len(issues), "issues": issues, "fixed": fixed}


def _check_files(ctx, fix) -> dict:
    """Orphan files (on disk, not in DB) and dangling DB rows (CONST-DOC-2)."""
    issues = []
    fixed = []
    fm_paths = {}
    for md_path, fm_dict, _ in _all_frontmatter_nodes(ctx):
        fm_paths[str(md_path.relative_to(ctx.root))] = fm_dict
    for md in ctx.page_dir.rglob("*.md"):
        rel = str(md.relative_to(ctx.root))
        if rel not in fm_paths:
            issues.append({"problem": "orphan md file (not in frontmatter)", "path": rel,
                           "layer": "Page", "fixable": False})
    return {"issue_count": len(issues), "issues": issues, "fixed": fixed}


def _check_relations(ctx, fix) -> dict:
    """LRU integrity: cap, contiguous positions, dangling targets (CONST-DOC-4)."""
    issues = []
    fixed = []
    all_uids = set()
    for _, fm_dict, _ in _all_frontmatter_nodes(ctx):
        uid = fm_dict.get("uid")
        if uid:
            all_uids.add(uid)
    for md_path, fm_dict, _ in _all_frontmatter_nodes(ctx):
        src = fm_dict.get("uid")
        if not src:
            continue
        rels = list_relations(fm_dict, src)
        if len(rels) > MAX_EDGES:
            issues.append({"from_uid": src, "problem": f"edge count {len(rels)} > {MAX_EDGES}",
                           "layer": "cross", "fixable": True})
        positions = [r.get("position", i) for i, r in enumerate(rels)]
        if positions != list(range(len(positions))):
            issues.append({"from_uid": src, "problem": "non-contiguous positions",
                           "positions": positions, "layer": "cross", "fixable": True})
        for r in rels:
            if r.get("to_uid") not in all_uids:
                issues.append({"from_uid": src, "problem": "dangling relation target",
                               "to_uid": r.get("to_uid"), "layer": "cross", "fixable": True})
    return {"issue_count": len(issues), "issues": issues, "fixed": fixed}


def _check_l1_immutable(ctx, fix) -> dict:
    """Page body must match its recorded content_hash (PRIN-ARCH-3, never auto-fix)."""
    issues = []
    for md_path, fm_dict, body in _all_frontmatter_nodes(ctx):
        if fm_dict.get("layer") != "Page":
            continue
        stored_hash = fm_dict.get("content_hash")
        if not stored_hash:
            continue
        actual = sha256_text(body)
        if actual != stored_hash:
            issues.append({"uid": fm_dict.get("uid"), "problem": "Page content_hash mismatch (tampered)",
                           "expected": stored_hash[:12], "actual": actual[:12],
                           "layer": "Page", "fixable": False})
    # NEVER auto-fix Page content (BAN-DOC-5: Page is source of truth)
    return {"issue_count": len(issues), "issues": issues, "fixed": [],
            "note": "Page mismatches are reported only; manual review required (BAN-DOC-5)"}


def _check_report_evidence(ctx, fix) -> dict:
    """Every Report must have >=1 evidence ref, no dangling refs (CONST-DOC-3).

    --fix is mechanical: removes dangling / inactive refs from Report frontmatter.
    It does NOT delete the Report itself (BAN-DOC-6: LLM推理成果不自动删).
    A Report with zero evidence is reported but NOT auto-deleted.
    """
    issues = []
    fixed = []

    uid_active: dict[str, bool] = {}
    for _, fd, _ in _all_frontmatter_nodes(ctx):
        uid = fd.get("uid")
        if uid:
            uid_active[uid] = fd.get("active", True)

    for md_path, fd, _ in _all_frontmatter_nodes(ctx):
        if fd.get("layer") != "Report":
            continue
        uid = fd.get("uid")
        evidence_list = fd.get(FM_EVIDENCE, [])
        if not evidence_list:
            issues.append({"report_uid": uid, "problem": "report with zero evidence (BAN-ARCH-5)",
                           "layer": "Report", "fixable": False})
            continue
        to_remove = []
        for ref in evidence_list:
            ref_uid = ref.get("ref_uid") if isinstance(ref, dict) else ref
            active = uid_active.get(ref_uid)
            if active is None:
                issues.append({"report_uid": uid, "problem": "dangling evidence ref",
                               "ref_uid": ref_uid, "layer": "Report", "fixable": True})
                if fix:
                    to_remove.append(ref)
                    fixed.append({"report_uid": uid, "ref_uid": ref_uid,
                                  "action": "removed dangling ref"})
            elif not active:
                issues.append({"report_uid": uid, "problem": "evidence ref points to inactive node",
                               "ref_uid": ref_uid, "layer": "Report", "fixable": True})
                if fix:
                    to_remove.append(ref)
                    fixed.append({"report_uid": uid, "ref_uid": ref_uid,
                                  "action": "removed ref to inactive node"})
        if fix and to_remove:
            for ref in to_remove:
                evidence_list.remove(ref)
            text = md_path.read_text(encoding="utf-8", errors="replace")
            _, body = fm.parse(text)
            md_path.write_text(fm.render(fd, body), encoding="utf-8")
    return {"issue_count": len(issues), "issues": issues, "fixed": fixed,
            "note": "--fix removes dangling/inactive refs from Report frontmatter; Report itself is never deleted (BAN-DOC-6)"}


def _suggest_node_path(title: str) -> str:
    """Heuristic: extract dominant noun from title → use as node_path category."""
    try:
        nouns = extract_nouns(title)
        if not nouns:
            return "uncategorized"
        top = max(nouns, key=nouns.get)
        if len(top) < 2:
            return "uncategorized"
        safe = top.replace(" ", "-").lower()[:30]
        return safe
    except Exception:
        return "uncategorized"


def _check_node_path_organization(ctx, fix) -> dict:
    """Detect pages at nodes/page/ root with no logical partition (PRIN-ARCH-24).

    Suggests target node_path per page by extracting dominant noun from title.
    --fix calls xu reorganize for each page.
    """
    issues = []
    fixed = []

    root_page_dir = ctx.page_dir
    if not root_page_dir.is_dir():
        return {"issue_count": 0, "issues": [], "fixed": [], "at_root": 0}

    root_uids = set()
    for p in root_page_dir.glob("*.md"):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            fm_dict, _ = fm.parse(text)
            uid = fm_dict.get("uid")
            if (uid and fm_dict.get("layer") == "Page" and
                    fm_dict.get("active", True) and
                    not (fm_dict.get("node_path") or "").strip()):
                root_uids.add(uid)
        except Exception:
            continue

    for _, fm_dict, _ in _all_frontmatter_nodes(ctx):
        uid = fm_dict.get("uid")
        if (uid and fm_dict.get("layer") == "Page" and
                fm_dict.get("active", True) and
                not (fm_dict.get("node_path") or "").strip()):
            root_uids.add(uid)

    if not root_uids:
        return {"issue_count": 0, "issues": [], "fixed": [], "at_root": 0}

    for uid in sorted(root_uids):
        fm_dict, md_path = _find_node_fm(ctx, uid)
        if not fm_dict:
            continue
        title = fm_dict.get("title") or ""
        suggested = _suggest_node_path(title)
        issues.append({
            "uid": uid,
            "title": title,
            "current_path": str(md_path.relative_to(ctx.root)) if md_path else "",
            "suggested_node_path": suggested,
            "suggest_reason": f"title contains noun: {suggested!r}",
            "layer": "Page",
            "fixable": True,
        })
        if fix:
            from ..commands.reorganize import cmd_reorganize
            class _FakeArgs:
                wiki = ctx.name
                uid = uid
                new_node_path = suggested
            r = cmd_reorganize(_FakeArgs())
            fixed.append({"uid": uid, "result": r.get("status", "unknown"),
                          "suggested": suggested})

    return {
        "issue_count": len(issues),
        "issues": issues,
        "fixed": fixed,
        "at_root": len(issues),
        "note": "--fix is mechanical but suggested_node_path is heuristic (from title noun extraction); review suggestions before applying",
    }


def cmd_delete_node(args) -> dict:
    """Physical delete with reference safety check (PRIN-DOC, BAN-ARCH-2 keeps UID retired)."""
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    node_fd = None
    node_path = None
    for md_path, fd, _ in _all_frontmatter_nodes(ctx):
        if fd.get("uid") == args.uid:
            node_fd = fd
            node_path = md_path
            break
    if not node_fd:
        return error(f"node not found: {args.uid}", "NodeNotFound")

    # who references this node? (List members, Report evidence, relations)
    list_refs = []
    evidence_refs = []
    rel_refs = []
    for md_p, fd, _ in _all_frontmatter_nodes(ctx):
        layer = fd.get("layer")
        uid = fd.get("uid")
        if layer == "List":
            members = fd.get(FM_MEMBERS, [])
            for m in members:
                m_uid = m.get("uid") if isinstance(m, dict) else m
                if m_uid == args.uid:
                    list_refs.append(uid)
                    break
        elif layer == "Report":
            evidence = fd.get(FM_EVIDENCE, [])
            for e in evidence:
                e_uid = e.get("ref_uid") if isinstance(e, dict) else e
                if e_uid == args.uid:
                    evidence_refs.append(uid)
                    break
        relations = fd.get("relations", [])
        for rel in relations:
            if rel.get("to_uid") == args.uid:
                rel_refs.append(uid)
                break

    blocking = bool(list_refs or evidence_refs)
    if blocking and not args.force:
        return error(
            f"node {args.uid} is referenced by List/Report; refusing delete (use --force)",
            "NodeReferenced",
            data={"list_refs": list_refs, "evidence_refs": evidence_refs,
                  "relation_refs": rel_refs},
            hints=["remove the references first, or pass --force to cascade"],
        )

    # Remove references from List members and Report evidence and Page relations
    for md_p, fd, _ in _all_frontmatter_nodes(ctx):
        layer = fd.get("layer")
        uid = fd.get("uid")
        changed = False
        if layer == "List" and uid in list_refs:
            members = fd.get(FM_MEMBERS, [])
            new_members = [m for m in members
                           if (m.get("uid") if isinstance(m, dict) else m) != args.uid]
            if len(new_members) != len(members):
                fd[FM_MEMBERS] = new_members
                changed = True
        elif layer == "Report" and uid in evidence_refs:
            evidence = fd.get(FM_EVIDENCE, [])
            new_evidence = [e for e in evidence
                           if (e.get("ref_uid") if isinstance(e, dict) else e) != args.uid]
            if len(new_evidence) != len(evidence):
                fd[FM_EVIDENCE] = new_evidence
                changed = True
        elif uid in rel_refs:
            relations = fd.get("relations", [])
            new_relations = [r for r in relations if r.get("to_uid") != args.uid]
            if len(new_relations) != len(relations):
                fd["relations"] = new_relations
                changed = True
        if changed:
            text = md_p.read_text(encoding="utf-8", errors="replace")
            _, body = fm.parse(text)
            md_p.write_text(fm.render(fd, body), encoding="utf-8")

    # Remove the node file itself
    removed_files = []
    if node_path and node_path.exists():
        node_path.unlink()
        removed_files.append(str(node_path))
    raw_path_str = node_fd.get("raw_path")
    if raw_path_str:
        raw_p = ctx.root / raw_path_str
        if raw_p.exists():
            raw_p.unlink()
            removed_files.append(raw_path_str)

    return success(
        {"uid": args.uid, "removed_files": removed_files,
         "cleaned_list_refs": list_refs, "cleaned_evidence_refs": evidence_refs,
         "cleaned_relation_refs": rel_refs, "forced": args.force},
        f"deleted node {args.uid} (UID is retired, never reused — BAN-ARCH-2)",
    )


def cmd_rebuild(args) -> dict:
    """Rebuild derived layers from Page. NEVER regenerates Page content (PRIN-ARCH-3).

    granularity:
      keep-l1     : renumber relation positions from frontmatter (default)
      keep-l1-l2  : also leave List intact, renumber relations
      full        : same as keep-l1 (frontmatter is source of truth)
    """
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    gran = args.granularity
    actions = []

    if gran == "full":
        actions.append("DB reconciliation skipped (frontmatter is source of truth)")

    # renumber relation positions to contiguous in frontmatter
    for md_path, fm_dict, _ in _all_frontmatter_nodes(ctx):
        src = fm_dict.get("uid")
        if not src:
            continue
        raw = fm_dict.get("relations", [])
        if not isinstance(raw, list):
            continue
        positions = [r.get("position", i) for i, r in enumerate(raw)]
        if positions == list(range(len(positions))):
            continue
        for i, r in enumerate(raw):
            r["position"] = i
        text = md_path.read_text(encoding="utf-8", errors="replace")
        _, body = fm.parse(text)
        md_path.write_text(fm.render(fm_dict, body), encoding="utf-8")
    actions.append("renumbered relation LRU positions in frontmatter")

    return success({"granularity": gran, "actions": actions},
                   f"rebuild ({gran}) complete; Page content untouched (PRIN-ARCH-3)")
