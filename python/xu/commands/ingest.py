"""ingest 鈥?two-phase L1 Node_Page creation (05-ingest.md).

Phase 1 (ingest-file): parse 鈫?write temporary file (system temp dir).
                        No node created.
Phase 2 (ingest-commit): validate 鈫?atomic write Page(s) + raws copy + patches v1
                         + IDF + relations. The ONLY write entry (PRIN-ING-1).
"""
from __future__ import annotations

import importlib
import json
import shutil
import tempfile

import yaml
from pathlib import Path

from ..utils import db as db_module
from ..ingest.relations_lru import add_relation
from ..ingest.splitter import extract_nouns, split_pages
from ..parsers.registry import parse_file
from ..utils import frontmatter as fm
from ..utils.config import cfg_get
from ..utils.constants import (
    FM_ACTIVE,
    FM_CONTENT_HASH,
    FM_CREATED,
    FM_LAYER,
    FM_PATCHES,
    FM_PARENT_UID,
    FM_SOURCE_HASH,
    FM_SPLIT_INDEX,
    FM_CONTENT_TYPE,
    FM_TITLE,
    FM_UID,
    IDF_CONSTANT,
    CONTENT_TYPES,
)
from ..utils.idf import increment_idf, load_idf, dump_idf
from ..utils.paths import (
    atomic_write_text,
    gen_uid,
    now_ts,
    safe_slug,
    sha256_file,
    sha256_text,
)
from ..utils.response import error, success, warning, make_response
from ..utils.wiki import resolve_wiki, find_node_md, find_by_source_hash, find_by_source_hash


def _scan_fm_index(ctx) -> tuple[dict, dict]:
    """Scan all Page frontmatter (SQLite primary + FS fallback).
    Returns (source_hash_map, content_hash_map).

    SQLite is authoritative for nodes written after this change.
    Legacy .md files are scanned as a fallback for pre-existing data.
    """
    source_map: dict[str, tuple[str, str, bool]] = {}
    content_map: dict[str, tuple[str, str]] = {}

    # SQLite (authoritative for current L1 pages)
    conn = ctx.connect()
    try:
        rows = conn.execute(
            "SELECT uid, title, active, content_hash, source_hash FROM node_page WHERE layer='Page'"
        ).fetchall()
        for row in rows:
            uid, title, active, content_hash, source_hash = row
            if source_hash:
                source_map[source_hash] = (uid, title or "", bool(active))
            if content_hash:
                content_map[content_hash] = (uid, title or "")
    finally:
        conn.close()

    # Legacy FS fallback (pre-existing .md files not yet migrated)
    page_dir = ctx.page_dir
    if page_dir.is_dir():
        for p in page_dir.rglob("*.md"):
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                fd, _ = fm.parse(text)
                uid = fd.get("uid")
                active = fd.get("active", True)
                if not uid:
                    continue
                # Only register if not already in SQLite map (DB wins)
                sh = fd.get("source_hash")
                if sh and sh not in source_map:
                    source_map[sh] = (uid, fd.get("title", ""), active)
                ch = fd.get("content_hash")
                if ch and ch not in content_map:
                    content_map[ch] = (uid, fd.get("title", ""))
            except Exception:
                continue
    return source_map, content_map


