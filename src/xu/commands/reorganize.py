"""reorganize — atomic node_path migration (PRIN-ARCH-25).

Moves a Page from one node_path partition to another:
- nodes/page/<old>/<slug>.md  →  nodes/page/<new>/<slug>.md
- raws/<old>/<filename>        →  raws/<new>/<filename>
- frontmatter node_path field updated

Files updated first; frontmatter updated last so failure leaves
filesystem as source of truth for recovery.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from ..utils.frontmatter import parse as fm_parse, render as fm_render
from ..utils.paths import atomic_write_text, safe_node_path
from ..utils.response import error, success, warning
from ..utils.wiki import resolve_wiki, find_node_md


def cmd_reorganize(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    try:
        new_node_path = safe_node_path(args.new_node_path)
    except ValueError as e:
        return error(str(e), "BadNodePath")

    result = find_node_md(ctx, args.uid)
    if not result:
        return error(f"node not found: {args.uid}", "NodeNotFound")
    fm_dict, body = result
    if not fm_dict:
        return error(f"node not found: {args.uid}", "NodeNotFound")

    if fm_dict.get("layer") != "Page":
        return error(f"reorganize is only for Page nodes; {fm_dict.get('layer')} not supported",
                     "UnsupportedLayer")

    old_node_path = fm_dict.get("node_path") or ""
    slug = fm_dict.get("slug") or args.uid

    if old_node_path == new_node_path:
        return warning(
            {"uid": args.uid, "node_path": old_node_path},
            f"node {args.uid} is already at node_path={old_node_path!r}; no move needed",
        )

    new_rel_md = f"nodes/page/{new_node_path}/{slug}.md" if new_node_path \
        else f"nodes/page/{slug}.md"
    new_md_path = ctx.root / new_rel_md

    old_md_path = _find_node_path(ctx, args.uid)
    if not old_md_path or not old_md_path.exists():
        return error("node file missing", "FileNotFound")

    if new_md_path.exists():
        return error(f"destination already exists: {new_rel_md}", "DstExists")

    new_md_path.parent.mkdir(parents=True, exist_ok=True)

    fm_dict["node_path"] = new_node_path
    fm_text_new = fm_render(fm_dict, body)
    atomic_write_text(new_md_path, fm_text_new)

    moved_raw = None
    old_raw = fm_dict.get("raw_path") or ""
    if old_raw:
        old_raw_abs = ctx.root / old_raw
        if old_raw_abs.exists():
            new_raw_rel = str(Path("raws") / new_node_path / Path(old_raw).name) \
                if new_node_path else str(Path("raws") / Path(old_raw).name)
            new_raw_abs = ctx.root / new_raw_rel
            new_raw_abs.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_raw_abs), str(new_raw_abs))
            moved_raw = new_raw_rel

    try:
        old_md_path.unlink()
    except OSError:
        pass

    return success(
        {"uid": args.uid,
         "old_node_path": old_node_path,
         "new_node_path": new_node_path,
         "old_rel_md": str(old_md_path.relative_to(ctx.root)),
         "new_rel_md": new_rel_md,
         "moved_raw": moved_raw},
        f"reorganized {args.uid} from {old_node_path!r} → {new_node_path!r}",
    )


def _find_node_path(ctx, uid: str) -> Path | None:
    """Find the .md path for a uid."""
    nodes_root = ctx.nodes_dir
    if not nodes_root.is_dir():
        return None
    for p in nodes_root.rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            fm_d, _ = fm_parse(text)
            if fm_d.get("uid") == uid:
                return p
        except Exception:
            continue
    return None
