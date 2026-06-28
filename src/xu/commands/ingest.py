"""ingest — two-phase Node_Page creation (05-ingest.md).

Phase 1 (ingest-file): parse → write temporary file (system temp dir).
                        No node created.
Phase 2 (ingest-commit): validate → atomic write Page(s) + raws copy + patches v1
                         + relations. The ONLY write entry (PRIN-ING-1).
"""
from __future__ import annotations

import importlib
import json
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor

import yaml
from pathlib import Path
from typing import Any

from ..ingest.splitter import split_pages
from ..parsers.image_meta import read_image_meta
from ..parsers.registry import parse_file
from ..utils import frontmatter as fm
from ..utils.config import cfg_get
from ..utils.constants import (
    FM_ACTIVE,
    FM_CONTENT_HASH,
    FM_CREATED,
    FM_LAYER,
    FM_NODE_PATH,
    FM_PATCHES,
    FM_PARENT_UID,
    FM_RAW_PATH,
    FM_SOURCE_HASH,
    FM_SOURCE_HASHES,
    FM_SPLIT_INDEX,
    FM_CONTENT_TYPE,
    FM_TITLE,
    FM_UID,
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
from ..utils.wiki import resolve_wiki, find_node_md, find_by_source_hash


def _scan_fm_index(ctx) -> tuple[dict, dict]:
    """Scan all Page frontmatter files. Returns (source_hash_map, content_hash_map)."""
    source_map: dict[str, tuple[str, str, bool]] = {}
    content_map: dict[str, tuple[str, str]] = {}
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
                sh = fd.get("source_hash")
                if sh:
                    source_map[sh] = (uid, fd.get("title", ""), active)
                for _sh in (fd.get("source_hashes") or []):
                    if _sh:
                        source_map[_sh] = (uid, fd.get("title", ""), active)
                attrs = fd.get("attrs", {})
                for _s in (attrs.get("album", {}).get("sources") or []):
                    if isinstance(_s, dict) and (_sh := _s.get("source_hash")):
                        source_map[_sh] = (uid, fd.get("title", ""), active)
                ch = fd.get("content_hash")
                if ch:
                    content_map[ch] = (uid, fd.get("title", ""))
            except Exception:
                continue
    return source_map, content_map


# ---------------------------------------------------------------------------
# Album/gallery helpers (shared between Phase 1 and Phase 2)
# ---------------------------------------------------------------------------

ALBUM_LAYOUTS = ("table", "list")


def _parse_captions(raw: str) -> dict[str, str]:
    """Parse --captions JSON: {filename: description_string}."""
    if not raw:
        return {}
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("--captions must be a JSON object {filename: description}")
    out: dict[str, str] = {}
    for k, v in parsed.items():
        if isinstance(v, str):
            out[str(k)] = v
        elif isinstance(v, dict):
            out[str(k)] = str(v.get("description", "") or "")
        else:
            out[str(k)] = ""
    return out


def _render_body(rows: list[dict[str, Any]], layout: str = "table") -> str:
    items = []
    for r in rows:
        w, h = r.get("width"), r.get("height")
        item: dict[str, Any] = {
            "filename": r["filename"],
            "sha256": r["sha256"],
            "raw_rel_path": r["raw_rel_path"],
        }
        if w and h:
            item["resolution"] = f"{w}×{h}"
        if r.get("gps"):
            item["gps"] = r["gps"]
        if r.get("captured"):
            item["captured"] = r["captured"]
        if r.get("caption"):
            item["caption"] = r["caption"]
        items.append(item)
    return yaml.dump(items, allow_unicode=True, default_flow_style=False, sort_keys=False)


def cmd_ingest_file(args) -> dict:
    """Phase 1: parse source (single file or gallery) → write temp file. No node created.

    Gallery mode (--files): N images → temp file with YAML body.
    Single-file mode (--file): 1 file → parsed markdown temp file.

    Dedup is checked BEFORE calling the parser (especially expensive MinerU)
    to avoid wasting API calls on already-ingested sources (PRIN-ING-3).

    The temporary file is stored in the system temp directory
    (tempfile.gettempdir()), not in the wiki itself.
    """
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound",
                     hints=["check the name/path; do NOT auto-create (PRIN-SAFETY)"])

    # ---- Gallery mode: --files provided ----
    _files = getattr(args, "files", None)
    if _files is not None and _files != "":
        return _cmd_ingest_file_album(ctx, args)

    # ---- Single-file mode ----
    if getattr(args, "file", None) is None:
        return error("source file not provided", "FileNotFound")
    src = Path(args.file).expanduser()
    if not src.is_file():
        return error(f"source file not found: {src}", "FileNotFound")

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

    source_hash = sha256_file(src)
    dup_fm = find_by_source_hash(ctx, source_hash)
    if dup_fm:
        return error(
            f"source already ingested as {dup_fm['uid']} (BAN-ING-4); use 'revise' to update",
            "DuplicateSource",
            data={"existing_uid": dup_fm["uid"], "existing_title": dup_fm.get("title", ""),
                  "existing_active": dup_fm.get("active", True), "source_hash": source_hash},
        )

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
    with tempfile.NamedTemporaryFile(
        mode="w", suffix="-pre.md", prefix=f"{stem}-",
        dir=tempfile.gettempdir(), delete=False, encoding="utf-8"
    ) as f:
        text = _strip_frontmatter(res.text)
        meta_header = (
            f"<!-- xu-temp source={src} parser={res.parser} "
            f"source_hash={source_hash} -->\n\n"
        )
        f.write(meta_header + text)
        temp_path = Path(f.name)

    return success(
        {
            "temp": str(temp_path),
            "parser": res.parser,
            "source": str(src),
            "source_hash": source_hash,
            "chars": len(text),
        },
        f"parsed via {res.parser} → temp file (Phase 1). No node created yet.",
        hints=[
            "review temp content, then run ingest-commit with --temp and --title",
            "Agent decides title/node_path/relations between phases (PRIN-ING-2)",
            "if node_path is empty, all pages land at nodes/page/ root — consider passing --node-path to organize by category (e.g. certificates/qsa, contracts/ta)",
        ],
    )


