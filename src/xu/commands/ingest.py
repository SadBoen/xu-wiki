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
    FM_RAW_PATH,
    FM_SOURCE_HASH,
    FM_TEMPLATE,
    FM_TITLE,
    FM_UID,
    IDF_CONSTANT,
    REQUIRED_FM_FIELDS,
    LAYERS,
    TEMPLATES,
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
from ..utils.response import error, success, warning
from ..utils.wiki import resolve_wiki


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
    if args.template not in TEMPLATES:
        return error(f"invalid template: {args.template}", "InvalidTemplate")

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
                FM_TEMPLATE: args.template,
                FM_ACTIVE: True,           # bool, not 0/1 (CONST-ARCH-2)
                FM_CREATED: ts,
                FM_CONTENT_HASH: content_hash,
                FM_NODE_PATH: node_path,
                "digest": args.digest,
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
                "INSERT INTO nodes(uid, layer, template, title, node_path, slug, "
                "rel_md_path, raw_path, content_hash, source_hash, active, digest, "
                "attrs, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)",
                (uid, "Page", args.template, title, node_path, slug,
                 str(rel_md), str(rel_raw) if rel_raw else None, content_hash,
                 source_hash, args.digest, "{}", ts, ts),
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
