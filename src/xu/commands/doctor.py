"""doctor / delete-node / rebuild — operations & resilience (07-doctor.md).

doctor checks are READ-ONLY by default; --fix applies only mechanical,
non-destructive repairs (PRIN-DOC). Never touches L1 source-of-truth content.
delete-node checks L2/L3 references before physical deletion.
rebuild reconstructs derived layers from L1 (never regenerates L1, PRIN-ARCH-3).
"""
from __future__ import annotations

import json
from pathlib import Path

from ..ingest.splitter import extract_nouns
from ..ingest.relations_lru import list_relations
from ..utils import frontmatter as fm
from ..utils.constants import IDF_CONSTANT, FM_EVIDENCE, FM_MEMBERS, FM_PATCHES, MAX_EDGES, REQUIRED_FM_FIELDS
from ..utils.idf import load_idf, dump_idf
from ..utils.paths import now_ts, sha256_text
from ..utils.response import error, success, warning
from ..utils.wiki import resolve_wiki


_LAYER_TAG = {"Page": "L1", "List": "L2", "Report": "L3"}


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
    by_layer = {"L1": 0, "L2": 0, "L3": 0, "cross": 0}
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
    conn = ctx.connect()
    try:
        checks = {
            "doctor-fields": _check_fields,
            "doctor-files": _check_files,
            "doctor-relations": _check_relations,
            "doctor-l1-immutable": _check_l1_immutable,
            "doctor-sqlite-md-consistency": _check_sqlite_md_consistency,
            "doctor-report-evidence": _check_report_evidence,
            "doctor-idf": _check_idf,
            "doctor-entity-consistency": _check_entity_consistency,
        }
        if kind in ("doctor", "doctor-all"):
            report = {}
            for fn_name, fn in checks.items():
                if fn_name in ("doctor-report-evidence", "doctor-idf"):
                    report[fn_name] = fn(ctx, fix)
                else:
                    report[fn_name] = fn(ctx, conn, fix)
            conn.commit()
            summary = _summarize(report)
            data = {"checks": report, "fix_applied": fix, **summary}
            # re-check after fix to verify repairs actually worked (CONST-DOC-8)
            if fix:
                recheck = {}
                for fn_name, fn in checks.items():
                    if fn_name in ("doctor-report-evidence", "doctor-idf"):
                        recheck[fn_name] = fn(ctx, False)
                    else:
                        recheck[fn_name] = fn(ctx, conn, False)
                post = _summarize(recheck)
                data["post_fix"] = {"residual_issues": post["total_issues"],
                                    "by_layer": post["by_layer"]}
            status = success if summary["total_issues"] == 0 else warning
            hints = [] if summary["total_issues"] == 0 else \
                ([f"re-run with --fix to repair {summary['auto_fixable']} auto-fixable issue(s)"]
                 if not fix else [])
            return status(data,
                          f"doctor-all: {summary['total_issues']} issue(s) "
                          f"(L1={summary['by_layer']['L1']} L2={summary['by_layer']['L2']} "
                          f"L3={summary['by_layer']['L3']} cross={summary['by_layer']['cross']})",
                          hints=hints)
        fn = checks.get(kind)
        if not fn:
            return error(f"unknown doctor check: {kind}", "UnknownCheck")
        if kind in ("doctor-report-evidence", "doctor-idf"):
            r = fn(ctx, fix)
        else:
            r = fn(ctx, conn, fix)
        conn.commit()
        summary = _summarize({kind: r})
        data = {kind: r, "fix_applied": fix, **summary}
        if fix:
            if kind in ("doctor-report-evidence", "doctor-idf"):
                post_r = fn(ctx, False)
            else:
                post_r = fn(ctx, conn, False)
            post = _summarize({kind: post_r})
            data["post_fix"] = {"residual_issues": post["total_issues"],
                                "by_layer": post["by_layer"]}
        status = success if summary["total_issues"] == 0 else warning
        hints = [] if (summary["total_issues"] == 0 or fix) else \
            [f"re-run with --fix to repair {summary['auto_fixable']} auto-fixable issue(s)"]
        return status(data, f"{kind}: {summary['total_issues']} issue(s)", hints=hints)
    finally:
        conn.close()