def _cmd_ingest_file_album(ctx, args) -> dict:
    """Phase 1 for gallery mode: copy raws + extract meta + write temp file."""
    layout = (args.layout or "table").lower()
    if layout not in ALBUM_LAYOUTS:
        return error(f"invalid layout: {args.layout!r}; must be one of {ALBUM_LAYOUTS}",
                     "InvalidLayout")
    vision = bool(getattr(args, "vision", False))

    raw_files = [p.strip() for p in args.files.split(",") if p.strip()]
    if not raw_files:
        return error("ingest-file --files requires comma-separated absolute paths",
                     "MissingFiles")

    files: list[Path] = []
    for f in raw_files:
        p = Path(f).expanduser()
        if not p.is_absolute():
            return error(f"file path must be absolute: {p}", "PathNotAbsolute",
                         data={"file": str(p)})
        if not p.is_file():
            return error(f"file not found: {p}", "FileNotFound", data={"file": str(p)})
        files.append(p)

    captions: dict[str, str] = {}
    if getattr(args, "captions", None):
        try:
            captions = _parse_captions(args.captions)
        except (ValueError, json.JSONDecodeError) as e:
            return error(f"--captions invalid: {e}", "BadCaptionsJSON",
                         data={"hint": 'use a JSON object {"001.jpeg": "船头整体"}'})

    try:
        node_path = safe_node_path(args.node_path or "")
    except ValueError as e:
        return error(str(e), "BadNodePath")

    title = args.title or safe_slug(args.files.split(",")[0].strip())

    # ---- Phase 1 dedup: build source_index before processing ----
    source_index, _ = _scan_fm_index(ctx)

    # ---- Parallel: sha256 + meta ----
    def process_one(src: Path) -> dict[str, Any]:
        sha = sha256_file(src)
        meta = read_image_meta(src)
        return {
            "filename": src.name,
            "source_path": str(src),
            "sha256": sha,
            "raw_rel_path": str(Path("raws") / Path(node_path) / src.name if node_path
                           else Path("raws") / src.name).replace("\\", "/"),
            "width": meta.get("width"),
            "height": meta.get("height"),
            "gps": meta.get("gps"),
            "captured": meta.get("captured"),
            "caption": captions.get(src.name, ""),
        }

    with ThreadPoolExecutor() as executor:
        all_rows: list[dict[str, Any]] = list(executor.map(process_one, files))

    # ---- Split into new vs duplicate ----
    new_rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in all_rows:
        sh = item["sha256"]
        if sh and sh in source_index:
            existing_uid, existing_title, existing_active = source_index[sh]
            skipped.append({
                "filename": item["filename"],
                "source_hash": sh,
                "existing_uid": existing_uid,
                "existing_title": existing_title,
            })
        else:
            new_rows.append(item)

    if not new_rows:
        return warning(
            {"skipped": skipped, "images": 0, "wiki": args.wiki},
            "all images already ingested",
            hints=["remove duplicates from --files and re-run Phase 1"],
        )

    # ---- Copy new images to raws/ ----
    album_raw_dir = ctx.raws_dir / (Path(node_path) if node_path else Path("."))
    album_raw_dir.mkdir(parents=True, exist_ok=True)
    for item in new_rows:
        src = Path(item["source_path"])
        dst = ctx.root / item["raw_rel_path"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copy2(src, dst)

    body = _render_body(new_rows, layout)

    frontmatter_dict = {
        "mode": "album",
        "title": title,
        "node_path": node_path,
        "layout": layout,
        "vision": vision,
    }
    yaml_header = yaml.dump(frontmatter_dict, allow_unicode=True, default_flow_style=False)
    temp_content = f"---\n{yaml_header}---\n{body}"

    stem = safe_slug(title)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix="-pre.md", prefix=f"{stem}-",
        dir=tempfile.gettempdir(), delete=False, encoding="utf-8"
    ) as f:
        f.write(temp_content)
        temp_path = Path(f.name)

    hints = [
        "review temp content, then run ingest-commit with --temp --title --content-type gallery",
        "if node_path is empty, all pages land at nodes/page/ root",
    ]
    if skipped:
        hints.insert(0, f"{len(skipped)} duplicate image(s) skipped; see data.skipped for details")
    return success(
        {
            "temp": str(temp_path),
            "parser": "album",
            "source": ", ".join(str(f) for f in files),
            "source_hash": new_rows[0]["sha256"] if new_rows else None,
            "chars": len(body),
            "images": len(new_rows),
            "skipped": skipped,
        },
        f"album Phase 1: {len(new_rows)} new images → temp file ({len(skipped)} duplicates skipped).",
        hints=hints,
    )


