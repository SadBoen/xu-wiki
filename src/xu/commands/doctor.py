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
from ..utils.constants import IDF_CONSTANT, MAX_EDGES, REQUIRED_FM_FIELDS
from ..utils.paths import now_ts, sha256_text
from ..utils.response import error, success, warning
from ..utils.wiki import resolve_wiki


_LAYER_TAG = {"Page": "L1", "List": "L2", "Report": "L3"}


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
            "doctor-report-evidence": _check_report_evidence,
            "doctor-idf": _check_idf,
        }
        if kind in ("doctor", "doctor-all"):
            report = {fn_name: fn(ctx, conn, fix) for fn_name, fn in checks.items()}
            conn.commit()
            summary = _summarize(report)
            data = {"checks": report, "fix_applied": fix, **summary}
            # re-check after fix to verify repairs actually worked (CONST-DOC-8)
            if fix:
                recheck = {fn_name: fn(ctx, conn, False) for fn_name, fn in checks.items()}
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
        r = fn(ctx, conn, fix)
        conn.commit()
        summary = _summarize({kind: r})
        data = {kind: r, "fix_applied": fix, **summary}
        if fix:
            post = _summarize({kind: fn(ctx, conn, False)})
            data["post_fix"] = {"residual_issues": post["total_issues"],
                                "by_layer": post["by_layer"]}
        status = success if summary["total_issues"] == 0 else warning
        hints = [] if (summary["total_issues"] == 0 or fix) else \
            [f"re-run with --fix to repair {summary['auto_fixable']} auto-fixable issue(s)"]
        return status(data, f"{kind}: {summary['total_issues']} issue(s)", hints=hints)
    finally:
        conn.close()


def _check_fields(ctx, conn, fix) -> dict:
    """Frontmatter completeness + DB/file consistency (CONST-DOC-1)."""
    issues = []
    fixed = []
    rows = conn.execute("SELECT uid, rel_md_path, layer FROM nodes WHERE rel_md_path IS NOT NULL").fetchall()
    for row in rows:
        lyr = _LAYER_TAG.get(row["layer"], "cross")
        md_path = ctx.root / row["rel_md_path"]
        if not md_path.exists():
            issues.append({"uid": row["uid"], "problem": "md file missing",
                           "path": row["rel_md_path"], "layer": lyr, "fixable": False})
            continue
        frontmatter, _ = fm.parse(md_path.read_text(encoding="utf-8", errors="replace"))
        missing = [f for f in REQUIRED_FM_FIELDS if f not in frontmatter]
        if missing:
            issues.append({"uid": row["uid"], "problem": "missing frontmatter fields",
                           "missing": missing, "layer": lyr, "fixable": False})
        if frontmatter.get("uid") and frontmatter["uid"] != row["uid"]:
            issues.append({"uid": row["uid"], "problem": "uid mismatch file vs DB",
                           "file_uid": frontmatter["uid"], "layer": lyr, "fixable": False})
    return {"issue_count": len(issues), "issues": issues, "fixed": fixed}


def _check_files(ctx, conn, fix) -> dict:
    """Orphan files (on disk, not in DB) and dangling DB rows (CONST-DOC-2)."""
    issues = []
    fixed = []
    db_paths = {r["rel_md_path"] for r in
                conn.execute("SELECT rel_md_path FROM nodes WHERE rel_md_path IS NOT NULL").fetchall()}
    for md in ctx.page_dir.rglob("*.md"):
        rel = str(md.relative_to(ctx.root))
        if rel not in db_paths:
            issues.append({"problem": "orphan md file (not in DB)", "path": rel,
                           "layer": "L1", "fixable": False})
    rows = conn.execute("SELECT uid, rel_md_path FROM nodes WHERE rel_md_path IS NOT NULL").fetchall()
    for row in rows:
        if not (ctx.root / row["rel_md_path"]).exists():
            issues.append({"problem": "DB row points to missing file", "uid": row["uid"],
                           "path": row["rel_md_path"], "layer": "L1", "fixable": True})
            if fix:
                conn.execute("UPDATE nodes SET active=0 WHERE uid=?", (row["uid"],))
                fixed.append({"uid": row["uid"], "action": "marked inactive"})
    return {"issue_count": len(issues), "issues": issues, "fixed": fixed}