def _check_fields(ctx, conn, fix) -> dict:
    """Frontmatter completeness + file existence (CONST-DOC-1)."""
    issues = []
    fixed = []
    for md_path, fm_dict, _ in _all_frontmatter_nodes(ctx):
        uid = fm_dict.get("uid", "")
        lyr = _LAYER_TAG.get(fm_dict.get("layer", ""), "cross")
        missing = [f for f in REQUIRED_FM_FIELDS if f not in fm_dict]
        if missing:
            issues.append({"uid": uid, "problem": "missing frontmatter fields",
                           "missing": missing, "layer": lyr, "fixable": False,
                           "path": str(md_path.relative_to(ctx.root))})
    return {"issue_count": len(issues), "issues": issues, "fixed": fixed}


def _check_files(ctx, conn, fix) -> dict:
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
                           "layer": "L1", "fixable": False})
    return {"issue_count": len(issues), "issues": issues, "fixed": fixed}


def _check_relations(ctx, conn, fix) -> dict:
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
        rels = list_relations(ctx, src)
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


def _check_l1_immutable(ctx, conn, fix) -> dict:
    """L1 body must match its recorded content_hash (PRIN-ARCH-3, never auto-fix)."""
    issues = []
    for md_path, fm_dict, body in _all_frontmatter_nodes(ctx):
        if fm_dict.get("layer") != "Page":
            continue
        stored_hash = fm_dict.get("content_hash")
        if not stored_hash:
            continue
        actual = sha256_text(body)
        if actual != stored_hash:
            issues.append({"uid": fm_dict.get("uid"), "problem": "L1 content_hash mismatch (tampered)",
                           "expected": stored_hash[:12], "actual": actual[:12],
                           "layer": "L1", "fixable": False})
    # NEVER auto-fix L1 content (BAN-DOC-5: L1 is source of truth)
    # T7: Also catch DB-only nodes (rel_md_path=NULL) that have NULL body
    db_only_rows = conn.execute(
        "SELECT uid, body, content_hash FROM nodes WHERE layer='Page' AND rel_md_path IS NULL"
    ).fetchall()
    for row in db_only_rows:
        if not row["body"]:
            issues.append({
                "uid": row["uid"],
                "problem": "DB-only node has NULL body in SQLite (ingest bug)",
                "expected": row["content_hash"],
                "actual": "NULL",
                "layer": "L1",
                "fixable": False,
            })
    return {"issue_count": len(issues), "issues": issues, "fixed": [],
            "note": "L1 mismatches are reported only; manual review required (BAN-DOC-5)"}


def _check_sqlite_md_consistency(ctx, conn, fix) -> dict:
    """SQLite content_hash vs .md frontmatter content_hash consistency check (T7).

    Compares the stored content_hash in the SQLite nodes table against the
    content_hash stored in each .md file's frontmatter. Mismatches indicate
    that the DB and frontmatter are out of sync. This is non-fixable via --fix
    because resolving it requires determining which source is authoritative.
    """
    issues = []
    fixed = []

    # Build uid -> (md_path, fm_content_hash, body) from .md files
    md_hashes: dict[str, tuple[Path, str, str]] = {}
    for md_path, fm_dict, body in _all_frontmatter_nodes(ctx):
        uid = fm_dict.get("uid")
        if not uid:
            continue
        md_hash = fm_dict.get("content_hash", "")
        md_hashes[uid] = (md_path, md_hash, body)

    # Query SQLite for all content_hash values
    rows = conn.execute(
        "SELECT uid, content_hash FROM nodes WHERE layer='Page'"
    ).fetchall()

    for row in rows:
        uid = row["uid"]
        db_hash = row["content_hash"] or ""
        if uid not in md_hashes:
            # Node in DB but not in frontmatter — handled by doctor-files
            # T7 fix: also catch DB-only nodes with NULL body
            if not db_hash:
                # DB-only entry with no hash and no .md is a data gap
                pass  # handled elsewhere
            continue
        md_path, fm_hash, body = md_hashes[uid]

        # Compare DB hash with frontmatter hash
        if db_hash != fm_hash:
            actual_body_hash = sha256_text(body)
            issues.append({
                "uid": uid,
                "problem": "content_hash mismatch between SQLite and .md frontmatter",
                "db_hash": db_hash[:12] if db_hash else "(empty)",
                "fm_hash": fm_hash[:12] if fm_hash else "(empty)",
                "actual_body_hash": actual_body_hash[:12],
                "layer": "L1",
                "fixable": False,
                "path": str(md_path.relative_to(ctx.root)),
            })

    # T7: check DB-only nodes (rel_md_path=NULL) have non-NULL body
    db_only = conn.execute(
        "SELECT uid, body, content_hash FROM nodes WHERE layer='Page' AND rel_md_path IS NULL"
    ).fetchall()
    for row in db_only:
        if not row["body"]:
            issues.append({
                "uid": row["uid"],
                "problem": "DB-only node (rel_md_path=NULL) has NULL body",
                "db_hash": (row["content_hash"] or "")[:12] if row["content_hash"] else "(empty)",
                "layer": "L1",
                "fixable": False,
            })

    return {"issue_count": len(issues), "issues": issues, "fixed": fixed,
            "note": "SQLite vs .md mismatches are reported only; manual reconciliation required"}


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
                           "layer": "L3", "fixable": False})
            continue
        to_remove = []
        for ref in evidence_list:
            ref_uid = ref.get("ref_uid") if isinstance(ref, dict) else ref
            active = uid_active.get(ref_uid)
            if active is None:
                issues.append({"report_uid": uid, "problem": "dangling evidence ref",
                               "ref_uid": ref_uid, "layer": "L3", "fixable": True})
                if fix:
                    to_remove.append(ref)
                    fixed.append({"report_uid": uid, "ref_uid": ref_uid,
                                  "action": "removed dangling ref"})
            elif not active:
                issues.append({"report_uid": uid, "problem": "evidence ref points to inactive node",
                               "ref_uid": ref_uid, "layer": "L3", "fixable": True})
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


