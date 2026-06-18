"""create — initialize a new wiki instance (02-create.md).

Builds the three-piece layout (raws/nodes/.xu), DB schema with all three
layers + patches/IDF derived tables, wiki-internal config, and a registry entry.
Builds in a temp dir then atomically renames (CONST-CRT-2).
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

import yaml

from ..utils import db
from ..utils.config import (
    load_registry,
    registry_find,
    save_registry,
)
from ..utils.constants import WIKI_FORMAT_VERSION, default_wiki_config
from ..utils.paths import now_ts
from ..utils.response import error, success, warning
from ..utils.wiki import is_wiki_root

NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _build_skeleton(target: Path, name: str) -> None:
    """Create full structure inside `target` (a fresh dir)."""
    (target / "raws").mkdir(parents=True)
    (target / "nodes" / "page").mkdir(parents=True)
    (target / "nodes" / "list").mkdir(parents=True)
    (target / "nodes" / "report").mkdir(parents=True)
    (target / "nodes" / "pending").mkdir(parents=True)
    (target / ".xu").mkdir(parents=True)

    # wiki marker (CONST-CRT-1)
    (target / "pyproject.toml").write_text(
        "[tool.xu-wiki]\nmarker = \"xu-wiki-project\"\n"
        f"name = \"{name}\"\n",
        encoding="utf-8",
    )

    # wiki-internal config (CONST-CRT-6)
    cfg = default_wiki_config(name)
    (target / ".xu" / "config.yaml").write_text(
        yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    # state.json
    (target / ".xu" / "state.json").write_text(
        '{"version": "%s", "created_at": %d}\n' % (WIKI_FORMAT_VERSION, now_ts()),
        encoding="utf-8",
    )

    # DB schema with all three layers + patches/IDF (CONST-CRT-6, PRIN-CRT-4/6)
    db.init_schema(target / ".xu" / "wiki.db")


def cmd_create(args) -> dict:
    name = args.name
    if not name:
        return error(
            "create requires --name (BAN-CRT-3)",
            "MissingName",
            hints=["provide an explicit --name; the program never auto-picks a name"],
        )
    if not NAME_RE.match(name):
        return error(
            f"invalid wiki name: {name!r} (CONST-CRT-4)",
            "InvalidName",
            hints=["name must be alnum/-/_ and <= 64 chars"],
        )

    # path normalization + symlink escape guard (CONST-CRT-5)
    raw_path = Path(args.path).expanduser()
    try:
        parent = raw_path.parent.resolve(strict=False)
        target = (parent / raw_path.name).resolve(strict=False)
    except (OSError, RuntimeError) as e:
        return error(f"path resolution failed: {e}", "PathError")

    # name uniqueness in registry (CONST-CRT-4)
    existing = registry_find(name)
    if existing and Path(existing[1]["path"]).resolve() != target:
        return error(
            f"wiki name {name!r} already registered at a different path (CONST-CRT-4)",
            "NameConflict",
            data={"existing_path": existing[1]["path"]},
        )

    # idempotency / already-a-wiki (BAN-CRT-1 exception, CONST-CRT-3)
    if target.exists():
        if is_wiki_root(target):
            _register(name, target, args.alias)
            return warning(
                {"path": str(target), "name": name},
                f"wiki already exists at {target}; reusing (CONST-CRT-3)",
                hints=["use as-is, or rm -rf and re-create to start fresh"],
            )
        if any(target.iterdir()):
            return error(
                f"target dir exists and is non-empty (BAN-CRT-1): {target}",
                "DirNotEmpty",
                hints=["choose an empty dir, or remove existing content yourself"],
            )

    # build in temp dir, then atomic rename (CONST-CRT-2).
    # The target dir is NOT created up-front. We build the entire skeleton
    # inside a sibling temp dir, then `os.replace` it into place as a single
    # atomic rename. On any failure we rmtree the temp dir and the target
    # is never touched (no half-built state).
    tmp_parent = target.parent
    tmp_parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix=".xu-create-", dir=str(tmp_parent)))
    try:
        _build_skeleton(tmp, name)
        os.replace(str(tmp), str(target))   # atomic on the same filesystem
    except Exception as e:  # rollback: leave no half-built artifact
        shutil.rmtree(tmp, ignore_errors=True)
        return error(f"create failed, rolled back: {e}", "CreateFailed")

    alias_warning = _register(name, target, args.alias)

    data = {
        "name": name,
        "path": str(target),
        "version": WIKI_FORMAT_VERSION,
        "layout": ["raws/", "nodes/page/", "nodes/list/", "nodes/report/", "nodes/pending/", ".xu/"],
        "tables": ["nodes", "patches", "idf", "relations", "evidence", "list_members"],
    }
    if alias_warning:
        return warning(data, alias_warning, hints=["alias not bound; pick another"])
    return success(
        data,
        f"created empty wiki '{name}' at {target}",
        hints=["next: xu-wiki ingest-commit to add Node_Page (L1)"],
    )


def _register(name: str, target: Path, alias: str | None) -> str | None:
    """Add/update registry entry. Returns a warning string if alias conflicts."""
    reg = load_registry()
    reg.setdefault("wikis", {})
    alias_msg = None
    bound_alias = alias
    if alias:
        for ename, entry in reg["wikis"].items():
            if ename == alias or entry.get("alias") == alias:
                alias_msg = f"alias {alias!r} conflicts (CONST-CRT-4); wiki created without alias"
                bound_alias = None
                break
    reg["wikis"][name] = {
        "path": str(target),
        "alias": bound_alias,
        "created_at": now_ts(),
    }
    save_registry(reg)
    return alias_msg
