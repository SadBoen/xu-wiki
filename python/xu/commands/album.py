"""ingest-album — many images → one L1 Page (album scenario).

This is a sub-flow of the ingest SOP, NOT a two-phase split
(PRIN-ING-1 only governs the single-source pipeline). Each source
file is copied to raws/, its essential metadata (resolution, GPS,
capture time) is extracted via Pillow when available, and the L1
body is rendered as a YAML list of dicts (PRIN-ING-13 body-style
matching, same format as table/gallery content_type).

EXIF data beyond resolution + GPS + DateTime is intentionally NOT
extracted; the source files in raws/ remain the authoritative
carrier of full EXIF (design-docs/05-ingest §5.7).

Vision/OCR per-photo is OPT-IN via --vision. When requested but the
backend is not configured, the command returns a warning explaining
the intent was understood but no captions could be produced. The
Agent (SOP layer) is responsible for asking the user about vision
BEFORE invoking this command (PRIN-SOP-7).
"""
from __future__ import annotations

import json
import shutil
import yaml
from pathlib import Path
from typing import Any

from ..ingest.splitter import extract_nouns
from ..parsers.image_meta import read_image_meta
from ..utils.constants import (
    FM_ACTIVE,
    FM_CONTENT_HASH,
    FM_CREATED,
    FM_LAYER,
    FM_PATCHES,
    FM_SOURCE_HASH,
    FM_CONTENT_TYPE,
    FM_TITLE,
    FM_UID,
    IDF_CONSTANT,
)
from ..utils import db as sqlite_db
from ..utils.paths import (
    gen_uid,
    now_ts,
    safe_slug,
    sha256_file,
    sha256_text,
)
from ..utils.response import error, success, warning
from ..utils.wiki import resolve_wiki

ALBUM_LAYOUTS = ("table", "list")
ALBUM_CONTENT_TYPE = "gallery"
ALBUM_DEDUP_SCOPE = "all"


def _parse_captions(raw: str) -> dict[str, str]:
    """Parse --captions JSON: {filename: description_string}."""
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