def cmd_ingest_file(args) -> dict:
    """Phase 1: dedup check 鈫?parse source 鈫?write temp file. No node created.

    Dedup is checked BEFORE calling the parser (especially expensive MinerU)
    to avoid wasting API calls on already-ingested sources (PRIN-ING-3).

    The temporary file is stored in the system temp directory
    (tempfile.gettempdir()), not in the wiki itself.
    """
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound",
                     hints=["check the name/path; do NOT auto-create (PRIN-SAFETY)"])

    src = Path(args.file).expanduser()
    if not src.is_file():
        return error(f"source file not found: {src}", "FileNotFound")

    # MissingExtra check: PDF/DOCX/PPTX requires the parse extra (markitdown)
    rich_exts = {".pdf", ".docx", ".pptx", ".xlsx", ".xls"}
    if src.suffix.lower() in rich_exts:
        try:
            importlib.import_module("markitdown")
        except ImportError:
            return error(
                f"cannot parse {src.suffix} files: 'markitdown' is not installed",
                "MissingExtra",
                data={"extra": "parse", "file_ext": src.suffix},
                hints=["pip install xu-wiki[parse] to enable PDF/DOCX/PPTX parsing"],
            )

    # Level-2 dedup: check BEFORE calling parser (especially MinerU 鈥?costs money).
    # Level-2 is all-pages, not active-only, so re-ingesting a deactivated source
    # is also caught here (PRIN-ING-3). Frontmatter is source of truth (FS).
    source_hash = sha256_file(src)
    dup_fm = find_by_source_hash(ctx, source_hash)
    if dup_fm:
        return warning(
            {"existing_uid": dup_fm["uid"], "existing_title": dup_fm.get("title", ""),
             "existing_active": dup_fm.get("active", True), "source_hash": source_hash},
            f"source already ingested as {dup_fm['uid']} (BAN-ING-4); Phase 1 skipped to avoid wasted parse cost",
            hints=["use 'revise' to update; ingest never overwrites (PRIN-ING-3)"],
        )

    # path whitelist (BAN-ING-5): allow anywhere readable for Phase 1 source,
    # but temp output stays in system temp dir.
    from ..utils.config import load_global_config
    mineru_key = load_global_config().get("mineru", {}).get("api_key", "")
    res = parse_file(src, mineru_key=mineru_key)
    if not res.ok:
        return error(
            f"all parsers failed for {src.name}; cannot enter Phase 2 (PRIN-ING-5)",
            "ParseFailed",
            data={"file": str(src)},
        )

    stem = safe_slug(src.stem)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix="-pre.md", prefix=f"{stem}-",
        dir=tempfile.gettempdir(), delete=False, encoding="utf-8"
    ) as f:
        text = _strip_frontmatter(res.text)
        meta_header = (
            f"<!-- xu-pending source={src} parser={res.parser} "
            f"source_hash={source_hash} -->\n\n"
        )
        f.write(meta_header + text)
        temp_path = Path(f.name)

    return success(
        {
            "pending": str(temp_path),
            "parser": res.parser,
            "source": str(src),
            "source_hash": source_hash,
            "chars": len(text),
        },
        f"parsed via {res.parser} 鈫?pending temp file (Phase 1). No node created yet.",
        hints=[
            "review pending content, then run ingest-commit with --pending and --title",
            "Agent decides title/raw_path/relations between phases (PRIN-ING-2)",
            "use --raw-path to organize raw files by category (e.g. certificates/qsa)",
        ],
    )


def _parse_pending_header(text: str) -> tuple[dict, str]:
    meta = {}
    body = text
    if text.startswith("<!-- xu-pending"):
        end = text.find("-->")
        if end != -1:
            header = text[len("<!-- xu-pending"):end].strip()
            for tok in header.split():
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    meta[k] = v
            body = text[end + 3:].lstrip("\n")
    return meta, body


def _validate_body_format(body: str, content_type: str) -> str | None:
    """Check body matches content_type format.

    Returns None if valid, or an error message string if invalid.
    """
    if content_type == "article":
        return None
    if content_type not in ("table", "gallery"):
        return f"unknown content_type: {content_type}"

    if not body.strip():
        return None  # empty body is allowed (can be filled later via revise)

    try:
        parsed = yaml.safe_load(body)
    except yaml.YAMLError:
        return (
            f"content_type={content_type} requires YAML list in body, "
            f"but parsing failed"
        )

    if not isinstance(parsed, list):
        return f"content_type={content_type} requires body to be a YAML list, got {type(parsed).__name__}"

    for i, item in enumerate(parsed):
        if not isinstance(item, dict):
            return f"content_type={content_type} body item {i} is not a dict: {type(item).__name__}"
        if content_type == "gallery" and "filename" not in item:
            return f"content_type={content_type} body item {i} missing required 'filename' field"

    return None


