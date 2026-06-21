"""ingest — two-phase L1 Node_Page creation (05-ingest.md).

Phase 1 (ingest-file): parse → write temporary file (system temp dir).
                        No node created.
Phase 2 (ingest-commit): validate → atomic write Page(s) + raws copy + patches v1
                         + IDF + relations. The ONLY write entry (PRIN-ING-1).
"""
from __future__ import annotations

import importlib
import json
import shutil
import tempfile

import yaml
from pathlib import Path

from ..ingest.relations_lru import add_relation
from ..ingest.splitter import extract_nouns, split_pages
from ..parsers.registry import parse_file
from ..utils import frontmatter as fm
from ..utils.config import cfg_get
from ..utils.db import idf_increment
from ..utils.constants import (
    FM_ACTIVE,
    FM_CONTENT_HASH,
    FM_CREATED,
    FM_LAYER,
    FM_NODE_PATH,
    FM_SOURCE_HASH,
    FM_CONTENT_TYPE,
    FM_TITLE,
    FM_UID,
    IDF_CONSTANT,
    CONTENT_TYPES,
)
from ..utils.paths import (
    atomic_write_text,
    gen_uid,
    now_ts,
    safe_node_path,
    safe_slug,
    sha256_file,
    sha256_text,
)
from ..utils.response import error, success, warning, make_response
from ..utils.wiki import resolve_wiki, find_node_md


