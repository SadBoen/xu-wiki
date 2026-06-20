"""ingest — L1 Node_Page creation.

ingest-file: parse source → create real node (UID, DB, raws/) with node_path="".
            The node is formal and queryable; only node_path is undetermined.
ingest-commit: update existing node's node_path (and title/digest/relations).
              Page splitting happens here (PRIN-ING-4).
"""
from __future__ import annotations

import importlib
import json
import shutil
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
    """Parse a source file and create a real node with node_path='' (pending assignment).

    The node is immediately formal: UID, DB record, raws/ copy all created.
    Only node_path is left empty — assign it via ingest-commit --uid.
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

    from ..utils.config import load_global_config
    mineru_key = load_global_config().get("mineru", {}).get("api_key", "")
    res = parse_file(src, mineru_key=mineru_key)
    if not res.ok:
        return error(
            f"all parsers failed for {src.name}",
            "ParseFailed",
            data={"file": str(src)},
        )

    # Validate node_path even though it's empty — catch invalid characters early
    try:
        safe_node_path(args.node_path)
    except ValueError as e:
        return error(str(e), "BadNodePath")

    text = _strip_frontmatter(res.text)
    source_hash = sha256_file(src)
    uid = gen_uid()
    ts = now_ts()

    # Slug from filename (title not yet known — will be set in ingest-commit)
    slug = safe_slug(src.stem)
    rel_md = Path("nodes/page") / f"{slug}-{uid}.md"
    md_path = ctx.root / rel_md
    md_path.parent.mkdir(parents=True, exist_ok=True)

    # Copy source to raws/ (PRIN-ING-6: every ingested source gets a physical copy)
    rel_raw = Path("raws") / Path(src.name)
    raw_dst = ctx.root / rel_raw
    raw_dst.parent.mkdir(parents=True, exist_ok=True)
    if not raw_dst.exists():
        shutil.copy2(src, raw_dst)

    frontmatter = {
        FM_UID: uid,
        FM_TITLE: src.stem,  # temporary; ingest-commit will override with real title
        FM_LAYER: "Page",
        FM_TEMPLATE: "article",
        FM_ACTIVE: True,
        FM_CREATED: ts,
        FM_CONTENT_HASH: sha256_text(text),
        FM_NODE_PATH: "",  # empty = pending path assignment
        FM_SOURCE_HASH: source_hash,
        "parser": res.parser,
    }
    doc = fm.render(frontmatter, text)
    atomic_write_text(md_path, doc)

    # DB record
    conn = ctx.connect()
    try:
        conn.execute(
            "INSERT INTO nodes(uid, layer, template, title, node_path, slug, "
            "rel_md_path, raw_path, content_hash, source_hash, active, digest, "
            "attrs, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)",
            (uid, "Page", "article", src.stem, "", slug,
             str(rel_md), str(rel_raw), sha256_text(text),
             source_hash, "", "{}", ts, ts),
        )
        conn.commit()
    finally:
        conn.close()

    return success(
        {
            "uid": uid,
            "parser": res.parser,
            "source": str(src),
            "source_hash": source_hash,
            "raw_path": str(rel_raw),
            "md_path": str(rel_md),
            "chars": len(text),
        },
        f"node {uid} created (node_path=''); assign path via ingest-commit --uid {uid}",
        hints=[f"ingest-commit --wiki {args.wiki} --uid {uid} --title '<title>' --node-path '<path>'"],
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
    """Update an existing node's node_path (and title/digest/relations).

    --uid: update existing node (created by ingest-file). Handles page splitting:
            if content splits into N pages, the original node is deactivated and
            N new active nodes are created.
    --pending: legacy migration — read old pending file, create real node, delete pending.
    --native: deprecated, creates node directly (no pending involved).
    """
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound",
                     hints=["check the name/path; do NOT auto-create (PRIN-SAFETY)"])

    conn = ctx.connect()
    try:
        # ---- Three input modes ----
        if args.uid:
            # Mode 1: update existing node by UID
            existing = conn.execute(
                "SELECT * FROM nodes WHERE uid=? AND active=1 LIMIT 1",
                (args.uid,),
            ).fetchone()
            if not existing:
                return error(f"node not found or inactive: {args.uid}", "NodeNotFound")
            existing = dict(existing)

            # Read content from the existing node's file
            md_file = ctx.root / existing["rel_md_path"]
            if not md_file.is_file():
                return error(f"node file missing: {md_file}", "NodeFileMissing")
            raw_text = md_file.read_text(encoding="utf-8")
            meta, content = fm.parse(raw_text)
            content = content.strip("\n")
            source_hash = existing.get("source_hash")
            parser_used = meta.get("parser", existing.get("template", "unknown"))
            raw_src_path = existing.get("raw_path")
            if raw_src_path:
                raw_src_path = str(ctx.root / raw_src_path)

            node_path_arg = args.node_path if args.node_path else ""
            title_arg = args.title if args.title else meta.get(FM_TITLE, existing["title"])

        elif args.pending:
            # Mode 2: legacy migration — old pending file → real node
            pending_path = Path(args.pending).expanduser()
            try:
                pending_path = pending_path.resolve()
                pending_path.relative_to(ctx.root.resolve())
            except (ValueError, OSError):
                return error("pending path must be inside the wiki (BAN-ING-5)", "PathNotWhitelisted")
            if not pending_path.is_file():
                return error(f"pending file not found: {pending_path}", "PendingNotFound")
            raw_text = pending_path.read_text(encoding="utf-8")
            meta, content = _parse_pending_header(raw_text)
            source_hash = meta.get("source_hash")
            parser_used = meta.get("parser", "unknown")
            raw_src_path = meta.get("source")
            node_path_arg = args.node_path if args.node_path else meta.get("node_path", "")
            title_arg = args.title if args.title else ""

            # Level-2 dedup for legacy migration
            if source_hash:
                dup = conn.execute(
                    "SELECT uid, title, active FROM nodes WHERE source_hash=? LIMIT 1",
                    (source_hash,),
                ).fetchone()
                if dup:
                    return warning(
                        {"existing_uid": dup["uid"], "existing_title": dup["title"],
                         "existing_active": bool(dup["active"]), "source_hash": source_hash},
                        f"source already ingested as {dup['uid']} (BAN-ING-4)",
                        hints=["use 'revise' to update; ingest never overwrites"],
                    )

        elif args.native:
            # Mode 3: --native (deprecated direct markdown)
            if not args.source:
                return error(
                    "--native requires --source <abs-path>",
                    "MissingSource",
                    hints=["--source must be an absolute path to the source file"],
                )
            src_path = Path(args.source).expanduser()
            if not src_path.is_file():
                return error(f"source file not found: {src_path}", "FileNotFound")
            content = args.native
            source_hash = sha256_text(args.native)
            parser_used = "native"
            raw_src_path = str(src_path)
            node_path_arg = args.node_path if args.node_path else ""
            title_arg = args.title if args.title else ""

            # Level-2 dedup for --native
            dup = conn.execute(
                "SELECT uid, title, active FROM nodes WHERE source_hash=? LIMIT 1",
                (source_hash,),
            ).fetchone()
            if dup:
                return warning(
                    {"existing_uid": dup["uid"], "existing_title": dup["title"],
                     "existing_active": bool(dup["active"]), "source_hash": source_hash},
                    f"source already ingested as {dup['uid']} (BAN-ING-4)",
                    hints=["use 'revise' to update; ingest never overwrites"],
                )
        else:
            return error("ingest-commit requires --uid, --pending, or --native", "MissingInput")

        if not title_arg:
            return error("ingest-commit requires --title", "MissingTitle",
                         data={"missing": ["title"]})
        if args.template not in TEMPLATES:
            return error(f"invalid template: {args.template}", "InvalidTemplate")

        try:
            node_path = safe_node_path(node_path_arg)
        except ValueError as e:
            return error(str(e), "BadNodePath")

        # relations parsing
        relations = []
        if args.relations:
            try:
                relations = json.loads(args.relations)
            except json.JSONDecodeError as e:
                return error(f"--relations must be valid JSON: {e}", "BadRelationsJSON")
            if not isinstance(relations, list):
                return error("--relations must be a JSON array", "BadRelationsType")

        # Page splitting (PRIN-ING-4)
        max_lines = cfg_get(ctx.config, "ingest.page_split_lines", 300)
        pages = split_pages(content, max_lines)
        if not pages:
            return error("no content to commit after splitting", "EmptyContent")

        created = []
        dup_pages = []
        multi = len(pages) > 1

        for idx, page_body in enumerate(pages):
            page_body = page_body.rstrip()
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
            title = title_arg if not multi else f"{title_arg} (part {idx + 1}/{len(pages)})"
            base_slug = safe_slug(title_arg)
            slug = f"{base_slug}-{idx + 1}-{uid}" if multi else f"{base_slug}-{uid}"
            ts = now_ts()

            frontmatter = {
                FM_UID: uid,
                FM_TITLE: title,
                FM_LAYER: "Page",
                FM_TEMPLATE: args.template,
                FM_ACTIVE: True,
                FM_CREATED: ts,
                FM_CONTENT_HASH: content_hash,
                FM_NODE_PATH: node_path,
                "digest": args.digest or "",
            }
            if source_hash:
                frontmatter[FM_SOURCE_HASH] = source_hash
            if parser_used:
                frontmatter["parser"] = parser_used

            rel_md = Path("nodes/page") / node_path / f"{slug}.md" if node_path \
                else Path("nodes/page") / f"{slug}.md"
            md_path = ctx.root / rel_md
            md_path.parent.mkdir(parents=True, exist_ok=True)
            doc = fm.render(frontmatter, page_body)
            atomic_write_text(md_path, doc)

            rel_raw = None
            if raw_src_path and Path(raw_src_path).is_file() and idx == 0:
                rel_raw = (Path("raws") / node_path / Path(raw_src_path).name
                            ) if node_path else Path("raws") / Path(raw_src_path).name
                raw_dst = ctx.root / rel_raw
                raw_dst.parent.mkdir(parents=True, exist_ok=True)
                if not raw_dst.exists():
                    shutil.copy2(raw_src_path, raw_dst)

            conn.execute(
                "INSERT INTO nodes(uid, layer, template, title, node_path, slug, "
                "rel_md_path, raw_path, content_hash, source_hash, active, digest, "
                "attrs, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?,?,?)",
                (uid, "Page", args.template, title, node_path, slug,
                 str(rel_md), str(rel_raw) if rel_raw else None, content_hash,
                 source_hash, args.digest or "", "{}", ts, ts),
            )
            conn.execute(
                "INSERT INTO patches(page_uid, version, op, delta, author, created_at) "
                "VALUES(?,1,'create',?,?,?)",
                (uid, content_hash, args.author, ts),
            )
            _update_idf(conn, page_body)
            created.append({"uid": uid, "title": title, "md_path": str(rel_md),
                            "raw_path": str(rel_raw) if rel_raw else None,
                            "lines": len(page_body.splitlines())})

        # Deactivate original node if we're replacing it (split case with --uid)
        if args.uid and created:
            conn.execute(
                "UPDATE nodes SET active=0, updated_at=? WHERE uid=?",
                (now_ts(), args.uid),
            )

        # Legacy pending file cleanup
        if args.pending:
            try:
                Path(args.pending).expanduser().resolve().unlink()
            except OSError:
                pass

        # Relations for the first created node
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

        data = {"created": created, "page_count": len(created),
                "duplicate_parts": dup_pages, "invalid_relations": invalid_relations}
        if not created and dup_pages:
            return warning(data, "all pages were content-duplicates; nothing created (BAN-ING-4)")
        if invalid_relations:
            return warning(data, f"created {len(created)} page(s); some relations invalid",
                           hints=["fix invalid_relations and retry via query-relation add"])
        hints = ["query to retrieve; read --uid for full body"]
        if parser_used == "native":
            hints.insert(0, "DEPRECATED: --native is deprecated")
        return success(data, f"committed {len(created)} Node_Page (L1)", hints=hints)

    except Exception as e:
        conn.rollback()
        return error(f"commit failed, rolled back: {e}", type(e).__name__,
                     data={"uid": getattr(args, "uid", None)},
                     hints=["fix the error and re-run ingest-commit"])
    finally:
        conn.close()


def _update_idf(conn, body: str) -> None:
    """Thin wrapper for backwards-compat; logic now lives in utils.db.idf_increment."""
    idf_increment(conn, body, extract_nouns_fn=extract_nouns, constant=IDF_CONSTANT)
