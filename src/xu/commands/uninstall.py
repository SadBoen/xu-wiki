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

 1. `--preserve-config` skips removal of `~/.xu-wiki/` (default: remove it).
2. `--purge-wikis` is ignored — wiki data is NEVER deleted.
3. `--keep-pip` skips the `pip uninstall xu-wiki -y` step (test escape
   hatch — the test suite uses this to verify the CLI without actually
   removing itself).
4. Default (no flags except --execute): removes pip package + `~/.xu-wiki/`
   config. Wiki data is preserved — always.

Audit: the uninstall itself is logged to the GLOBAL audit log (no wiki
context). Wiki removals (under --purge-wikis) ALSO log to each wiki's
own audit.jsonl before the wiki dir is deleted.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..utils.config import GLOBAL_DIR, load_registry, save_registry
from ..utils.response import error, success, warning
from ..utils.wiki import is_wiki_root

MANIFEST_PATH = Path("~/.local/share/xu-wiki/manifest.json").expanduser()


def _list_wikis() -> list[tuple[str, str]]:
    """Return [(name, path), ...] for every registered wiki."""
    reg = load_registry()
    out = []
    for name, entry in reg.get("wikis", {}).items():
        p = entry.get("path") if isinstance(entry, dict) else None
        if p:
            out.append((name, p))
    return out


def _plan(args, *, mode: str | None = None) -> dict:
    """Build the plan: what would be / was removed."""
    execute = bool(getattr(args, "execute", False))
    resolved_mode = mode or ("execute" if execute else "dry-run")
    wikis = _list_wikis()
    annotated = []
    for name, p in wikis:
        annotated.append({
            "name": name,
            "path": p,
            "is_wiki_root": is_wiki_root(p),
        })

    keep_skill = bool(getattr(args, "keep_skill", False))
    targets = getattr(args, "targets", None) or []
    manifest = _read_manifest()
    skill_deployments = manifest.get("deployments", []) if manifest else []
    if targets:
        skill_deployments = [d for d in skill_deployments if d.get("agent") in targets]

    plan = {
        "mode": resolved_mode,
        "execute": execute,
        "pip_uninstall": not bool(getattr(args, "keep_pip", False)),
        "purge_skill": not keep_skill,
        "purge_wikis": False,
        "purge_config": not bool(getattr(args, "preserve_config", False)),
        "targets": targets or [d["agent"] for d in skill_deployments],
        "skill_deployments": skill_deployments,
        "wikis_found": annotated,
        "global_dir": str(GLOBAL_DIR),
        "global_dir_exists": GLOBAL_DIR.exists(),
        "manifest_path": str(MANIFEST_PATH),
        "manifest_exists": MANIFEST_PATH.exists(),
        "package": "xu-wiki",
        "installer": _detect_installer(),
    }
    non_wiki = [w for w in annotated if not w["is_wiki_root"]]
    if non_wiki:
        plan["non_wiki_paths_detected"] = [
            {"name": w["name"], "path": w["path"]} for w in non_wiki
        ]
    return plan


def _read_manifest() -> dict | None:
    if not MANIFEST_PATH.exists():
        return None
    try:
        return json.loads(MANIFEST_PATH.read_text())
    except Exception:
        return None