def _parse_temp_header(text: str) -> tuple[dict, str]:
    """Parse temp file: supports both HTML-comment style and YAML-frontmatter style.

    HTML-comment style (legacy single-file):
        <!-- xu-temp source=/path parser=text source_hash=abc -->

    YAML frontmatter style (gallery/album):
        ---
        mode: album
        title: 2026WWC参展
        node_path: events/2026wwc
        layout: table
        vision: false
        source_hashes:
          - sha256:abc
          - sha256:def
        sources:
          - filename: 001.jpeg
            source_hash: sha256:abc
            raw_rel_path: raws/events/2026wwc/001.jpeg
            ...
        ---
        - filename: 001.jpeg
          raw_rel_path: raws/events/2026wwc/001.jpeg
          ...
    """
    meta: dict = {}

    # HTML-comment style (single-file / legacy)
    if text.startswith("<!-- xu-temp"):
        end = text.find("-->")
        if end != -1:
            header = text[len("<!-- xu-temp"):end].strip()
            for tok in header.split():
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    meta[k] = v
            body = text[end + 3:].lstrip("\n")
            return meta, body

    # YAML frontmatter style (gallery)
    if text.startswith("---"):
        end = text.find("\n---")
        if end != -1:
            try:
                front = yaml.safe_load(text[:end + 1])
                if isinstance(front, dict):
                    meta = front
                body = text[end + 4:].lstrip("\n")
                return meta, body
            except yaml.YAMLError:
                pass

    return meta, text


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
    """Phase 2: validate + atomic write Page(s) + raws copy + patches v1 + relations.

    --temp: path to Phase 1 temp file (required for normal flow).
    --native: deprecated, bypasses Phase 1 (no temp file, no source copy to raws/).

    Gallery mode (mode=album in temp meta): dedup by per-image source_hash,
    skip duplicate images, render attrs.album.sources.
    """
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound",
                     hints=["check the name/path; do NOT auto-create (PRIN-SAFETY)"])

    source_hash = None
    raw_src_path = None
    parser_used = "native"
    temp_meta: dict = {}
    if args.native:
        if not args.source:
            return error(
                "--native requires --source <abs-path or URL> (PRIN-ING-6: local sources must be copyable to raws/; URL sources are stored as-is)",
                "MissingSource",
                hints=["--source must be an absolute path to the source file, or a http:// / https:// URL"],
            )
        src_path = Path(args.source).expanduser()
        is_url = args.source.startswith(("http://", "https://"))
        if not is_url and not src_path.is_file():
            return error(f"source file not found: {src_path}", "FileNotFound")
        content = args.native
        raw_src_path = args.source  # URL stored as-is; local path stored as resolved string
        source_hash = sha256_text(args.native)
        node_path_arg = args.node_path
    elif args.temp:
        temp_file_path = Path(args.temp).expanduser()
        if not temp_file_path.is_file():
            return error(f"temp file not found: {temp_file_path}", "TempNotFound")
        raw_text = temp_file_path.read_text(encoding="utf-8")
        temp_meta, content = _parse_temp_header(raw_text)
        source_hash = temp_meta.get("source_hash")
        parser_used = temp_meta.get("parser", "unknown")
        raw_src_path = temp_meta.get("source")
        node_path_arg = args.node_path
    else:
        return error("ingest-commit requires --temp or --native", "MissingInput")

    try:
        node_path = safe_node_path(node_path_arg or "")
    except ValueError as e:
        return error(str(e), "BadNodePath")

    if not args.title:
        return error("ingest-commit requires --title (CONST-ING-4)", "MissingTitle",
                     data={"missing": ["title"]})
    if args.content_type not in CONTENT_TYPES:
        return error(f"invalid content-type: {args.content_type}", "InvalidContentType")

    # ---- Gallery mode (mode=album): delegate to dedicated handler ----
    if temp_meta.get("mode") == "album":
        return _cmd_ingest_commit_album(ctx, args, temp_meta, content)

    # split into pages (PRIN-ING-4)
    max_lines = cfg_get(ctx.config, "ingest.page_split_lines", 300)
    pages = split_pages(content, max_lines)
    if not pages:
        return error("no content to commit after splitting", "EmptyContent")

    _, content_index = _scan_fm_index(ctx)

    created = []
    dup_pages = []
    multi = len(pages) > 1
    first_uid = gen_uid()
    new_content_hashes: set[str] = set()

    written: list[dict] = []

    for idx, page_body in enumerate(pages):
        page_body = page_body.rstrip()

        body_err = _validate_body_format(page_body, args.content_type)
        if body_err:
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

        frontmatter = {
            FM_UID: uid,
            FM_TITLE: title,
            FM_LAYER: "Page",
            FM_CONTENT_TYPE: args.content_type,
            FM_ACTIVE: True,
            FM_CREATED: ts,
            FM_CONTENT_HASH: content_hash,
            FM_NODE_PATH: node_path,
            FM_SPLIT_INDEX: split_index,
            FM_PARENT_UID: parent_uid,
            FM_PATCHES: [{"op": "create", "delta": content_hash,
                          "created_at": ts}],
        }
        if source_hash:
            frontmatter[FM_SOURCE_HASH] = source_hash

        rel_md = Path("nodes/page") / node_path / f"{slug}.md" if node_path \
            else Path("nodes/page") / f"{slug}.md"
        md_path = ctx.root / rel_md
        md_path.parent.mkdir(parents=True, exist_ok=True)

        rel_raw = None
        raw_written = None
        if raw_src_path and Path(raw_src_path).is_file() and idx == 0:
            rel_raw = (Path("raws") / node_path / Path(raw_src_path).name
                        ) if node_path else Path("raws") / Path(raw_src_path).name
            raw_dst = ctx.root / rel_raw
            raw_dst.parent.mkdir(parents=True, exist_ok=True)
            if not raw_dst.exists():
                shutil.copy2(raw_src_path, raw_dst)
            raw_written = raw_dst
            frontmatter[FM_RAW_PATH] = str(rel_raw)

        doc = fm.render(frontmatter, page_body)
        atomic_write_text(md_path, doc)

        new_content_hashes.add(content_hash)
        written.append({"md": md_path, "raw": raw_written})
        created.append({"uid": uid, "title": title, "md_path": str(rel_md),
                        "raw_path": str(rel_raw) if rel_raw else None,
                        "body": page_body,
                        "lines": len(page_body.splitlines())})

    verify_failed = []
    for item in created:
        md_p = ctx.root / str(item["md_path"])
        v_checks, v_passed, v_failed = _verify_committed(ctx, md_p, item["uid"])
        if v_failed:
            verify_failed.append({"uid": item["uid"], "failed": v_failed, "checks": v_checks})

    if verify_failed:
        for w in written:
            if w["md"].exists():
                w["md"].unlink()
            if w["raw"] and w["raw"].exists():
                w["raw"].unlink()
        return error(
            f"verify failed for {len(verify_failed)} node(s): {[f['uid'] for f in verify_failed]}",
            "VerifyFailed",
            data={"verify_failed": verify_failed},
            hints=["fix the failed checks and re-run ingest-commit"]
        )

    if args.temp:
        try:
            Path(args.temp).expanduser().resolve().unlink()
        except OSError:
            pass

    data = {"created": created, "page_count": len(created),
            "duplicate_parts": dup_pages}
    if not created and dup_pages:
        return warning(data, "all pages were content-duplicates; nothing created (BAN-ING-4)")
    hints = ["query to retrieve; read --uid for full body"]
    if parser_used == "native":
        hints.insert(0, "DEPRECATED: --native is deprecated; use --temp for external documents (PRIN-ING-6)")
    if created and str(created[0]["md_path"]).startswith("nodes/page/"):
        bare = str(created[0]["md_path"])[len("nodes/page/"):]
        if "/" not in bare:
            hints.append("node_path is empty — all pages are piling at nodes/page/ root; future ingest should pass --node-path to organize by category")
    return success(data, f"committed {len(created)} Node_Page via {parser_used}", hints=hints)


