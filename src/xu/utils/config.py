"""Global + wiki-internal config and the system registry.

Global config: ~/.xu/config.yaml  (wikis registry + api keys segment)
Wiki config:   <wiki>/.xu/config.yaml
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from .paths import atomic_write_text

def _global_dir() -> Path:
    """Global config dir. Honors XU_HOME (useful for isolation/testing)."""
    override = os.environ.get("XU_HOME")
    if override:
        return Path(override).expanduser()
    return Path(os.path.expanduser("~/.xu"))


GLOBAL_DIR = _global_dir()
GLOBAL_CONFIG = GLOBAL_DIR / "config.yaml"
REGISTRY_FILE = GLOBAL_DIR / "registry.yaml"


def load_global_config() -> dict:
    if GLOBAL_CONFIG.exists():
        with open(GLOBAL_CONFIG, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def save_global_config(cfg: dict) -> None:
    atomic_write_text(GLOBAL_CONFIG, yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))


def load_registry() -> dict:
    """Registry: {wikis: {name: {path, alias, created_at}}}."""
    if REGISTRY_FILE.exists():
        with open(REGISTRY_FILE, encoding="utf-8") as f:
            return yaml.safe_load(f) or {"wikis": {}}
    return {"wikis": {}}


def save_registry(reg: dict) -> None:
    atomic_write_text(REGISTRY_FILE, yaml.safe_dump(reg, allow_unicode=True, sort_keys=False))


def registry_find(name_or_alias: str) -> tuple[str, dict] | None:
    reg = load_registry()
    wikis = reg.get("wikis", {})
    if name_or_alias in wikis:
        return name_or_alias, wikis[name_or_alias]
    for name, entry in wikis.items():
        if entry.get("alias") == name_or_alias:
            return name, entry
    return None


def load_wiki_config(wiki_root: str | Path) -> dict:
    cfg_path = Path(wiki_root) / ".xu" / "config.yaml"
    if cfg_path.exists():
        with open(cfg_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def save_wiki_config(wiki_root: str | Path, cfg: dict) -> None:
    cfg_path = Path(wiki_root) / ".xu" / "config.yaml"
    atomic_write_text(cfg_path, yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))


def cfg_get(cfg: dict, dotted: str, default: Any = None) -> Any:
    cur: Any = cfg
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur
