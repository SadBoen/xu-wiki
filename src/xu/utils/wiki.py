"""Wiki instance context: locate root, expose three-piece layout paths."""
from __future__ import annotations

from pathlib import Path

from . import db
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
    def pending_dir(self) -> Path:
        return self.root / "nodes" / "pending"

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
            (self.root / "pyproject.toml").exists()
            and self.raws_dir.is_dir()
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
