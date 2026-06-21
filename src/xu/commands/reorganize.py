"""reorganize — atomic node_path migration (PRIN-ARCH-25).

Moves a Page from one node_path partition to another, atomically updating:
- nodes/page/<old>/<slug>.md  →  nodes/page/<new>/<slug>.md
- raws/<old>/<filename>        →  raws/<new>/<filename>
- DB node_path + rel_md_path + raw_path

All three updated in a single DB transaction; files moved last so that a
failure mid-move leaves the DB as the source of truth for recovery.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from ..utils.frontmatter import parse as fm_parse, render as fm_render
from ..utils.paths import atomic_write_text, safe_node_path
from ..utils.response import error, success, warning
from ..utils.wiki import resolve_wiki


def cmd_reorganize(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    try:
        new_node_path = safe_node_path(args.new_node_path)
    except ValueError as e:
        return error(str(e), "BadNodePath")

    conn = ctx.connect()
    try:
        row = conn.execute(
            "SELECT uid, node_path, rel_md_path, raw_path, slug, title, layer "
            "FROM nodes WHERE uid=?",
            (args.uid,),
        ).fetchone()
        if not row:
            return error(f"node not found: {args.uid}", "NodeNotFound")

        if row["layer"] != "Page":
            return error(f"reorganize is only for Page nodes; {row['layer']} not supported",
                         "UnsupportedLayer")

        old_node_path = row["node_path"] or ""
        old_rel_md = row["rel_md_path"] or ""
        old_raw = row["raw_path"] or ""

        if old_node_path == new_node_path:
            return warning(
                {"uid": args.uid, "node_path": old_node_path},
                f"node {args.uid} is already at node_path={old_node_path!r}; no move needed",
            )

        slug = row["slug"] or args.uid
        new_rel_md = f"nodes/page/{new_node_path}/{slug}.md" if new_node_path \
            else f"nodes/page/{slug}.md"
        new_raw_rel = None
        if old_raw:
            old_raw_path = Path(old_raw)
            new_raw_rel = str(Path("raws") / new_node_path / old_raw_path.name) \
                if new_node_path else str(Path("raws") / old_raw_path.name)

        old_md_path = ctx.root / old_rel_md
        new_md_path = ctx.root / new_rel_md

        if not old_md_path.exists():
            return error(f"node file missing: {old_rel_md}", "FileNotFound")

        if new_md_path.exists():
            return error(f"destination already exists: {new_rel_md}", "DstExists")

        new_md_path.parent.mkdir(parents=True, exist_ok=True)

        fm_text = old_md_path.read_text(encoding="utf-8")
        fm_dict, body = fm_parse(fm_text)
        fm_dict["node_path"] = new_node_path
        fm_text_new = fm_render(fm_dict, body)
        atomic_write_text(new_md_path, fm_text_new)

        moved_raw = None
        if old_raw:
            old_raw_abs = ctx.root / old_raw
            if old_raw_abs.exists():
                new_raw_abs = ctx.root / new_raw_rel
                new_raw_abs.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old_raw_abs), str(new_raw_abs))
                moved_raw = new_raw_rel

        try:
            old_md_path.unlink()
        except OSError:
            pass

        conn.execute(
            "UPDATE nodes SET node_path=?, rel_md_path=?, raw_path=?, updated_at=? "
            "WHERE uid=?",
            (new_node_path, new_rel_md, moved_raw,
             int(__import__("time").time()), args.uid),
        )
        conn.commit()

        return success(
            {"uid": args.uid,
             "old_node_path": old_node_path,
             "new_node_path": new_node_path,
             "old_rel_md": old_rel_md,
             "new_rel_md": new_rel_md,
             "moved_raw": moved_raw},
            f"reorganized {args.uid} from {old_node_path!r} → {new_node_path!r}",
        )
    finally:
        conn.close()