def _render_body(rows: list[dict[str, Any]]) -> str:
    items = []
    for r in rows:
        w, h = r.get("width"), r.get("height")
        item = {
            "filename": r["filename"],
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


def _scan_fm_index(ctx):
    """Scan all Page frontmatter files. Returns (source_hash_map, content_hash_map)."""
    from ..commands.ingest import _scan_fm_index as _scan
    return _scan(ctx)


def cmd_ingest_album(args) -> dict:
    """Album scenario: many images → one L1 Page with table or list body."""
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(
            f"wiki not found: {args.wiki!r}", "WikiNotFound",
            hints=["check the name/path; do NOT auto-create (PRIN-SAFETY)"],
        )

    if not args.title:
        return error("ingest-album requires --title (CONST-ING-4)", "MissingTitle",
                     data={"missing": ["title"]})

    layout = (args.layout or "table").lower()
    if layout not in ALBUM_LAYOUTS:
        return error(
            f"invalid layout: {args.layout!r}; must be one of {ALBUM_LAYOUTS}",
            "InvalidLayout",
        )

    vision = bool(args.vision)

    # LLM decides raw placement via --raw-path; fallback to safe_slug(title).
    # Always places under raws/<raw_path_arg>/ (never flat).
    if getattr(args, 'raw_path', None):
        raw_path_arg = args.raw_path
    else:
        raw_path_arg = safe_slug(args.title)

    raw_files = [p.strip() for p in (args.files or "").split(",") if p.strip()]
    if not raw_files:
        return error(
            "ingest-album requires --files (comma-separated absolute paths)",
            "MissingFiles",
        )

    files: list[Path] = []
    for f in raw_files:
        p = Path(f).expanduser()
        if not p.is_absolute():
            return error(
                f"file path must be absolute: {p}", "PathNotAbsolute",
                data={"file": str(p)},
                hints=["album CLI requires absolute paths (hard rule 9)"],
            )
        if not p.is_file():
            return error(f"file not found: {p}", "FileNotFound", data={"file": str(p)})
        files.append(p)

    captions: dict[str, str] = {}
    if args.captions:
        try:
            captions = _parse_captions(args.captions)
        except (ValueError, json.JSONDecodeError) as e:
            return error(
                f"--captions invalid: {e}", "BadCaptionsJSON",
                data={"hint": "use a JSON object {\"001.jpeg\": \"船头整体\"}"},
            )

    rows: list[dict[str, Any]] = []
    album_raw_dir = ctx.raws_dir / raw_path_arg
    album_raw_dir.mkdir(parents=True, exist_ok=True)

    for src in files:
        sha = sha256_file(src)
        meta = read_image_meta(src)
        rel_raw = Path("raws") / raw_path_arg / src.name
        dst = ctx.root / rel_raw
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            shutil.copy2(src, dst)
        rows.append({
            "position": len(rows) + 1,
            "filename": src.name,
            "source_path": str(src),
            "source_hash": sha,
            "raw_rel_path": str(rel_raw).replace("\\", "/"),
            "width": meta.get("width"),
            "height": meta.get("height"),
            "gps": meta.get("gps"),
            "captured": meta.get("captured"),
            "caption": captions.get(src.name, ""),
        })

    # Level-2 dedup (CONST-ING-3): scan frontmatter for existing source_hash
    source_index, _ = _scan_fm_index(ctx)
    collides: list[dict[str, Any]] = []
    for r in rows:
        sh = r["source_hash"]
        if sh in source_index:
            existing_uid, existing_title, existing_active = source_index[sh]
            collides.append({
                "filename": r["filename"],
                "source_hash": sh,
                "existing_uid": existing_uid,
                "existing_title": existing_title,
                "existing_layer": "Page",
                "existing_active": existing_active,
            })
    if collides:
        return warning(
            {"collisions": collides, "checked": len(rows),
             "wiki": args.wiki, "title": args.title},
            f"{len(collides)} source file(s) already ingested; album rejected (BAN-ING-4)",
            hints=[
                "remove colliding files from --files, or use 'revise' to update the existing node",
                "an album cannot reuse a source_hash (CONST-ING-3 Level-2)",
            ],
        )

    body = _render_body(rows)
    content_hash = sha256_text(body)

    uid = gen_uid()
    base_slug = safe_slug(args.title)
    slug = f"{base_slug}-{uid}"
    ts = now_ts()

    # SQLite INSERT: write node + patch atomically (DB-only, no .md file)
    conn = ctx.connect()
    try:
        conn.execute(
            "INSERT INTO nodes("
            "uid, layer, content_type, title, slug, rel_md_path, "
            "content_hash, source_hash, active, attrs, created_at, updated_at, body"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                uid,
                "Page",
                ALBUM_CONTENT_TYPE,
                args.title,
                slug,
                None,           # rel_md_path: DB-only
                content_hash,
                rows[0]["source_hash"] if rows else None,
                1,
                json.dumps({
                    "album": {
                        "layout": layout,
                        "count": len(rows),
                        "vision": vision,
                        "sources": [
                            {
                                "filename": r["filename"],
                                "source_hash": r["source_hash"],
                                "raw_rel_path": r["raw_rel_path"],
                                "width": r["width"],
                                "height": r["height"],
                                "gps": r["gps"],
                                "captured": r["captured"],
                            }
                            for r in rows
                        ],
                    },
                }),
                ts,
                ts,
                body,
            ),
        )
        conn.execute(
            "INSERT INTO patches(page_uid, version, op, delta, author, created_at) "
            "VALUES (?,1,?,?,?,?)",
            (uid, "create", content_hash, args.author or "agent", ts),
        )
        sqlite_db.idf_increment(conn, body, extract_nouns_fn=extract_nouns, constant=IDF_CONSTANT)
        conn.commit()
    finally:
        conn.close()

    data = {
        "uid": uid,
        "title": args.title,
        "raw_path": str(Path("raws") / raw_path_arg),
        "layout": layout,
        "count": len(rows),
        "sources": [
            {k: r[k] for k in
             ("filename", "source_hash", "raw_rel_path",
              "width", "height", "gps", "captured")}
            for r in rows
        ],
    }
    hints = ["read by UID to view; revise to update captions"]
    if vision:
        hints.append(
            "vision intent was set; per-photo captions will be added "
            "when a vision backend is configured"
        )
    return success(
        data,
        f"album committed: {len(rows)} photos → 1 Node_Page (L1, content_type={ALBUM_CONTENT_TYPE})",
        hints=hints,
    )