def _check_relations(ctx, conn, fix) -> dict:
    """LRU integrity: cap, contiguous positions, dangling targets (CONST-DOC-4)."""
    issues = []
    fixed = []
    sources = [r["from_uid"] for r in
               conn.execute("SELECT DISTINCT from_uid FROM relations").fetchall()]
    for src in sources:
        rels = list_relations(conn, src)
        if len(rels) > MAX_EDGES:
            issues.append({"from_uid": src, "problem": f"edge count {len(rels)} > {MAX_EDGES}",
                           "layer": "cross", "fixable": True})
            if fix:
                # trim the LRU tail back to MAX_EDGES (PRIN-DOC-3 inverse of ingest)
                for r in rels[MAX_EDGES:]:
                    conn.execute("DELETE FROM relations WHERE from_uid=? AND to_uid=? "
                                 "AND relation_name=?", (src, r["to_uid"], r["relation_name"]))
                fixed.append({"from_uid": src, "action": f"trimmed {len(rels) - MAX_EDGES} tail edge(s)"})
                rels = rels[:MAX_EDGES]
        positions = [r["position"] for r in rels]
        if positions != list(range(len(positions))):
            issues.append({"from_uid": src, "problem": "non-contiguous positions",
                           "positions": positions, "layer": "cross", "fixable": True})
            if fix:
                for newpos, r in enumerate(rels):
                    conn.execute("UPDATE relations SET position=? WHERE from_uid=? AND to_uid=? "
                                 "AND relation_name=?",
                                 (newpos, src, r["to_uid"], r["relation_name"]))
                fixed.append({"from_uid": src, "action": "renumbered positions"})
        for r in rels:
            if not conn.execute("SELECT 1 FROM nodes WHERE uid=?", (r["to_uid"],)).fetchone():
                issues.append({"from_uid": src, "problem": "dangling relation target",
                               "to_uid": r["to_uid"], "layer": "cross", "fixable": True})
                if fix:
                    conn.execute("DELETE FROM relations WHERE from_uid=? AND to_uid=? "
                                 "AND relation_name=?",
                                 (src, r["to_uid"], r["relation_name"]))
                    fixed.append({"from_uid": src, "to_uid": r["to_uid"], "action": "removed dangling edge"})
    return {"issue_count": len(issues), "issues": issues, "fixed": fixed}


def _check_l1_immutable(ctx, conn, fix) -> dict:
    """L1 body must match its recorded content_hash (PRIN-ARCH-3, never auto-fix)."""
    issues = []
    rows = conn.execute(
        "SELECT uid, rel_md_path, content_hash FROM nodes "
        "WHERE layer='Page' AND rel_md_path IS NOT NULL AND content_hash IS NOT NULL"
    ).fetchall()
    for row in rows:
        md_path = ctx.root / row["rel_md_path"]
        if not md_path.exists():
            issues.append({"uid": row["uid"], "problem": "L1 file missing",
                           "layer": "L1", "fixable": False})
            continue
        _, body = fm.parse(md_path.read_text(encoding="utf-8", errors="replace"))
        actual = sha256_text(body)
        if actual != row["content_hash"]:
            issues.append({"uid": row["uid"], "problem": "L1 content_hash mismatch (tampered)",
                           "expected": row["content_hash"][:12], "actual": actual[:12],
                           "layer": "L1", "fixable": False})
    # NEVER auto-fix L1 content (BAN-DOC-5: L1 is source of truth)
    return {"issue_count": len(issues), "issues": issues, "fixed": [],
            "note": "L1 mismatches are reported only; manual review required (BAN-DOC-5)"}