def cmd_ingest_file(args) -> dict:
    """Phase 1: parse a source file into a temporary file. No node created.

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

    try:
        safe_node_path(args.node_path)
    except ValueError as e:
        return error(str(e), "BadNodePath")
    stem = safe_slug(src.stem)
    # Write to system temp directory (PRIN-ING-7 implementation detail)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix="-pre.md", prefix=f"{stem}-",
        dir=tempfile.gettempdir(), delete=False, encoding="utf-8"
    ) as f:
        text = _strip_frontmatter(res.text)
        meta_header = (
            f"<!-- xu-pending source={src} parser={res.parser} "
            f"source_hash={sha256_file(src)} -->\n\n"
        )
        f.write(meta_header + text)
        temp_path = Path(f.name)

    return success(
        {
            "pending": str(temp_path),
            "parser": res.parser,
            "source": str(src),
            "source_hash": sha256_file(src),
            "chars": len(text),
        },
        f"parsed via {res.parser} → pending temp file (Phase 1). No node created yet.",
        hints=[
            "review pending content, then run ingest-commit with --pending and --title",
            "Agent decides title/node_path/relations between phases (PRIN-ING-2)",
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
        node_path_arg = args.node_path
    elif args.pending:
        pending_path = Path(args.pending).expanduser()
        if not pending_path.is_file():
            return error(f"pending temp file not found: {pending_path}", "PendingNotFound")
        raw_text = pending_path.read_text(encoding="utf-8")
        meta, content = _parse_pending_header(raw_text)
        source_hash = meta.get("source_hash")
        parser_used = meta.get("parser", "unknown")
        raw_src_path = meta.get("source")
        node_path_arg = args.node_path
    else:
        return error("ingest-commit requires --pending or --native", "MissingInput")

    try:
        node_path = safe_node_path(node_path_arg or "")
    except ValueError as e:
        return error(str(e), "BadNodePath")

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

    conn = ctx.connect()
    try:
        # split into pages (PRIN-ING-4)
        max_lines = cfg_get(ctx.config, "ingest.page_split_lines", 300)
        pages = split_pages(content, max_lines)
        if not pages:
            return error("no content to commit after splitting", "EmptyContent")

        # Level-2 dedup: source file hash across ALL pages (CONST-ING-3,
        # PRIN-ING-3). Note: Level-2 is "所有 Page" — NOT filtered by active —
        # so re-ingesting the same source is caught even against a deactivated
        # page. (Level-1 below is active-only, per the design's contrast.)
        if source_hash:
            dup = conn.execute(
                "SELECT uid, title, active FROM nodes WHERE source_hash=? LIMIT 1",
                (source_hash,),
            ).fetchone()
            if dup:
                return warning(
                    {"existing_uid": dup["uid"], "existing_title": dup["title"],
                     "existing_active": bool(dup["active"]), "source_hash": source_hash},
                    f"source already ingested as {dup['uid']} (BAN-ING-4); not re-created",
                    hints=["use 'revise' to update; ingest never overwrites (PRIN-ING-3)"],
                )

        created = []
        dup_pages = []
        multi = len(pages) > 1
        for idx, page_body in enumerate(pages):
            page_body = page_body.rstrip()  # normalize to match fm.render storage

            # body format must match content_type (PRIN-ING-13)
            body_err = _validate_body_format(page_body, args.content_type)
            if body_err:
                return error(body_err, "BodyFormatMismatch")

            content_hash = sha256_text(page_body)
            # Level-1 dedup: body hash (CONST-ING-3)
            dup = conn.execute(
                "SELECT uid, title FROM nodes WHERE content_hash=? AND active=1 LIMIT 1",
                (content_hash,),
            ).fetchone()
            if dup:
                dup_pages.append({"part": idx + 1, "existing_uid": dup["uid"]})
                continue

            uid = gen_uid()
            title = args.title if not multi else f"{args.title} (part {idx + 1}/{len(pages)})"
            base_slug = safe_slug(args.title)
            slug = f"{base_slug}-{idx + 1}-{uid}" if multi else f"{base_slug}-{uid}"
            ts = now_ts()

            frontmatter = {
                FM_UID: uid,
                FM_TITLE: title,
                FM_LAYER: "Page",
                FM_CONTENT_TYPE: args.content_type,
                FM_ACTIVE: True,           # bool, not 0/1 (CONST-ARCH-2)
                FM_CREATED: ts,
                FM_CONTENT_HASH: content_hash,
                FM_NODE_PATH: node_path,
            }
            if source_hash:
                frontmatter[FM_SOURCE_HASH] = source_hash

            # physical layout: nodes/page/<node_path>/<slug>.md (PRIN-ARCH-19/23)
            rel_md = Path("nodes/page") / node_path / f"{slug}.md" if node_path \
                else Path("nodes/page") / f"{slug}.md"
            md_path = ctx.root / rel_md
            md_path.parent.mkdir(parents=True, exist_ok=True)
            doc = fm.render(frontmatter, page_body)
            atomic_write_text(md_path, doc)

            # copy raw into raws/ mirrored by node_path (PRIN-ING-6, PRIN-ARCH-25)
            rel_raw = None
            if raw_src_path and Path(raw_src_path).is_file() and idx == 0:
                rel_raw = (Path("raws") / node_path / Path(raw_src_path).name
                            ) if node_path else Path("raws") / Path(raw_src_path).name
                raw_dst = ctx.root / rel_raw
                raw_dst.parent.mkdir(parents=True, exist_ok=True)
                if not raw_dst.exists():
                    shutil.copy2(raw_src_path, raw_dst)

            # DB row
            conn.execute(
                "INSERT INTO nodes(uid, layer, content_type, title, node_path, slug, "
                "rel_md_path, raw_path, content_hash, source_hash, active, "
                "attrs, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?,?)",
                (uid, "Page", args.content_type, title, node_path, slug,
                 str(rel_md), str(rel_raw) if rel_raw else None, content_hash,
                 source_hash, "{}", ts, ts),
            )
            # patches v1 (PRIN-ING-10, CONST-ING-7)
            conn.execute(
                "INSERT INTO patches(page_uid, version, op, delta, author, created_at) "
                "VALUES(?,1,'create',?,?,?)",
                (uid, content_hash, args.author, ts),
            )
            # IDF (PRIN-ING-9, CONST-ING-6) — incremental update
            _update_idf(conn, page_body)

            created.append({"uid": uid, "title": title, "md_path": str(rel_md),
                            "raw_path": str(rel_raw) if rel_raw else None,
                            "lines": len(page_body.splitlines())})

        # relations: attach to the first created page (CONST-ING-5)
        invalid_relations = []
        if relations and created:
            anchor = created[0]["uid"]
            for rel in relations:
                to_uid = rel.get("to")
                rname = rel.get("relation_name")
                if not to_uid or not rname:
                    invalid_relations.append({"relation": rel, "reason": "missing to/relation_name"})
                    continue
                exists = conn.execute("SELECT 1 FROM nodes WHERE uid=?", (to_uid,)).fetchone()
                if not exists:
                    invalid_relations.append({"relation": rel, "reason": "to_uid not found"})
                    continue
                add_relation(conn, anchor, to_uid, rname, rel.get("comment", ""))

        conn.commit()

        # Phase 2 success → delete pending temp file (PRIN-ING-7)
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
        hints = ["query to retrieve; read --uid for full body"]
        if parser_used == "native":
            hints.insert(0, "DEPRECATED: --native is deprecated; use --pending for external documents (PRIN-ING-6)")
        return success(data, f"committed {len(created)} Node_Page (L1) via {parser_used}", hints=hints)
    except Exception as e:
        conn.rollback()
        uncommitted_pending = str(args.pending) if args.pending else None
        return error(
            f"commit failed, rolled back: {e}", type(e).__name__,
            data={"uncommitted_pending": uncommitted_pending},
            hints=["pending file retained — fix the error and re-run ingest-commit"]
        )
    finally:
        conn.close()


def _update_idf(conn, body: str) -> None:
    """Thin wrapper for backwards-compat; logic now lives in utils.db.idf_increment."""
    idf_increment(conn, body, extract_nouns_fn=extract_nouns, constant=IDF_CONSTANT)


def cmd_ingest_verify(args) -> dict:
    """Verify a committed L1 node's on-disk integrity.

    Checks (all read-only, non-destructive):
    1. DB record exists for the uid
    2. nodes/ markdown file exists and frontmatter has all required fields
    3. content_hash in DB matches SHA256(body) in the file
    4. raw_path file exists (if node has a source file, i.e. not --native)
    5. content_type matches body format (article/table/gallery)
    """
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    conn = ctx.connect()

    # 1. DB record
    row = conn.execute(
        "SELECT uid, layer, content_type, title, node_path, raw_path, "
        "content_hash, active FROM nodes WHERE uid=?",
        (args.uid,),
    ).fetchone()
    if not row:
        return error(f"uid {args.uid} not found in DB", "NodeNotFound")

    checks = []
    passed = []
    failed = []

    def check(name: str, condition: bool, detail: str = "") -> None:
        checks.append({"check": name, "status": "pass" if condition else "fail", "detail": detail})
        if condition:
            passed.append(name)
        else:
            failed.append(name)

    # 2. nodes/ file exists + frontmatter
    from ..utils.frontmatter import parse as fm_parse
    md_path = ctx.root / "nodes" / "page" / f"{args.uid}.md"
    if not md_path.exists():
        # try with slug-based path
        md_path = find_node_md(ctx, args.uid)

    check("nodes_file_exists", md_path is not None and md_path.exists(),
          str(md_path) if md_path else "")

    frontmatter, body = {}, ""
    if md_path and md_path.exists():
        text = md_path.read_text(encoding="utf-8")
        frontmatter, body = fm_parse(text)
        required = ["uid", "title", "layer", "content_type", "active", "created_at", "content_hash"]
        missing = [f for f in required if f not in frontmatter]
        check("frontmatter_complete", len(missing) == 0,
              f"missing: {missing}" if missing else "")
    else:
        checks.append({"check": "frontmatter_complete", "status": "fail", "detail": "nodes file missing"})
        failed.append("frontmatter_complete")

    # 3. content_hash match
    if body:
        actual_hash = sha256_text(body)
        stored_hash = row["content_hash"]
        match = actual_hash == stored_hash
        check("content_hash_match", match,
              f"stored={stored_hash[:8]}... actual={actual_hash[:8]}...")

    # 4. raw_path file exists (only for non-native ingests)
    raw_path_str = row["raw_path"]
    if raw_path_str:
        raw_file = ctx.root / raw_path_str
        check("raw_file_exists", raw_file.exists(), str(raw_file))
    else:
        checks.append({"check": "raw_file_exists", "status": "skip", "detail": "native ingest (no source file)"})

    # 5. content_type ↔ body format
    ct = row["content_type"] or frontmatter.get("content_type", "article")
    if body:
        fmt_err = _validate_body_format(body, ct)
        check("content_type_body_match", fmt_err is None, fmt_err or "")
    else:
        checks.append({"check": "content_type_body_match", "status": "skip", "detail": "empty body"})

    conn.close()

    status = "success" if not failed else "error"
    msgs = {
        "uid": args.uid,
        "wiki": args.wiki,
        "passed": passed,
        "failed": failed,
        "checks": checks,
    }
    detail = f"{len(passed)}/{len(checks)} checks passed"
    if failed:
        detail += f"; FAILED: {failed}"
    return make_response(status, msgs, detail)
