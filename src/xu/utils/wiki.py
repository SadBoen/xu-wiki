"""Wiki instance context: locate root, expose four-piece layout paths."""

from __future__ import annotations

from pathlib import Path

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
        return self.root / "nodes" / "pages"

    @property
    def list_dir(self) -> Path:
        return self.root / "nodes" / "lists"

    @property
    def report_dir(self) -> Path:
        return self.root / "nodes" / "reports"

    @property
    def entity_dir(self) -> Path:
        return self.root / "nodes" / "entities"

    @property
    def xu_dir(self) -> Path:
        return self.root / ".xu"

    @property
    def log_path(self) -> Path:
        return self.root / ".xu" / "audit.jsonl"

    def is_valid(self) -> bool:
        return (
            self.raws_dir.is_dir() and self.nodes_dir.is_dir() and self.xu_dir.is_dir()
        )


def is_wiki_root(path: str | Path) -> bool:
    p = Path(path)
    return (p / ".xu" / "config.yaml").exists()


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


def write_node_frontmatter(ctx: WikiContext, uid: str, fm_node: dict) -> None:
    """Find node .md by uid and rewrite its frontmatter, preserving body."""
    nodes_root = ctx.nodes_dir
    if not nodes_root.is_dir():
        return
    for p in nodes_root.rglob("*.md"):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            parsed, body = _fm.parse(text)
            if parsed.get("uid") == uid:
                p.write_text(_fm.render(fm_node, body), encoding="utf-8")
                return
        except Exception:
            continue


def find_node_md(ctx: WikiContext, uid: str) -> tuple[dict, str] | None:
    """Find a node .md file by UID via fs walk. Returns (frontmatter, body) or None."""
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
    """Find a node by its source_hash via fs walk. Returns frontmatter or None.

    Used for Level-2 dedup — frontmatter is the source of truth (FS).
    """
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
