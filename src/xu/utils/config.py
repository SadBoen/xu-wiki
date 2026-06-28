"""Global + wiki-internal config and the system registry.

Global config: ~/.xu-wiki/config.yaml  (wikis registry + api keys segment)
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
    return Path(os.path.expanduser("~/.xu-wiki"))


GLOBAL_DIR = _global_dir()
GLOBAL_CONFIG = GLOBAL_DIR / "config.yaml"
# PRIN-LOG-1: global process-layer audit log for commands without a wiki
# context (create / wikis / register / unregister / config / skills).
# Lives in ~/.local/share/xu-wiki/ (co-located with manifest, separate from
# GLOBAL_DIR ~/.xu-wiki/ so uninstall rmtree does not recreate config dirs).
# Commands WITH a resolvable --wiki write to
# <wiki>/.xu/audit.jsonl instead.
_LOCAL_SHARE = Path(os.path.expanduser("~/.local/share/xu-wiki"))
GLOBAL_AUDIT_LOG = _LOCAL_SHARE / "global_audit.jsonl"

_CONFIG_TEMPLATE = {
    "mineru": {"api_key": ""},
    "wikis": {},
}


def load_global_config() -> dict:
    if GLOBAL_CONFIG.exists():
        with open(GLOBAL_CONFIG, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return dict(_CONFIG_TEMPLATE)


def save_global_config(cfg: dict) -> None:
    """Persist `cfg` to GLOBAL_CONFIG and chmod 600 if any secret is present.

    (3.4 fix): the README has long told users to `chmod 600` their
    config.yaml after writing the MinerU key, but the CLI never
    enforced it — every subsequent `xu config set-mineru-key` would
    silently reset the file to umask-default permissions (644 on most
    systems), exposing the API key to other local users. We now
    auto-chmod 600 if the saved config contains a non-empty
    `mineru.api_key` (or any other future `*.api_key`).
    """
    header = ""
    if not GLOBAL_CONFIG.exists():
        header = (
            "# xu-wiki 全局配置文件\n"
            "# ========================\n"
            "# mineru.api_key: MinerU 云端解析服务的 API 密钥（用于 PDF 在线解析，markitdown 不可用时触发）\n"
            "# wikis: wiki 注册表（xu create / register 自动写入，不要手动编辑）\n"
            "#\n"
        )
    atomic_write_text(GLOBAL_CONFIG, header + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
    if _contains_secret(cfg):
        try:
            os.chmod(GLOBAL_CONFIG, 0o600)
        except OSError:
            pass


def _contains_secret(cfg: dict) -> bool:
    """True if cfg has any non-empty `*.api_key` (or `*.token`, `*.secret`)."""
    SENSITIVE_SUFFIXES = ("api_key", "token", "secret", "password")
    def walk(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, str) and any(k.endswith(s) for s in SENSITIVE_SUFFIXES):
                    if v:  # non-empty
                        return True
                if walk(v):
                    return True
        elif isinstance(obj, list):
            return any(walk(v) for v in obj)
        return False
    return walk(cfg)


def load_registry() -> dict:
    """Registry: {wikis: {name: {path, alias, created_at}}} — stored in GLOBAL_CONFIG."""
    if GLOBAL_CONFIG.exists():
        with open(GLOBAL_CONFIG, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
            return {"wikis": cfg.get("wikis", {})}
    return {"wikis": {}}


def save_registry(reg: dict) -> None:
    cfg: dict[str, Any] = {}
    if GLOBAL_CONFIG.exists():
        with open(GLOBAL_CONFIG, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    cfg["wikis"] = reg.get("wikis", {})
    header = ""
    if not GLOBAL_CONFIG.exists():
        header = (
            "# xu-wiki 全局配置文件\n"
            "# ========================\n"
            "# mineru.api_key: MinerU 云端解析服务的 API 密钥（用于 PDF 在线解析，markitdown 不可用时触发）\n"
            "# wikis: wiki 注册表（xu create / register 自动写入，不要手动编辑）\n"
            "#\n"
        )
    atomic_write_text(GLOBAL_CONFIG, header + yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False))
    if _contains_secret(cfg):
        try:
            os.chmod(GLOBAL_CONFIG, 0o600)
        except OSError:
            pass


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
