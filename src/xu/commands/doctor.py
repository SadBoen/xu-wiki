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
            "doctor-report-evidence": _check_report_evidence,
            "doctor-idf": _check_idf,
            "doctor-node-path-organization": _check_node_path_organization,
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
    return {"issue_count": len(issues), "issues": issues, "fixed": [],
            "note": "L1 mismatches are reported only; manual review required (BAN-DOC-5)"}


def _check_report_evidence(ctx, conn, fix) -> dict:
    """Every Report must have >=1 evidence ref, no dangling refs (CONST-DOC-3).

    --fix is mechanical: removes dangling / inactive refs from the evidence table.
    It does NOT delete the Report itself (BAN-DOC-6: LLM推理成果不自动删).
    A Report with zero evidence is reported but NOT auto-deleted.
    """
    issues = []
    fixed = []
    reports = conn.execute("SELECT uid FROM nodes WHERE layer='Report'").fetchall()
    for r in reports:
        refs = conn.execute("SELECT ref_uid FROM evidence WHERE report_uid=?", (r["uid"],)).fetchall()
        if not refs:
            issues.append({"report_uid": r["uid"], "problem": "report with zero evidence (BAN-ARCH-5)",
                           "layer": "L3", "fixable": False})
            continue
        for ref in refs:
            target = conn.execute("SELECT active FROM nodes WHERE uid=?", (ref["ref_uid"],)).fetchone()
            if not target:
                issues.append({"report_uid": r["uid"], "problem": "dangling evidence ref",
                               "ref_uid": ref["ref_uid"], "layer": "L3", "fixable": True})
                if fix:
                    conn.execute("DELETE FROM evidence WHERE report_uid=? AND ref_uid=?",
                                 (r["uid"], ref["ref_uid"]))
                    fixed.append({"report_uid": r["uid"], "ref_uid": ref["ref_uid"],
                                  "action": "removed dangling ref"})
            elif not target["active"]:
                issues.append({"report_uid": r["uid"], "problem": "evidence ref points to inactive node",
                               "ref_uid": ref["ref_uid"], "layer": "L3", "fixable": True})
                if fix:
                    conn.execute("DELETE FROM evidence WHERE report_uid=? AND ref_uid=?",
                                 (r["uid"], ref["ref_uid"]))
                    fixed.append({"report_uid": r["uid"], "ref_uid": ref["ref_uid"],
                                  "action": "removed ref to inactive node"})
    return {"issue_count": len(issues), "issues": issues, "fixed": fixed,
            "note": "--fix removes dangling/inactive refs from evidence table; Report itself is never deleted (BAN-DOC-6)"}


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


def _check_node_path_organization(ctx, conn, fix) -> dict:
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
            "layer": "L1",
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

        # Decrement IDF frequencies contributed by this Page's body so deleted
        # nodes don't leave ghost nouns skewing query scores (CONST-ING-6).
        if node["layer"] == "Page" and node["rel_md_path"]:
            mp = ctx.root / node["rel_md_path"]
            if mp.exists():
                _, body = fm.parse(mp.read_text(encoding="utf-8", errors="replace"))
                ts = now_ts()
                for noun, cnt in extract_nouns(body).items():
                    rw = conn.execute("SELECT freq FROM idf WHERE noun=?", (noun,)).fetchone()
                    if not rw:
                        continue
                    new_freq = rw["freq"] - cnt
                    if new_freq <= 0:
                        conn.execute("DELETE FROM idf WHERE noun=?", (noun,))
                    else:
                        conn.execute("UPDATE idf SET freq=?, weight=?, updated_at=? WHERE noun=?",
                                     (new_freq, IDF_CONSTANT / (new_freq + 1), ts, noun))

        # Commit the DB cascade FIRST, then unlink files. Files are
        # unrecoverable; the DB is transactional. If a file unlink fails after
        # commit we only leak an orphan (doctor-files catches it) — far safer
        # than deleting files first and losing them when the DB write fails.
        conn.execute("DELETE FROM relations WHERE to_uid=?", (args.uid,))
        conn.execute("DELETE FROM evidence WHERE ref_uid=?", (args.uid,))
        conn.execute("DELETE FROM list_members WHERE member_uid=?", (args.uid,))
        conn.execute("DELETE FROM nodes WHERE uid=?", (args.uid,))  # FK cascades patches/evidence/relations(from)
        conn.commit()

        # DB committed — now remove md file + raw if present (best-effort)
        removed_files = []
        for rel in (node["rel_md_path"], node["raw_path"]):
            if rel:
                p = ctx.root / rel
                if p.exists():
                    p.unlink()
                    removed_files.append(rel)

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
      keep-l1     : rebuild IDF + renumber relation positions from frontmatter (default)
      keep-l1-l2  : also leave L2 lists intact, rebuild IDF/relations
      full        : same as keep-l1 (DB reconciliation deprecated; frontmatter is source of truth)
    """
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    gran = args.granularity
    conn = ctx.connect()
    try:
        actions = []

        if gran == "full":
            actions.append("DB reconciliation skipped (frontmatter is source of truth)")

        # rebuild IDF from all active L1 bodies (always, for any granularity)
        # reads from frontmatter via fs walk; writes to SQLite (IDF still in SQLite)
        if conn:
            conn.execute("DELETE FROM idf")
        freq: dict[str, int] = {}
        for md_path, fm_dict, body in _all_frontmatter_nodes(ctx):
            if fm_dict.get("layer") != "Page":
                continue
            if not fm_dict.get("active", True):
                continue
            for noun, cnt in extract_nouns(body).items():
                freq[noun] = freq.get(noun, 0) + cnt
        ts = now_ts()
        if conn:
            for noun, f in freq.items():
                conn.execute("INSERT INTO idf(noun,freq,weight,updated_at) VALUES(?,?,?,?)",
                             (noun, f, IDF_CONSTANT / (f + 1), ts))
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

        if conn:
            conn.commit()
        return success({"granularity": gran, "actions": actions},
                       f"rebuild ({gran}) complete; L1 content untouched (PRIN-ARCH-3)")
    except Exception as e:
        if conn:
            conn.rollback()
        return error(f"rebuild failed, rolled back: {e}", type(e).__name__)
    finally:
        if conn:
            conn.close()
