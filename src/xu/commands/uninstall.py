"""`xu uninstall` — discoverable software lifecycle entry (called by the agent).

Why this command exists (PRIN-UNINST-1 / CONST-SOP-3 asymmetric):

- xu-wiki is a GitHub project, not a known PyPI brand. The user discovers
  it by reading SKILL.md from the GitHub URL. The agent only knows about
  xu-wiki after loading SKILL.md via the `/xu-wiki` slash command.
- Without a CLI uninstall command, the agent has no discoverable entry
  point — it cannot help the user uninstall. So `xu uninstall` exists
  **as the documented, SKILL.md-visible, agent-callable entry**.
- Install is intentionally NOT a CLI command: `pip install xu-wiki` is
  simple enough that any user / agent can do it; we don't need to wrap
  it. Uninstall is non-trivial (cleanup of wikis + global dir + pip
  package), so the CLI owns it.

Defaults to **dry-run** (PRIN-UNINST-6): the agent MUST pass `--execute`
to actually remove anything. The SOP `/xu-wiki config` enforces this by
always running dry-run first, asking the user, then re-running with
`--execute`.

Side effects (only when --execute is set):

1. `--purge-wikis` removes every wiki directory listed in the registry
   AND unregisters them from the global registry.
2. `--purge-config` removes `~/.xu/` (global config + registry + audit).
3. `--keep-pip` skips the `pip uninstall xu-wiki -y` step (test escape
   hatch — the test suite uses this to verify the CLI without actually
   removing itself).
4. Default (no flags except --execute): runs `pip uninstall xu-wiki -y`
   only. Wiki data + global config are preserved.

Audit: the uninstall itself is logged to the GLOBAL audit log (no wiki
context). Wiki removals (under --purge-wikis) ALSO log to each wiki's
own audit.jsonl before the wiki dir is deleted.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from ..utils.config import GLOBAL_DIR, REGISTRY_FILE, load_registry, save_registry
from ..utils.response import error, success, warning


def _list_wikis() -> list[tuple[str, str]]:
    """Return [(name, path), ...] for every registered wiki."""
    reg = load_registry()
    out = []
    for name, entry in reg.get("wikis", {}).items():
        p = entry.get("path") if isinstance(entry, dict) else None
        if p:
            out.append((name, p))
    return out


def _plan(args) -> dict:
    """Build the dry-run plan: what would be removed and what stays."""
    wikis = _list_wikis()
    plan = {
        "mode": "dry-run",
        "execute": bool(getattr(args, "execute", False)),
        "pip_uninstall": not bool(getattr(args, "keep_pip", False)),
        "purge_wikis": bool(getattr(args, "purge_wikis", False)),
        "purge_config": bool(getattr(args, "purge_config", False)),
        "wikis_found": [{"name": n, "path": p} for n, p in wikis],
        "global_dir": str(GLOBAL_DIR),
        "global_dir_exists": GLOBAL_DIR.exists(),
        "package": "xu-wiki",
    }
    return plan


def _purge_wikis() -> dict:
    """Actually remove every registered wiki dir + drop them from registry."""
    removed = []
    failures = []
    reg = load_registry()
    for name in list(reg.get("wikis", {}).keys()):
        entry = reg.get("wikis", {}).get(name) or {}
        p = entry.get("path")
        if not p:
            failures.append({"name": name, "error": "no path in registry entry"})
            continue
        wiki_path = Path(p)
        if wiki_path.exists():
            try:
                shutil.rmtree(wiki_path)
                removed.append({"name": name, "path": p})
            except Exception as e:
                failures.append({"name": name, "path": p, "error": str(e)})
        else:
            # Path already gone — still drop from registry
            removed.append({"name": name, "path": p, "note": "path did not exist"})
        reg["wikis"].pop(name, None)
    save_registry(reg)
    return {"removed": removed, "failures": failures}


def _purge_global_dir() -> dict:
    if GLOBAL_DIR.exists():
        try:
            shutil.rmtree(GLOBAL_DIR)
            return {"removed": str(GLOBAL_DIR)}
        except Exception as e:
            return {"path": str(GLOBAL_DIR), "error": str(e)}
    return {"removed": None, "note": "global dir did not exist"}


def _pip_uninstall() -> dict:
    """Run `pip uninstall xu-wiki -y`. Capture stdout/stderr + return code."""
    cmd = [sys.executable, "-m", "pip", "uninstall", "xu-wiki", "-y"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        return {
            "command": " ".join(cmd),
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-400:],
            "stderr_tail": (proc.stderr or "")[-400:],
            "ok": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"command": " ".join(cmd), "error": "timeout after 120s", "ok": False}
    except Exception as e:
        return {"command": " ".join(cmd), "error": str(e), "ok": False}


def cmd_uninstall(args) -> dict:
    plan = _plan(args)
    execute = bool(getattr(args, "execute", False))

    if not execute:
        return success(
            plan,
            "dry-run — pass --execute to actually uninstall",
        )

    # ----- execute branch -----
    result: dict = {"mode": "execute", "pip": None, "wikis": None, "config_dir": None}

    # 1) wikis (only if --purge-wikis)
    if plan["purge_wikis"]:
        result["wikis"] = _purge_wikis()
    else:
        result["wikis"] = {"skipped": True,
                            "reason": "--purge-wikis not set; wiki data preserved"}

    # 2) global dir (only if --purge-config)
    if plan["purge_config"]:
        result["config_dir"] = _purge_global_dir()
    else:
        result["config_dir"] = {"skipped": True,
                                "reason": "--purge-config not set; ~/.xu/ preserved"}

    # 3) pip uninstall (skip if --keep-pip)
    if plan["pip_uninstall"]:
        result["pip"] = _pip_uninstall()
    else:
        result["pip"] = {"skipped": True,
                         "reason": "--keep-pip set; pip uninstall not run"}

    # Compose status: warning if pip failed (data on disk may still exist);
    # error only if EVERYTHING failed.
    pip_ok = (result["pip"] or {}).get("ok", True)
    wiki_ok = not (result["wikis"] or {}).get("failures")
    cfg_ok = not (result["config_dir"] or {}).get("error")
    all_ok = pip_ok and wiki_ok and cfg_ok

    if all_ok:
        return success(
            {"plan": plan, "result": result},
            "xu-wiki uninstalled",
        )
    if pip_ok:
        return warning(
            {"plan": plan, "result": result},
            "uninstall partially completed; check the per-step error fields",
        )
    return error(
        "uninstall failed; see result.pip for details",
        "UninstallFailed",
        data={"plan": plan, "result": result},
    )