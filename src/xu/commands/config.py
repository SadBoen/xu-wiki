"""SOP: config — alias management, register / unregister, global config.

Implements the four SOP-config capabilities promised in
design-docs/08-sop-architecture.md §5.5 / §六:

  xu-wiki alias set   --wiki <name|alias> --alias <new>
  xu-wiki alias unset --wiki <name|alias>
  xu-wiki alias show  --wiki <name|alias>
  xu-wiki register    --name <n> --path <abs> [--alias <a>]
  xu-wiki unregister  --name <n>
  xu-wiki config set_mineru_key   # reads from MINERU_API_KEY env
  xu-wiki config show             # secrets masked
  xu-wiki config path             # global config locations

All commands return 4-key JSON (status / data / message / hints) per
the protocol in design-docs/02-create.md and PRIN-ARCH-4.

Design constraints honored:
  [PRIN-SOP-5] All side effects (registry / global config) go through
               the existing utils.config layer; we never open() files
               directly.
  [BAN-SOP-2]  No bypass of CLI; this file IS the CLI implementation
               for SOP-config.
  [CONST-CRT-4] Alias conflicts are explicit errors here (the user is
               explicitly asking for a SET, unlike create where conflict
               is warning).
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from ..utils.config import (
    GLOBAL_DIR,
    load_global_config,
    load_registry,
    registry_find,
    save_global_config,
    save_registry,
)
from ..utils.paths import now_ts
from ..utils.response import error, success, warning

NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _validate_name(name: str):
    if not name or not NAME_RE.match(name):
        return error(
            f"invalid wiki name: {name!r} (must match ^[A-Za-z0-9_-]{{1,64}}$)",
            "InvalidName",
        )
    return None


def _mask_key(k: str | None) -> str:
    if not k:
        return ""
    if len(k) <= 8:
        return "***"
    return f"{k[:4]}...{k[-4:]}"


def _find_wiki(wiki_ref: str):
    found = registry_find(wiki_ref)
    if not found:
        return None, error(f"wiki not found: {wiki_ref!r}", "NameNotFound")
    return found, None


def cmd_alias_set(args):
    new_alias = args.alias
    if not new_alias or not NAME_RE.match(new_alias):
        return error(f"invalid alias: {new_alias!r}", "InvalidName")

    found, err = _find_wiki(args.wiki)
    if err:
        return err
    name, entry = found

    reg = load_registry()
    wikis = reg.setdefault("wikis", {})

    for en, e in wikis.items():
        if en == name:
            continue
        if en == new_alias or e.get("alias") == new_alias:
            return error(
                f"alias {new_alias!r} already used by wiki {en!r}",
                "AliasConflict",
                data={"attempted_alias": new_alias, "current_wiki": name, "conflicting_wiki": en},
            )

    previous = entry.get("alias")
    wikis[name]["alias"] = new_alias
    save_registry(reg)
    return success(
        {"name": name, "alias": new_alias, "previous_alias": previous},
        f"set alias of {name!r} to {new_alias!r}",
        hints=[f"now reachable as `xu-wiki --wiki {new_alias} ...`"],
    )


def cmd_alias_unset(args):
    found, err = _find_wiki(args.wiki)
    if err:
        return err
    name, entry = found
    previous = entry.get("alias")
    if previous is None:
        return warning({"name": name}, f"wiki {name!r} has no alias to unset")

    reg = load_registry()
    reg["wikis"][name]["alias"] = None
    save_registry(reg)
    return success(
        {"name": name, "previous_alias": previous},
        f"unset alias of {name!r}",
    )


def cmd_alias_show(args):
    found, err = _find_wiki(args.wiki)
    if err:
        return err
    name, entry = found
    return success(
        {
            "name": name,
            "alias": entry.get("alias"),
            "path": entry.get("path"),
            "created_at": entry.get("created_at"),
        },
        f"alias of {name!r}: {entry.get('alias')!r}",
    )


def cmd_register(args):
    name_err = _validate_name(args.name)
    if name_err:
        return name_err

    raw_path = Path(args.path).expanduser()
    if not raw_path.exists() or not raw_path.is_dir():
        return error(
            f"path does not exist or is not a dir: {raw_path}",
            "PathNotFound",
            data={"path": str(raw_path)},
        )

    target = raw_path.resolve(strict=False)

    reg = load_registry()
    wikis = reg.setdefault("wikis", {})

    if args.name in wikis:
        existing_path = Path(wikis[args.name]["path"]).resolve(strict=False)
        if existing_path == target:
            return warning(
                {"name": args.name, "path": str(target)},
                f"wiki {args.name!r} already registered at {target}; reusing "
                f"(register is idempotent, no files written)",
            )
        return error(
            f"name {args.name!r} already registered at {wikis[args.name]['path']}",
            "NameConflict",
            data={"existing_path": wikis[args.name]["path"]},
        )

    bound_alias = getattr(args, "alias", None)
    alias_msg = None
    if bound_alias:
        if not NAME_RE.match(args.alias):
            return error(f"invalid alias: {args.alias!r}", "InvalidName")
        for en, e in wikis.items():
            if en == args.alias or e.get("alias") == args.alias:
                alias_msg = (
                    f"alias {args.alias!r} conflicts (CONST-CRT-4); "
                    f"registered without alias"
                )
                bound_alias = None
                break

    wikis[args.name] = {
        "path": str(target),
        "alias": bound_alias,
        "created_at": now_ts(),
    }
    save_registry(reg)

    data = {
        "name": args.name,
        "path": str(target),
        "alias": bound_alias,
        "created_at": wikis[args.name]["created_at"],
    }
    if alias_msg:
        return warning(
            data,
            f"registered {args.name!r} at {target}; {alias_msg}",
            hints=["resolve the conflict and re-run to bind the alias"],
        )
    return success(
        data,
        f"registered {args.name!r} at {target} (no files written)",
        hints=["wiki files were not touched; only the global registry was updated"],
    )


def cmd_unregister(args):
    reg = load_registry()
    wikis = reg.get("wikis", {})
    found = None
    for n, e in wikis.items():
        if n == args.name or e.get("alias") == args.name:
            found = (n, e)
            break
    if not found:
        return error(f"wiki not found: {args.name!r}", "NameNotFound")
    name, entry = found

    removed_path = wikis.pop(name).get("path")
    save_registry(reg)
    return success(
        {"name": name, "removed_path": removed_path},
        f"unregistered {name!r}; wiki files at {removed_path!r} were NOT touched",
        hints=[
            "to delete wiki data: rm -rf <path>",
            "register again later with `xu-wiki register --name ... --path <path>`",
        ],
    )


def cmd_config_set_mineru_key(args):
    key = os.environ.get("MINERU_API_KEY")
    if not key:
        return error(
            "MINERU_API_KEY env var is empty; "
            "set it before running this command (safer than passing key on CLI)",
            "MissingKey",
            data={
                "hint": "export MINERU_API_KEY=...; xu-wiki config set_mineru_key",
            },
        )
    cfg = load_global_config()
    cfg.setdefault("mineru", {})["api_key"] = key
    save_global_config(cfg)
    return success(
        {"masked": _mask_key(key), "scope": "global"},
        "MinerU API key saved to global config",
        hints=[
            "test with: xu-wiki config show",
            "rotation: re-run with new MINERU_API_KEY env value",
        ],
    )


def cmd_config_show(args):
    cfg = load_global_config()
    reg = load_registry()
    safe = {
        "wikis_count": len(reg.get("wikis", {})),
        "mineru": {
            "api_key_set": bool(cfg.get("mineru", {}).get("api_key")),
            "api_key_masked": _mask_key(cfg.get("mineru", {}).get("api_key")),
        },
        "paths": {
            "global_dir": str(GLOBAL_DIR),
            "registry": str(GLOBAL_DIR / "config.yaml"),
            "global_config": str(GLOBAL_DIR / "config.yaml"),
        },
    }
    return success(safe, "global config (secrets masked)")


def cmd_config_path(args):
    return success(
        {
            "global_dir": str(GLOBAL_DIR),
            "registry": str(GLOBAL_DIR / "config.yaml"),
            "global_config": str(GLOBAL_DIR / "config.yaml"),
        },
        "global config locations",
    )