def _check_report_evidence(ctx, conn, fix) -> dict:
    """Every Report must have >=1 evidence ref, no dangling refs (CONST-DOC-3)."""
    issues = []
    reports = conn.execute("SELECT uid FROM nodes WHERE layer='Report'").fetchall()
    for r in reports:
        refs = conn.execute("SELECT ref_uid FROM evidence WHERE report_uid=?", (r["uid"],)).fetchall()
        if not refs:
            issues.append({"report_uid": r["uid"], "problem": "report with zero evidence (BAN-ARCH-5)",
                           "layer": "L3", "fixable": False})
        for ref in refs:
            target = conn.execute("SELECT active FROM nodes WHERE uid=?", (ref["ref_uid"],)).fetchone()
            if not target:
                issues.append({"report_uid": r["uid"], "problem": "dangling evidence ref",
                               "ref_uid": ref["ref_uid"], "layer": "L3", "fixable": False})
            elif not target["active"]:
                # CONST-DOC-3 #2: referenced node must be active
                issues.append({"report_uid": r["uid"], "problem": "evidence ref points to inactive node",
                               "ref_uid": ref["ref_uid"], "layer": "L3", "fixable": False})
    return {"issue_count": len(issues), "issues": issues, "fixed": [],
            "note": "evidence integrity is structural; never auto-deleted (BAN-DOC-6)"}


def _check_idf(ctx, conn, fix) -> dict:
    """IDF weight = const/(freq+1) consistency (CONST-ING-6 / CONST-DOC-5)."""
    issues = []
    fixed = []
    rows = conn.execute("SELECT noun, freq, weight FROM idf").fetchall()
    for row in rows:
        expected = IDF_CONSTANT / (row["freq"] + 1)
        if abs(expected - row["weight"]) > 1e-6:
            issues.append({"noun": row["noun"], "problem": "weight mismatch",
                           "expected": round(expected, 4), "actual": row["weight"],
                           "layer": "cross", "fixable": True})
            if fix:
                conn.execute("UPDATE idf SET weight=? WHERE noun=?", (expected, row["noun"]))
                fixed.append(row["noun"])
    return {"issue_count": len(issues), "issues": issues[:50], "fixed": fixed,
            "total_nouns": len(rows)}


def cmd_delete_node(args) -> dict:
    """Physical delete with reference safety check (PRIN-DOC, BAN-ARCH-2 keeps UID retired)."""
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    conn = ctx.connect()
    try:
        node = conn.execute("SELECT * FROM nodes WHERE uid=?", (args.uid,)).fetchone()
        if not node:
            return error(f"node not found: {args.uid}", "NodeNotFound")
        node = dict(node)

        # who references this node? (L2 members, L3 evidence, relations)
        list_refs = [r["list_uid"] for r in
                     conn.execute("SELECT list_uid FROM list_members WHERE member_uid=?",
                                  (args.uid,)).fetchall()]
        evidence_refs = [r["report_uid"] for r in
                         conn.execute("SELECT report_uid FROM evidence WHERE ref_uid=?",
                                      (args.uid,)).fetchall()]
        rel_refs = [r["from_uid"] for r in
                    conn.execute("SELECT DISTINCT from_uid FROM relations WHERE to_uid=?",
                                 (args.uid,)).fetchall()]

        blocking = bool(list_refs or evidence_refs)
        if blocking and not args.force:
            return error(
                f"node {args.uid} is referenced by L2/L3; refusing delete (use --force)",
                "NodeReferenced",
                data={"list_refs": list_refs, "evidence_refs": evidence_refs,
                      "relation_refs": rel_refs},
                hints=["remove the references first, or pass --force to cascade"],
            )

        # delete md file + raw if present
        removed_files = []
        if node["rel_md_path"]:
            p = ctx.root / node["rel_md_path"]
            if p.exists():
                p.unlink()
                removed_files.append(node["rel_md_path"])
        if node["raw_path"]:
            p = ctx.root / node["raw_path"]
            if p.exists():
                p.unlink()
                removed_files.append(node["raw_path"])

        # cascade DB (relations from this node cascade via FK; clean inbound too)
        conn.execute("DELETE FROM relations WHERE to_uid=?", (args.uid,))
        conn.execute("DELETE FROM evidence WHERE ref_uid=?", (args.uid,))
        conn.execute("DELETE FROM list_members WHERE member_uid=?", (args.uid,))
        conn.execute("DELETE FROM nodes WHERE uid=?", (args.uid,))  # FK cascades patches/evidence/relations(from)
        conn.commit()

        return success(
            {"uid": args.uid, "removed_files": removed_files,
             "cleaned_list_refs": list_refs, "cleaned_evidence_refs": evidence_refs,
             "cleaned_relation_refs": rel_refs, "forced": args.force},
            f"deleted node {args.uid} (UID is retired, never reused — BAN-ARCH-2)",
        )
    except Exception as e:
        conn.rollback()
        return error(f"delete failed, rolled back: {e}", type(e).__name__)
    finally:
        conn.close()


