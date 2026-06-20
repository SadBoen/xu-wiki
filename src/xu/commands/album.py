"""ingest-album — many images → one L1 Page (album scenario).

This is a sub-flow of the ingest SOP, NOT a two-phase split
(PRIN-ING-1 only governs the single-source pipeline). Each source
file is copied to raws/, its essential metadata (resolution, GPS,
capture time) is extracted via Pillow when available, and the L1
body is rendered as a markdown table or list — one row/entry per
photo (PRIN-ING-13 body-style matching).

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
from pathlib import Path
from typing import Any

from ..ingest.splitter import extract_nouns
from ..parsers.image_meta import read_image_meta
from ..utils import frontmatter as fm
from ..utils.paths import safe_slug, safe_node_path
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


def _render_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| # | Filename | Path | Resolution | GPS | Captured | Description |",
        "|---|----------|------|------------|-----|----------|-------------|",
    ]

    def esc(s: str) -> str:
        return (s or "").replace("|", "\\|")

    for r in rows:
        w, h = r.get("width"), r.get("height")
        res = f"{w}×{h}" if (w and h) else "—"
        gps = r.get("gps") or "—"
        captured = r.get("captured") or "—"
        desc = r.get("caption") or "—"
        lines.append(
            f"| {r['position']} | {esc(r['filename'])} | "
            f"`{esc(r['raw_rel_path'])}` | {res} | {esc(gps)} | "
            f"{esc(captured)} | {esc(desc)} |"
        )
    return "\n".join(lines) + "\n\n"


def _render_list(rows: list[dict[str, Any]]) -> str:
    lines = []
    for r in rows:
        w, h = r.get("width"), r.get("height")
        res = f"{w}×{h}" if (w and h) else "—"
        gps = r.get("gps") or "—"
        captured = r.get("captured") or "—"
        meta = f"`{r['raw_rel_path']}` — {res} — {gps} — {captured}"
        lines.append(f"- **{r['filename']}** — {meta}")
        if r.get("caption"):
            lines.append(f"  描述：{r['caption']}")
    return "\n".join(lines) + "\n\n"


def _render_marker(layout: str, count: int, vision: bool) -> str:
    return f"<!-- xu-album layout={layout} count={count} vision={'yes' if vision else 'no'} -->\n"


def _render_body(title: str, node_path: str, rows: list[dict[str, Any]],
                 layout: str, vision: bool) -> str:
    n = len(rows)
    vision_note = ""
    if vision:
        vision_note = "；vision 意图已标记（后端未配置时由 SOP 提示用户）"
    intro = (
        f"# {title}\n\n"
        f"> 相册主题：{title}；{n} 张图片；源文件存于 `raws/{node_path}/`"
        f"{vision_note}。\n\n"
    )
    body_main = _render_table(rows) if layout == "table" else _render_list(rows)
    return intro + body_main + _render_marker(layout, n, vision)


def cmd_ingest_album(args) -> dict:
    """Album scenario: many images → one L1 Page with table or list body.

    Single-shot (no two-phase). The L1 Page stores a markdown table or
    list with one row/entry per photo; minimal per-photo metadata
    (filename, source_hash, resolution, GPS, captured) goes into
    attrs.album.sources for queryability.
    """
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

    try:
        if args.node_path:
            node_path = safe_node_path(args.node_path)
        else:
            node_path = safe_slug(args.title)
    except ValueError as e:
        return error(str(e), "BadNodePath")

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
                f"file path must be absolute: {p}",
                "PathNotAbsolute",
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
                f"--captions invalid: {e}",
                "BadCaptionsJSON",
                data={"hint": "use a JSON object {\"001.jpeg\": \"船头整体\"}"},
            )

    rows: list[dict[str, Any]] = []
    album_raw_dir = ctx.raws_dir / (Path(node_path) if node_path else Path("."))
    album_raw_dir.mkdir(parents=True, exist_ok=True)

    for src in files:
        sha = sha256_file(src)
        meta = read_image_meta(src)
        rel_raw = (Path("raws") / Path(node_path) / src.name) if node_path \
            else Path("raws") / src.name
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

    conn = ctx.connect()
    try:
        # Level-2 dedup (CONST-ING-3): any source_hash already in DB
        # (single Page or another album) → album rejected (BAN-ING-4)
        collides: list[dict[str, Any]] = []
        for r in rows:
            dup = conn.execute(
                "SELECT uid, title, layer, active FROM nodes "
                "WHERE source_hash=? LIMIT 1",
                (r["source_hash"],),
            ).fetchone()
            if dup:
                collides.append({
                    "filename": r["filename"],
                    "source_hash": r["source_hash"],
                    "existing_uid": dup["uid"],
                    "existing_title": dup["title"],
                    "existing_layer": dup["layer"],
                    "existing_active": bool(dup["active"]),
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

        body = _render_body(args.title, node_path, rows, layout, vision)
        content_hash = sha256_text(body)

        uid = gen_uid()
        base_slug = safe_slug(args.title)
        slug = f"{base_slug}-{uid}"
        ts = now_ts()

        frontmatter = {
            FM_UID: uid,
            FM_TITLE: args.title,
            FM_LAYER: "Page",
            FM_CONTENT_TYPE: ALBUM_CONTENT_TYPE,
            FM_ACTIVE: True,
            FM_CREATED: ts,
            FM_CONTENT_HASH: content_hash,
            FM_NODE_PATH: node_path,
        }
        if rows:
            frontmatter[FM_SOURCE_HASH] = rows[0]["source_hash"]

        rel_md = (Path("nodes") / "page" / Path(node_path) / f"{slug}.md") \
            if node_path else Path("nodes") / "page" / f"{slug}.md"
        md_path = ctx.root / rel_md
        md_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(md_path, fm.render(frontmatter, body))

        primary_raw = str(Path("raws") / Path(node_path)) if node_path else "raws"
        attrs = json.dumps({
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
        }, ensure_ascii=False)

        conn.execute(
            "INSERT INTO nodes(uid, layer, content_type, title, node_path, slug, "
            "rel_md_path, raw_path, content_hash, source_hash, active, "
            "attrs, created_at, updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?,?)",
            (uid, "Page", ALBUM_CONTENT_TYPE, args.title, node_path, slug,
             str(rel_md).replace("\\", "/"), primary_raw.replace("\\", "/"),
             content_hash, rows[0]["source_hash"] if rows else None,
             attrs, ts, ts),
        )
        # patches v1 (PRIN-ING-10, CONST-ING-7)
        conn.execute(
            "INSERT INTO patches(page_uid, version, op, delta, author, created_at) "
            "VALUES(?,1,'create',?,?,?)",
            (uid, content_hash, args.author, ts),
        )
        # IDF incremental (PRIN-ING-9, CONST-ING-6)
        idf_increment(conn, body, extract_nouns_fn=extract_nouns, constant=IDF_CONSTANT)

        conn.commit()

        data = {
            "uid": uid,
            "title": args.title,
            "node_path": node_path,
            "layout": layout,
            "count": len(rows),
            "md_path": str(rel_md).replace("\\", "/"),
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
    except Exception as e:
        conn.rollback()
        return error(f"album commit failed, rolled back: {e}", type(e).__name__)
    finally:
        conn.close()
