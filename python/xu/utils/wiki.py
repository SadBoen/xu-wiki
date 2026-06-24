"""Wiki instance context: locate root, expose three-piece layout paths."""
from __future__ import annotations

from pathlib import Path

from . import db
from . import frontmatter as _fm
from .config import load_wiki_config, registry_find


class WikiContext:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.config = load_wiki_config(self.root)

    @property
    def raws_dir(self) -> Path:
        return self.root / "raws"

    @property
    def nodes_dir(self) -> Path:
        return self.root / "nodes"

    @property
    def page_dir(self) -> Path:
        return self.root / "nodes" / "page"

    @property
    def list_dir(self) -> Path:
        return self.root / "nodes" / "list"

    @property
    def report_dir(self) -> Path:
        return self.root / "nodes" / "report"

    @property
    def xu_dir(self) -> Path:
        return self.root / ".xu"

    @property
    def db_path(self) -> Path:
        return self.root / ".xu" / "wiki.db"

    @property
    def log_path(self) -> Path:
        return self.root / ".xu" / "audit.jsonl"

    def connect(self):
        return db.connect(self.db_path)

    def is_valid(self) -> bool:
        return (
            self.raws_dir.is_dir()
            and self.nodes_dir.is_dir()
            and self.xu_dir.is_dir()
            and self.db_path.exists()
        )


def is_wiki_root(path: str | Path) -> bool:
    p = Path(path)
    return (p / ".xu" / "config.yaml").exists() and (p / ".xu" / "wiki.db").exists()


def resolve_wiki(name_or_path: str) -> WikiContext | None:
    """Resolve a wiki by registry name/alias, then by path."""
    found = registry_find(name_or_path)
    if found:
        _, entry = found
        root = Path(entry["path"])
        if is_wiki_root(root):
            return WikiContext(root)
    p = Path(name_or_path).expanduser()
    if is_wiki_root(p):
        return WikiContext(p)
    return None


def find_node_md(ctx: WikiContext, uid: str) -> tuple[dict, str] | None:
    """Find a node by UID. SQLite-first: query DB for rel_md_path, then read .md from fs.
    Falls back to fs walk if DB lookup fails or rel_md_path is NULL/empty.

    Returns (frontmatter, body) or None.
    """
    # SQLite-first: try to get rel_md_path from DB
    try:
        conn = ctx.connect()
        try:
            row = conn.execute(
                "SELECT rel_md_path FROM node_page WHERE uid=? AND active=1", (uid,)
            ).fetchone()
            if row and row["rel_md_path"]:
                md_path = ctx.root / row["rel_md_path"]
                text = md_path.read_text(encoding="utf-8")
                fm_dict, body = _fm.parse(text)
                return fm_dict, body
        finally:
            conn.close()
    except Exception:
        pass

    # Fallback: fs walk
    nodes_root = ctx.nodes_dir
    if not nodes_root.is_dir():
        return None
    for p in nodes_root.rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
            fm_dict, body = _fm.parse(text)
            if fm_dict.get("uid") == uid:
                return fm_dict, body
        except Exception:
            continue
    return None


def find_by_source_hash(ctx: WikiContext, source_hash: str) -> dict | None:
    """Find a node by its source_hash. Checks SQLite first, then FS fallback.

    Used for Level-2 dedup 閳?SQLite is authoritative for current L1 pages.
    """
    # SQLite first
    conn = ctx.connect()
    try:
        row = conn.execute(
            "SELECT uid, title, active, content_type, content_hash, source_hash, "
            "'Page' as layer, created_at FROM node_page WHERE source_hash=?",
            (source_hash,),
        ).fetchone()
        if row:
            return {
                "uid": row["uid"],
                "title": row["title"],
                "active": bool(row["active"]),
                "content_type": row["content_type"],
                "content_hash": row["content_hash"],
                "source_hash": row["source_hash"],
                "layer": row["layer"],
                "created_at": row["created_at"],
            }
    finally:
        conn.close()

    # Legacy FS fallback
    nodes_root = ctx.nodes_dir
    if not nodes_root.is_dir():
        return None
    for p in nodes_root.rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8")
            fm_dict, _ = _fm.parse(text)
            if fm_dict.get("source_hash") == source_hash:
                return fm_dict
        except Exception:
            continue
    return None