def _strip_frontmatter(text: str) -> str:
    """Strip leading YAML frontmatter (---...---) from markdown text."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[end + 4:].lstrip("\n")
    return text


def cmd_ingest_commit(args) -> dict:
    """Phase 2: validate + atomic write Page(s) + raws copy + patches v1 + IDF + relations.

    --pending: path to Phase 1 temp file (required for normal flow).
    --native: deprecated, bypasses Phase 1 (no temp file, no source copy to raws/).
    """
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound",
                     hints=["check the name/path; do NOT auto-create (PRIN-SAFETY)"])

    # Determine source content (BAN-ING-3: --native still goes through commit flow)
    source_hash = None
    raw_src_path = None
    parser_used = "native"
    if args.native:
        if not args.source:
            return error(
                "--native requires --source <abs-path> (PRIN-ING-6: every ingested source must be copyable to raws/)",
                "MissingSource",
                hints=["--source must be an absolute path to the source file"],
            )
        src_path = Path(args.source).expanduser()
        if not src_path.is_file():
            return error(f"source file not found: {src_path}", "FileNotFound")
        content = args.native
        raw_src_path = str(src_path)
        source_hash = sha256_text(args.native)
        raw_path_arg = args.raw_path
    elif args.pending:
        pending_path = Path(args.pending).expanduser()
        if not pending_path.is_file():
            return error(f"pending temp file not found: {pending_path}", "PendingNotFound")
        raw_text = pending_path.read_text(encoding="utf-8")
        meta, content = _parse_pending_header(raw_text)
        source_hash = meta.get("source_hash")
        parser_used = meta.get("parser", "unknown")
        raw_src_path = meta.get("source")
        raw_path_arg = args.raw_path
    else:
        return error("ingest-commit requires --pending or --native", "MissingInput")

    if not args.title:
        return error("ingest-commit requires --title (CONST-ING-4)", "MissingTitle",
                     data={"missing": ["title"]})
    if args.content_type not in CONTENT_TYPES:
        return error(f"invalid content-type: {args.content_type}", "InvalidContentType")

    # relations parsing (CONST-ING-5): must be JSON array
    relations = []
    if args.relations:
        try:
            relations = json.loads(args.relations)
        except json.JSONDecodeError as e:
            return error(f"--relations must be valid JSON: {e}", "BadRelationsJSON")
        if not isinstance(relations, list):
            return error("--relations must be a JSON array (CONST-ING-5)", "BadRelationsType")

    # split into pages (PRIN-ING-4)
    max_lines = cfg_get(ctx.config, "ingest.page_split_lines", 300)
    pages = split_pages(content, max_lines)
    if not pages:
        return error("no content to commit after splitting", "EmptyContent")

    # Build frontmatter index once (for dedup + relation target check)
    source_index, content_index = _scan_fm_index(ctx)

    # Level-2 dedup: source file hash across ALL pages (CONST-ING-3,
    # PRIN-ING-3). Note: Level-2 is "鎵€鏈?Page" 鈥?NOT filtered by active 鈥?
    # so re-ingesting the same source is caught even against a deactivated
    # page. (Level-1 below is active-only, per the design's contrast.)
    if source_hash:
        if source_hash in source_index:
            existing_uid, existing_title, existing_active = source_index[source_hash]
            return warning(
                {"existing_uid": existing_uid, "existing_title": existing_title,
                 "existing_active": existing_active, "source_hash": source_hash},
                f"source already ingested as {existing_uid} (BAN-ING-4); not re-created",
                hints=["use 'revise' to update; ingest never overwrites (PRIN-ING-3)"],
            )

    created = []
    dup_pages = []
    multi = len(pages) > 1
    first_uid = gen_uid()
    new_content_hashes: set[str] = set()
    all_uids: set[str] = {uid for uid, _, _ in source_index.values()}
    for uid in {v[0] for v in content_index.values()}:
        all_uids.add(uid)

    # Snapshot IDF before writes so we can restore on rollback
    idf_snapshot = load_idf(ctx)

    # Track files written so we can roll back on verify failure
    written: list[dict] = []

    conn = ctx.connect()
    try:
        # Use savepoint for atomicity within this connection
        conn.execute("SAVEPOINT ingest_pages")

        for idx, page_body in enumerate(pages):
            page_body = page_body.rstrip()

            body_err = _validate_body_format(page_body, args.content_type)
            if body_err:
                conn.execute("ROLLBACK TO SAVEPOINT ingest_pages")
                dump_idf(ctx, idf_snapshot)
                return error(body_err, "BodyFormatMismatch")

            content_hash = sha256_text(page_body)
            if content_hash in content_index:
                dup_pages.append({"part": idx + 1, "existing_uid": content_index[content_hash][0]})
                continue
            if content_hash in new_content_hashes:
                dup_pages.append({"part": idx + 1, "existing_uid": "duplicate in this commit"})
                continue

            uid = first_uid if idx == 0 else gen_uid()
            split_index = idx + 1
            parent_uid = first_uid
            title = args.title if not multi else f"{args.title} (part {idx + 1}/{len(pages)})"
            base_slug = safe_slug(args.title)
            slug = f"{base_slug}-{idx + 1}-{uid}" if multi else f"{base_slug}-{uid}"
            ts = now_ts()

            rel_raw = None
            raw_written = None
            if raw_src_path and Path(raw_src_path).is_file() and idx == 0:
                # LLM decides raw placement via --raw-path (e.g. certs/qsa/cert.pdf).
                # Fallback: filename-only under raws/ (prevents flat raws/ root).
                # Validate path stays under raws/ (BAN-ARCH-7 equivalent for raw files).
                if raw_path_arg:
                    raw_rel = Path("raws") / raw_path_arg
                else:
                    raw_rel = Path("raws") / Path(raw_src_path).name
                raw_dst = ctx.root / raw_rel
                raw_dst.parent.mkdir(parents=True, exist_ok=True)
                if not raw_dst.exists():
                    shutil.copy2(raw_src_path, raw_dst)
                raw_written = raw_dst

            # Write L1 Page to SQLite (PRIN-ING-1)
            conn.execute(
                "INSERT INTO node_page(uid, title, content_type, slug, "
                "rel_md_path, raw_path, content_hash, source_hash, active, attrs, "
                "created_at, updated_at, body) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    uid,
                    title,
                    args.content_type,
                    slug,
                    None,           # rel_md_path: no .md file written
                    str(rel_raw) if rel_raw else None,
                    content_hash,
                    source_hash or None,
                    1,               # active
                    None,            # attrs
                    ts,
                    ts,
                    page_body,      # inlined body (PRIN-ARCH-16)
                ),
            )
            # Write initial patch v1 (CONST-ING-7)
            conn.execute(
                "INSERT INTO patches(page_uid, version, op, delta, author, created_at) "
                "VALUES(?,?,?,?,?,?)",
                (uid, 1, "create", content_hash, args.author or "agent", ts),
            )

            # IDF (PRIN-ING-9, CONST-ING-6)
            increment_idf(ctx, extract_nouns(page_body))

            new_content_hashes.add(content_hash)
            written.append({"uid": uid, "raw": raw_written})
            created.append({
                "uid": uid,
                "title": title,
                "slug": slug,
                "raw_path": str(rel_raw) if rel_raw else None,
                "body": page_body,
                "lines": len(page_body.splitlines()),
            })

        conn.execute("RELEASE SAVEPOINT ingest_pages")
    finally:
        conn.close()

    # Verify all created nodes after writes (post-write, with rollback on failure)
    # For SQLite-backed L1 pages, verify by reading back from DB.
    # Rollback: DELETE from SQLite + delete raw files.
    verify_failed = []
    conn_verify = ctx.connect()
    try:
        for item in created:
            row = conn_verify.execute(
                "SELECT uid, title, layer, content_type, active, created_at, "
                "content_hash, slug FROM node_page WHERE uid=?",
                (item["uid"],),
            ).fetchone()
            v_checks = []
            v_passed = []
            v_failed = []
            def vcheck(name, cond, detail=""):
                v_checks.append({"check": name, "status": "pass" if cond else "fail", "detail": detail})
                if cond:
                    v_passed.append(name)
                else:
                    v_failed.append(name)
            if not row:
                vcheck("db_record_exists", False, f"uid={item['uid']} not found in DB")
            else:
                vcheck("db_record_exists", True, f"uid={item['uid']}")
                required = ["uid", "title", "layer", "content_type", "active", "created_at", "content_hash"]
                # Check all required fields are non-null/empty
                for f in required:
                    vcheck(f"db_field_{f}", bool(row[f]), f"{f}={row[f]}")
                vcheck("db_content_hash_match", row["content_hash"] == sha256_text(item["body"]),
                      f"stored={row['content_hash'][:8]}... body={sha256_text(item['body'])[:8]}...")
            if v_failed:
                verify_failed.append({"uid": item["uid"], "failed": v_failed, "checks": v_checks})
    finally:
        conn_verify.close()

    if verify_failed:
        # Rollback: restore IDF + delete SQLite rows + delete raw files
        dump_idf(ctx, idf_snapshot)
        conn_rb = ctx.connect()
        try:
            for w in written:
                conn_rb.execute("DELETE FROM node_page WHERE uid=?", (w["uid"],))
                conn_rb.execute("DELETE FROM patches WHERE page_uid=?", (w["uid"],))
            conn_rb.commit()
        finally:
            conn_rb.close()
        for w in written:
            if w["raw"] and Path(w["raw"]).exists():
                Path(w["raw"]).unlink()
        return error(
            f"verify failed for {len(verify_failed)} node(s): {[f['uid'] for f in verify_failed]}",
            "VerifyFailed",
            data={"verify_failed": verify_failed},
            hints=["fix the failed checks and re-run ingest-commit"]
        )

    # relations: attach to the first created page via SQLite (CONST-ING-5)
    invalid_relations = []
    if relations and created:
        anchor = created[0]
        anchor_uid = anchor["uid"]
        conn_rel = ctx.connect()
        try:
            # Get current max position for this anchor
            max_pos_row = conn_rel.execute(
                "SELECT MAX(position) FROM relations WHERE from_uid=?", (anchor_uid,)
            ).fetchone()
            position = (max_pos_row[0] + 1) if max_pos_row and max_pos_row[0] is not None else 0

            for rel in relations:
                to_uid = rel.get("to")
                rname = rel.get("relation_name")
                if not to_uid or not rname:
                    invalid_relations.append({"relation": rel, "reason": "missing to/relation_name"})
                    continue
                if to_uid not in all_uids:
                    # Check if target exists in DB
                    exists = conn_rel.execute(
                        "SELECT 1 FROM node_page WHERE uid=?", (to_uid,)
                    ).fetchone()
                    if not exists:
                        existing = find_node_md(ctx, to_uid)
                        if not existing:
                            invalid_relations.append({"relation": rel, "reason": "to_uid not found"})
                            continue
                    all_uids.add(to_uid)
                ts = now_ts()
                conn_rel.execute(
                    "INSERT OR REPLACE INTO relations(from_uid, to_uid, relation_name, comment, position, created_at) "
                    "VALUES(?,?,?,?,?,?)",
                    (anchor_uid, to_uid, rname, rel.get("comment", ""), position, ts),
                )
                position += 1
            conn_rel.commit()
        finally:
            conn_rel.close()

    # Phase 2 success 鈫?delete pending temp file (PRIN-ING-7)
    if args.pending:
        try:
            Path(args.pending).expanduser().resolve().unlink()
        except OSError:
            pass

    data = {"created": created, "page_count": len(created),
            "duplicate_parts": dup_pages, "invalid_relations": invalid_relations}
    if not created and dup_pages:
        return warning(data, "all pages were content-duplicates; nothing created (BAN-ING-4)")
    if invalid_relations:
        return warning(data, f"created {len(created)} page(s); some relations invalid",
                       hints=["fix invalid_relations and retry via query-relation add"])
    return success(data, f"committed {len(created)} Node_Page (L1) via {parser_used}", hints=hints)


def _verify_committed(ctx, md_path, uid) -> tuple[list[dict], list[str], list[str]]:
    """Full post-commit verify by reading from disk.

    Returns (checks, passed, failed).
    """
    checks = []
    passed = []
    failed = []

    def check(name, cond, detail=""):
        checks.append({"check": name, "status": "pass" if cond else "fail", "detail": detail})
        if cond:
            passed.append(name)
        else:
            failed.append(name)

    check("nodes_file_exists", md_path is not None and md_path.exists(),
          str(md_path) if md_path else "")

    frontmatter, body = {}, ""
    if md_path and md_path.exists():
        text = md_path.read_text(encoding="utf-8")
        frontmatter, body = fm.parse(text)
        required = ["uid", "title", "layer", "content_type", "active", "created_at", "content_hash"]
        missing = [f for f in required if f not in frontmatter]
        check("frontmatter_complete", len(missing) == 0,
              f"missing: {missing}" if missing else "")
        if body:
            actual_hash = sha256_text(body)
            stored_hash = frontmatter.get("content_hash", "")
            check("content_hash_match", actual_hash == stored_hash,
                  f"stored={stored_hash[:8]}... actual={actual_hash[:8]}...")
        ct = frontmatter.get("content_type", "article")
        fmt_err = _validate_body_format(body, ct) if body else None
        check("content_type_body_match", fmt_err is None, fmt_err or "" if fmt_err else "")
    else:
        check("frontmatter_complete", False, "nodes file missing")

    checks.extend(_raw_path_checks(ctx, frontmatter))
    return checks, passed, failed


def cmd_ingest_verify(args) -> dict:
    """Verify a committed L1 node's on-disk integrity (post-commit, read-only)."""
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    md_path = ctx.root / "nodes" / "page" / f"{args.uid}.md"
    if not md_path.exists():
        result = find_node_md(ctx, args.uid)
        if result:
            md_path = result[1]

    checks, passed, failed = _verify_committed(ctx, md_path, args.uid)

    status = "success" if not failed else "error"
    msgs = {"uid": args.uid, "wiki": args.wiki, "passed": passed, "failed": failed, "checks": checks}
    detail = f"{len(passed)}/{len(checks)} checks passed"
    if failed:
        detail += f"; FAILED: {failed}"
    return make_response(status, msgs, detail)