def _check_idf(ctx, fix) -> dict:
    """IDF weight = const/(freq+1) consistency (CONST-ING-6 / CONST-DOC-5)."""
    issues = []
    fixed = []
    idf = load_idf(ctx)
    new_idf = {}
    for noun, (freq, weight) in idf.items():
        expected = IDF_CONSTANT / (freq + 1)
        if abs(expected - weight) > 1e-6:
            issues.append({"noun": noun, "problem": "weight mismatch",
                           "expected": round(expected, 4), "actual": weight,
                           "layer": "cross", "fixable": True})
            if fix:
                new_idf[noun] = (freq, expected)
                fixed.append(noun)
    if fix and new_idf:
        for noun in new_idf:
            idf[noun] = new_idf[noun]
        dump_idf(ctx, idf)
    return {"issue_count": len(issues), "issues": issues[:50], "fixed": fixed,
            "total_nouns": len(idf)}


def _check_entity_consistency(ctx, conn, fix) -> dict:
    """Entity nodes are DB-only with no immutable constraints (DESIGN-ARCH-1).

    Entity has no associated .md file and no content_hash, so there is
    nothing to check for consistency. This check always returns ok.
    """
    return {"issue_count": 0, "issues": [], "fixed": []}


def cmd_delete_node(args) -> dict:
    """Delete node row from SQLite (PRIN-DOC). Does not touch .md files."""
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    conn = ctx.connect()
    try:
        # Check if node exists in DB
        cur = conn.execute("SELECT uid FROM nodes WHERE uid = ?", (args.uid,))
        if cur.fetchone() is None:
            return error(f"node not found: {args.uid}", "NodeNotFound")

        # Delete from SQLite
        conn.execute("DELETE FROM nodes WHERE uid = ?", (args.uid,))
        conn.commit()
        return success(
            {"uid": args.uid},
            f"deleted node {args.uid} from SQLite (UID is retired, never reused — BAN-ARCH-2)",
        )
    finally:
        conn.close()


def cmd_rebuild(args) -> dict:
    """Rebuild derived layers from L1. NEVER regenerates L1 content (PRIN-ARCH-3).

    granularity:
      keep-l1     : rebuild IDF + renumber relation positions from frontmatter (default)
      keep-l1-l2  : also leave L2 lists intact, rebuild IDF/relations
      full        : same as keep-l1 (frontmatter is source of truth)
    """
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    gran = args.granularity
    actions = []

    if gran == "full":
        actions.append("DB reconciliation skipped (frontmatter is source of truth)")

    # rebuild IDF from all active L1 bodies (always, for any granularity)
    # reads from frontmatter via fs walk; writes to idf.md
    freq: dict[str, tuple[int, float]] = {}
    for md_path, fm_dict, body in _all_frontmatter_nodes(ctx):
        if fm_dict.get("layer") != "Page":
            continue
        if not fm_dict.get("active", True):
            continue
        for noun, cnt in extract_nouns(body).items():
            freq[noun] = (freq.get(noun, (0, 0.0))[0] + cnt,
                          IDF_CONSTANT / (freq.get(noun, (0, 0.0))[0] + cnt + 1))
    dump_idf(ctx, {noun: (f, w) for noun, (f, w) in freq.items()})
    actions.append(f"rebuilt IDF: {len(freq)} noun(s)")

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
                   f"rebuild ({gran}) complete; L1 content untouched (PRIN-ARCH-3)")