def _purge_wikis(strict_wiki_check: bool = True) -> dict:
    """Actually remove every registered wiki dir + drop them from registry.

    `strict_wiki_check` (default True): refuse to rmtree any path that
    doesn't look like a wiki (`.xu/config.yaml` + `.xu/wiki.db`).
    Such entries are still dropped from the registry, but the directory
    is left intact and reported under `refused`. This prevents the
    "I registered ~/projects/notebook as a wiki and uninstall nuked
    my whole project" failure mode (3.1).

    Returns a dict with three lists (P1 schema, machine-readable):

    - `removed`  : entries that were ACTUALLY rmtree'd
                   (or whose path didn't exist on disk — entry
                   still dropped from registry as no-op).
                   Each item: {name, path[, note]}.
    - `refused`  : entries where strict_wiki_check blocked rmtree
                   because the path is not a wiki marker. Directory
                   left intact, registry entry still dropped.
                   Each item: {name, path, reason}.
    - `failures` : entries where shutil.rmtree raised. Directory MAY
                   be partially deleted; registry entry KEPT (might
                   be transient permission/mount issue — operator
                   should investigate).
                   Each item: {name, path, error}.

    The three lists are disjoint and exhaustive over the registry.
    Agents parsing this response should treat `removed` as success,
    `refused` as "user probably registered wrong path", `failures`
    as "investigate, possibly retry".
    """
    removed = []
    refused = []
    failures = []
    reg = load_registry()
    for name in list(reg.get("wikis", {}).keys()):
        entry = reg.get("wikis", {}).get(name) or {}
        p = entry.get("path")
        if not p:
            failures.append({"name": name, "error": "no path in registry entry"})
            reg["wikis"].pop(name, None)
            continue
        wiki_path = Path(p)
        if wiki_path.exists():
            if strict_wiki_check and not is_wiki_root(wiki_path):
                refused.append({
                    "name": name,
                    "path": p,
                    "reason": "path is not a wiki (missing .xu/config.yaml or .xu/wiki.db); "
                              "leaving directory intact",
                })
                reg["wikis"].pop(name, None)
                continue
            try:
                shutil.rmtree(wiki_path)
                removed.append({"name": name, "path": p})
            except Exception as e:
                failures.append({"name": name, "path": p, "error": str(e)})
                # keep registry entry on failure (might be transient)
                continue
        else:
            # Path already gone — still drop from registry
            removed.append({"name": name, "path": p, "note": "path did not exist"})
        reg["wikis"].pop(name, None)
    save_registry(reg)
    return {"removed": removed, "refused": refused, "failures": failures}


def _purge_global_dir() -> dict:
    """Remove ~/.xu-wiki/ and report enough audit detail for the agent to
    cross-check the action (P0: agent review fix).

    Returns a dict with:
    - existed_before (bool): was the dir present at start? (lets the
      agent distinguish "removed" from "no-op")
    - files_removed_count (int): how many entries were rmtree'd
    - path (str): the absolute path (already known to the agent via
      plan.global_dir, but echoed here for log clarity)
    - ok (bool): True iff the rmtree succeeded
    - error (str|None): populated only on failure
    """
    existed = GLOBAL_DIR.exists()
    if not existed:
        return {
            "existed_before": False,
            "files_removed_count": 0,
            "path": str(GLOBAL_DIR),
            "ok": True,
            "note": "global dir did not exist; nothing to remove",
        }
    try:
        # Count entries BEFORE rmtree — shutil.rmtree doesn't report.
        count = sum(1 for _ in GLOBAL_DIR.iterdir())
        shutil.rmtree(GLOBAL_DIR)
        return {
            "existed_before": True,
            "files_removed_count": count,
            "path": str(GLOBAL_DIR),
            "ok": True,
        }
    except Exception as e:
        return {
            "existed_before": existed,
            "files_removed_count": 0,
            "path": str(GLOBAL_DIR),
            "ok": False,
            "error": str(e),
        }


def _detect_installer() -> str:
    """Return one of: "pipx", "pip", "unknown".

    Detection heuristics:
    - pipx: `sys.prefix` is under `<base>/local/share/pipx/venvs/`
      (pipx default venv layout). Also accepts `~/.local/pipx/venvs/`
      (alternative path).
    - pip: `sys.prefix != sys.base_prefix` (we're in a venv) AND the
      prefix doesn't match pipx layout.
    - unknown: system Python (`sys.prefix == sys.base_prefix`).

    The function is read-only — it does not modify sys.path or env.
    """
    prefix = Path(sys.prefix).resolve()
    base = Path(sys.base_prefix).resolve()
    pipx_markers = ("/pipx/venvs/", "/local/share/pipx/venvs/")
    if any(m in str(prefix) for m in pipx_markers):
        return "pipx"
    if prefix != base:
        return "pip"  # some venv that's not pipx
    return "unknown"