def cmd_rebuild(args) -> dict:
    """Rebuild derived layers from L1. NEVER regenerates L1 content (PRIN-ARCH-3).

    granularity:
      keep-l1     : rebuild IDF + relation positions from current L1 (default)
      keep-l1-l2  : also leave L2 lists intact, rebuild IDF/relations
      full        : rebuild IDF + reconcile DB rows from L1 md files
    """
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    gran = args.granularity
    conn = ctx.connect()
    try:
        actions = []

        if gran == "full":
            # reconcile: ensure every L1 md file has a DB row, re-derive content_hash
            reconciled = 0
            for md in ctx.page_dir.rglob("*.md"):
                rel = str(md.relative_to(ctx.root))
                frontmatter, body = fm.parse(md.read_text(encoding="utf-8", errors="replace"))
                uid = frontmatter.get("uid")
                if not uid:
                    continue
                ch = sha256_text(body)
                row = conn.execute("SELECT uid FROM nodes WHERE uid=?", (uid,)).fetchone()
                if not row:
                    ts = now_ts()
                    conn.execute(
                        "INSERT INTO nodes(uid,layer,template,title,node_path,slug,rel_md_path,"
                        "content_hash,active,created_at,updated_at) "
                        "VALUES(?,?,?,?,?,?,?,?,1,?,?)",
                        (uid, frontmatter.get("layer", "Page"), frontmatter.get("template", "article"),
                         frontmatter.get("title", uid), frontmatter.get("node_path", ""),
                         md.stem, rel, ch, ts, ts),
                    )
                    reconciled += 1
                else:
                    conn.execute("UPDATE nodes SET content_hash=?, rel_md_path=? WHERE uid=?",
                                 (ch, rel, uid))
            actions.append(f"reconciled {reconciled} L1 row(s) from disk")

        # rebuild IDF from all active L1 bodies (always, for any granularity)
        conn.execute("DELETE FROM idf")
        freq: dict[str, int] = {}
        rows = conn.execute(
            "SELECT rel_md_path FROM nodes WHERE layer='Page' AND active=1 AND rel_md_path IS NOT NULL"
        ).fetchall()
        for row in rows:
            p = ctx.root / row["rel_md_path"]
            if not p.exists():
                continue
            _, body = fm.parse(p.read_text(encoding="utf-8", errors="replace"))
            for noun, cnt in extract_nouns(body).items():
                freq[noun] = freq.get(noun, 0) + cnt
        ts = now_ts()
        for noun, f in freq.items():
            conn.execute("INSERT INTO idf(noun,freq,weight,updated_at) VALUES(?,?,?,?)",
                         (noun, f, IDF_CONSTANT / (f + 1), ts))
        actions.append(f"rebuilt IDF: {len(freq)} noun(s)")

        # renumber relation positions to contiguous
        for src in [r["from_uid"] for r in
                    conn.execute("SELECT DISTINCT from_uid FROM relations").fetchall()]:
            rels = list_relations(conn, src)
            for newpos, r in enumerate(rels):
                conn.execute("UPDATE relations SET position=? WHERE from_uid=? AND to_uid=? "
                             "AND relation_name=?", (newpos, src, r["to_uid"], r["relation_name"]))
        actions.append("renumbered relation LRU positions")

        conn.commit()
        return success({"granularity": gran, "actions": actions},
                       f"rebuild ({gran}) complete; L1 content untouched (PRIN-ARCH-3)")
    except Exception as e:
        conn.rollback()
        return error(f"rebuild failed, rolled back: {e}", type(e).__name__)
    finally:
        conn.close()