def _cmd_ingest_commit_album(ctx, args, meta: dict, body: str) -> dict:
    """Phase 2 commit handler for gallery mode (mode=album in temp meta).

    Phase 1 already:
    - copied all images to raws/
    - extracted metadata (width, height, gps, captured, caption)
    - rendered YAML body (all images)

    Phase 2 here:
    - Level-2 dedup: skip images whose source_hash already exists
    - content_hash: based on deduplicated body
    - render frontmatter with attrs.album.sources (only new images)
    - write .md
    """
    # Level-2 dedup: parse body to get source_hash per image
    source_index, _ = _scan_fm_index(ctx)
    all_body_items: list[dict] = yaml.safe_load(body) or []
    new_body_items: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for item in all_body_items:
        sh = item.get("sha256", "")
        if sh and sh in source_index:
            existing_uid, existing_title, existing_active = source_index[sh]
            skipped.append({
                "filename": item.get("filename", ""),
                "source_hash": sh,
                "existing_uid": existing_uid,
                "existing_title": existing_title,
                "existing_layer": "Page",
                "existing_active": existing_active,
            })
        else:
            new_body_items.append(item)

    if not new_body_items:
        return warning(
            {"skipped": skipped, "checked": len(all_body_items),
             "wiki": args.wiki, "title": args.title},
            "all images already ingested; nothing to commit",
            hints=[
                "remove skipped files from --files and re-run Phase 1",
                "or use 'revise' to update the existing node",
            ],
        )

    # Re-render body with only new (non-duplicate) images
    layout = meta.get("layout", "table")
    body = _render_body(new_body_items, layout)
    content_hash = sha256_text(body)

    uid = gen_uid()
    base_slug = safe_slug(args.title)
    slug = f"{base_slug}-{uid}"
    ts = now_ts()

    frontmatter: dict[str, Any] = {
        FM_UID: uid,
        FM_TITLE: args.title,
        FM_LAYER: "Page",
        FM_CONTENT_TYPE: "gallery",
        FM_ACTIVE: True,
        FM_CREATED: ts,
        FM_CONTENT_HASH: content_hash,
        FM_NODE_PATH: meta.get("node_path", ""),
        FM_PATCHES: [{"op": "create", "delta": content_hash,
                      "created_at": ts}],
        FM_SOURCE_HASHES: [item["sha256"] for item in new_body_items],
        "attrs": {
            "album": {
                "layout": layout,
                "count": len(new_body_items),
                "vision": bool(meta.get("vision", False)),
                "sources": [
                    {
                        "filename": item["filename"],
                        "source_hash": item["sha256"],
                        "raw_rel_path": item["raw_rel_path"],
                        "width": item.get("width"),
                        "height": item.get("height"),
                        "gps": item.get("gps"),
                        "captured": item.get("captured"),
                        "caption": item.get("caption", ""),
                    }
                    for item in new_body_items
                ],
            },
        },
    }

    node_path_val = meta.get("node_path", "")
    rel_md = Path("nodes/page") / node_path_val / f"{slug}.md" if node_path_val \
        else Path("nodes/page") / f"{slug}.md"
    md_path = ctx.root / rel_md
    md_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(md_path, fm.render(frontmatter, body))

    # Delete temp file
    if getattr(args, "temp", None):
        try:
            Path(args.temp).expanduser().resolve().unlink()
        except OSError:
            pass

    data = {
        "uid": uid,
        "title": args.title,
        "node_path": node_path_val,
        "layout": layout,
        "count": len(new_body_items),
        "skipped": skipped,
        "md_path": str(rel_md).replace("\\", "/"),
            "sources": [
                {
                    "filename": item["filename"],
                    "source_hash": item["sha256"],
                    "raw_rel_path": item["raw_rel_path"],
                    "width": item.get("width"),
                    "height": item.get("height"),
                    "gps": item.get("gps"),
                    "captured": item.get("captured"),
                    "caption": item.get("caption", ""),
                }
                for item in new_body_items
            ],
    }
    hints = ["read by UID to view; revise to update captions"]
    if skipped:
        hints.insert(0, f"{len(skipped)} duplicate image(s) skipped; see data.skipped for details")
    if meta.get("vision"):
        hints.append("vision intent was set; per-photo captions will be added when a vision backend is configured")
    return success(
        data,
        f"album committed: {len(new_body_items)} photos → 1 Node_Page (content_type=gallery)",
        hints=hints,
    )