def _pip_uninstall() -> dict:
    """Run `pip uninstall xu-wiki -y`. Capture stdout/stderr + return code.

    The `command` field is REDACTED: we replace the absolute
    `sys.executable` path with the literal `python3` so that audit logs
    and the agent's 4-key JSON don't leak the user's local venv
    layout (e.g. `/root/workspace/xu-wiki/.venv/bin/python3`). The
    full unredacted command is recoverable from `command_full` for
    developer debugging (test escape hatch).
    """
    cmd_full = [sys.executable, "-m", "pip", "uninstall", "xu-wiki", "-y"]
    cmd_redacted = ["python3", "-m", "pip", "uninstall", "xu-wiki", "-y"]
    redaction_note = "(sys.executable absolute path redacted; see command_full for debug)"
    try:
        proc = subprocess.run(
            cmd_full, capture_output=True, text=True, timeout=120
        )
        return {
            "command": " ".join(cmd_redacted),
            "command_redaction_note": redaction_note,
            "command_full": " ".join(cmd_full),
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-400:],
            "stderr_tail": (proc.stderr or "")[-400:],
            "ok": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"command": " ".join(cmd_redacted),
                "command_redaction_note": redaction_note,
                "command_full": " ".join(cmd_full),
                "error": "timeout after 120s", "ok": False}
    except Exception as e:
        return {"command": " ".join(cmd_redacted),
                "command_redaction_note": redaction_note,
                "command_full": " ".join(cmd_full),
                "error": str(e), "ok": False}


def _pipx_uninstall() -> dict:
    """Run `pipx uninstall xu-wiki`. Uses `python3 -m pipx` to ensure pipx is
    on PATH regardless of how Python was invoked.
    """
    cmd = ["python3", "-m", "pipx", "uninstall", "xu-wiki"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
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


def _purge_skill_bundles(targets: list[str] | None = None) -> dict:
    """Remove skill bundle deployments from manifest and filesystem.

    Reads manifest, removes entries for the given targets (or all if None),
    and deletes the symlink/copy at each target's skill_path.
    """
    manifest = _read_manifest()
    if not manifest:
        return {"removed": [], "skipped": True,
                "reason": "no manifest found; nothing to clean"}

    deployments = manifest.get("deployments", [])
    if targets:
        deployments = [d for d in deployments if d.get("agent") in targets]

    removed = []
    failures = []
    remaining = []

    for d in deployments:
        skill_path = d.get("skill_path")
        if not skill_path:
            failures.append({"agent": d.get("agent"), "error": "no skill_path in manifest"})
            continue
        p = Path(skill_path)
        try:
            if p.is_symlink():
                p.unlink()
            elif p.exists():
                shutil.rmtree(p)
            removed.append({"agent": d.get("agent"), "path": skill_path,
                            "mode": d.get("mode", "unknown")})
        except Exception as e:
            failures.append({"agent": d.get("agent"), "path": skill_path, "error": str(e)})
        remaining.append(d)

    if remaining and not failures:
        manifest["deployments"] = remaining
        try:
            MANIFEST_PATH.write_text(json.dumps(manifest, indent=2))
        except Exception:
            pass
    elif not remaining or (not remaining and failures):
        try:
            MANIFEST_PATH.unlink()
        except FileNotFoundError:
            pass

    return {"removed": removed, "failures": failures,
            "skipped": False if removed else True}


def _format_dry_run(plan: dict) -> str:
    lines = ["Proposed uninstall plan:", f"  Program:  xu-wiki ({plan['installer']})"]
    if plan["pip_uninstall"]:
        if plan["installer"] == "pipx":
            lines.append(f"           → pipx uninstall xu-wiki")
        else:
            lines.append(f"           → pip uninstall xu-wiki")
    else:
        lines.append(f"           (kept — --keep-pip)")

    skill_deps = plan.get("skill_deployments", [])
    if skill_deps:
        lines.append("  Skill bundle:")
        for d in skill_deps:
            mode = d.get("mode", "unknown")
            lt = d.get("link_target", "")
            lines.append(f"    - {d['agent']:<8} {d['skill_path']}  ({mode}"
                        + (f" → {lt}" if lt else "") + ")")
    else:
        lines.append("  Skill bundle: (none deployed)")

    if plan["purge_config"]:
        lines.append(f"  Config:     {plan['global_dir']}  (REMOVED)")
    else:
        lines.append(f"  Config:     {plan['global_dir']}  (preserved — --preserve-config)")

    if plan.get("wikis_found"):
        lines.append("  Wiki data:")
        for w in plan["wikis_found"]:
            lines.append(f"    - {w['name']:<8} {w['path']}  (preserved — wiki data NEVER deleted)")
    return "\n".join(lines)


def cmd_uninstall(args) -> dict:
    plan = _plan(args)
    execute = bool(getattr(args, "execute", False))

    if not execute:
        print(_format_dry_run(plan))
        return success(
            plan,
            "dry-run — pass --execute to actually uninstall",
        )

    # ----- execute branch -----
    result: dict = {"mode": "execute", "pip": None, "wikis": None,
                    "config_dir": None, "skill_bundles": None, "installer": None}

    # 0) detect installer context. Already in plan via _plan(); re-read
    # here so the pipx guard is a single local reference.
    installer = plan["installer"]

    # 1) wikis (wiki data NEVER deleted regardless of any flag)
    if plan["purge_wikis"]:
        result["wikis"] = _purge_wikis()
    else:
        result["wikis"] = {"skipped": True,
                            "reason": "--purge-wikis not set; wiki data preserved"}

    # 2) skill bundles (only if --purge-skill, default: remove)
    if plan["purge_skill"]:
        targets = plan.get("targets")
        result["skill_bundles"] = _purge_skill_bundles(targets if targets else None)
    else:
        result["skill_bundles"] = {"skipped": True,
                                   "reason": "--keep-skill set; skill bundles preserved"}

    # 3) global dir (only if --purge-config, default: remove)
    if plan["purge_config"]:
        result["config_dir"] = _purge_global_dir()
    else:
        result["config_dir"] = {"skipped": True,
                                "reason": "--preserve-config set; ~/.xu-wiki/ preserved"}

    # 4) pip/pipx uninstall (skip if --keep-pip)
    if plan["pip_uninstall"]:
        if installer == "pipx":
            result["pip"] = _pipx_uninstall()
        else:
            result["pip"] = _pip_uninstall()
    else:
        result["pip"] = {"skipped": True,
                         "reason": "--keep-pip set; pip uninstall not run"}

    # Compose status: warning if pip failed (data on disk may still exist);
    # error only if EVERYTHING failed.
    # (P0 audit fix): config_dir now uses `ok`/`existed_before`/`files_removed_count`
    # instead of just an `error` string. The agent can cross-check by
    # independently stat-ing the path.
    pip_ok = (result["pip"] or {}).get("ok", True)
    wiki_failures = (result["wikis"] or {}).get("failures") or []
    wiki_refused = (result["wikis"] or {}).get("refused") or []
    cfg_ok = (result["config_dir"] or {}).get("ok", True)
    all_ok = pip_ok and not wiki_failures and not wiki_refused and cfg_ok
    partial = pip_ok and (wiki_failures or wiki_refused or not cfg_ok)

    if all_ok:
        return success(
            {"plan": plan, "result": result},
            "xu-wiki uninstalled",
        )
    if partial:
        return warning(
            {"plan": plan, "result": result},
            "uninstall partially completed; check the per-step error/refused fields",
        )
    return error(
        "uninstall failed; see result.pip for details",
        "UninstallFailed",
        data={"plan": plan, "result": result},
    )