def _raw_path_checks(ctx, frontmatter) -> list[dict]:
    """Check raw files exist and mirror node_path. Returns list of check dicts."""
    checks = []
    node_path = frontmatter.get("node_path", "")
    attrs = frontmatter.get("attrs", {})
    album_sources = attrs.get("album", {}).get("sources", []) if isinstance(attrs, dict) else []

    def add_check(name, status, detail=""):
        checks.append({"check": name, "status": status, "detail": detail})

    if album_sources:
        for src in album_sources:
            raw_rel = src.get("raw_rel_path", "") if isinstance(src, dict) else ""
            if not raw_rel:
                add_check("raw_file_exists", "fail", "source missing raw_rel_path")
                continue
            raw_file = ctx.root / raw_rel
            add_check("raw_file_exists", "pass" if raw_file.exists() else "fail", str(raw_file))
            if node_path:
                expected_prefix = f"raws/{node_path}"
                ok = raw_rel.startswith(expected_prefix + "/") or raw_rel == expected_prefix
                add_check("raw_path_node_path_mirror",
                         "pass" if ok else "fail",
                         f"raw_rel_path={raw_rel} should be under raws/{node_path}/" if not ok else "")
            else:
                add_check("raw_path_node_path_mirror", "skip", "node_path empty for album")
    elif raw_path_str := frontmatter.get("raw_path", ""):
        raw_file = ctx.root / raw_path_str
        add_check("raw_file_exists", "pass" if raw_file.exists() else "fail", str(raw_file))
        if node_path:
            expected_prefix = f"raws/{node_path}"
            ok = raw_path_str.startswith(expected_prefix + "/") or raw_path_str == expected_prefix
            add_check("raw_path_node_path_mirror",
                     "pass" if ok else "fail",
                     f"raw_path={raw_path_str} should be under raws/{node_path}/" if not ok else "")
        else:
            add_check("raw_path_node_path_mirror", "skip", "node_path empty")
    else:
        add_check("raw_file_exists", "skip", "raw_path not in frontmatter (pre-fix node or --native without source)")
        add_check("raw_path_node_path_mirror", "skip", "raw_path not in frontmatter (pre-fix node or --native without source)")
    return checks


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

    frontmatter: dict[str, Any] = {}
    body = ""
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
    """Verify a committed Page's on-disk integrity (post-commit, read-only)."""
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    md_path = ctx.root / "nodes" / "page" / f"{args.uid}.md"
    if not md_path.exists():
        result = find_node_md(ctx, args.uid)
        if result:
            md_path = Path(result[1])

    checks, passed, failed = _verify_committed(ctx, md_path, args.uid)

    status = "success" if not failed else "error"
    msgs = {"uid": args.uid, "wiki": args.wiki, "passed": passed, "failed": failed, "checks": checks}
    detail = f"{len(passed)}/{len(checks)} checks passed"
    if failed:
        detail += f"; FAILED: {failed}"
    return make_response(status, msgs, detail)
