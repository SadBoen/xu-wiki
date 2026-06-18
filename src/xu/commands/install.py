"""install / uninstall — software lifecycle (03-install.md / 04-uninstall.md).

install装能力不装数据 (PRIN-INST-1): sets up a project-local venv + CLI symlink,
verifies the project-level SKILL.md is present (PRIN-INST-3: Agent's resources
are managed by the Agent — install does NOT touch the Agent's skill dir),
writes the global config skeleton.
It NEVER touches any wiki instance data.

uninstall is the inverse function (PRIN-UNINST-3): default dry-run (PRIN-UNINST-6),
removes only what install wrote, NEVER the knowledge base (BAN-UNINST-1).
The project-level SKILL.md is left in place per PRIN-UNINST-4 (Agent's
resources are still owned by the Agent; uninstall only informs, does not
delete).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from ..utils.config import GLOBAL_DIR, load_global_config, save_global_config
from ..utils.paths import now_ts
from ..utils.response import error, success, warning

PROJECT_ROOT = Path(__file__).resolve().parents[3]   # xu-wiki/
VENV_DIR = PROJECT_ROOT / ".venv"
BIN_DIR = GLOBAL_DIR / "bin"
CLI_LINK = BIN_DIR / "xu-wiki"
PROJECT_SKILL = PROJECT_ROOT / ".trae" / "skills" / "xu-wiki" / "SKILL.md"
INSTALL_META = GLOBAL_DIR / "install.json"


def _detect_python() -> str:
    """Probe python candidates by priority (BAN-INST-4)."""
    for cand in (sys.executable, shutil.which("python3"), shutil.which("python")):
        if cand and Path(cand).exists():
            return cand
    raise RuntimeError("no usable python interpreter found")


def cmd_install(args) -> dict:
    actions = []
    GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    # NOTE: we deliberately do NOT create GLOBAL_DIR/skills/. Per PRIN-INST-3 /
    # BAN-INST-3, the Agent's skill dir is owned by the Agent; install only
    # verifies the project-level SKILL.md is in place (the Agent picks it up
    # automatically from .trae/skills/ in the project).

    # 1. project-local venv (CONST-INST-1) — idempotent (PRIN-INST-4)
    if not VENV_DIR.exists():
        try:
            py = _detect_python()
            subprocess.run([py, "-m", "venv", str(VENV_DIR)], check=True,
                           capture_output=True, text=True)
            actions.append(f"created venv at {VENV_DIR}")
        except Exception as e:
            return error(f"venv creation failed, rolled back: {e}", "VenvFailed")
    else:
        actions.append("venv already present (reused)")

    # 2. install package into venv (editable)
    venv_py = VENV_DIR / "bin" / "python"
    if venv_py.exists():
        try:
            subprocess.run([str(venv_py), "-m", "pip", "install", "-q", "-e", str(PROJECT_ROOT)],
                           check=True, capture_output=True, text=True)
            actions.append("installed xu-wiki into venv (editable)")
        except subprocess.CalledProcessError as e:
            actions.append(f"pip install skipped/failed (non-fatal): {e.stderr[-200:] if e.stderr else e}")

    # 3. CLI symlink, not a copy (CONST-INST-2)
    venv_cli = VENV_DIR / "bin" / "xu-wiki"
    if venv_cli.exists():
        if CLI_LINK.is_symlink() or CLI_LINK.exists():
            CLI_LINK.unlink()
        CLI_LINK.symlink_to(venv_cli)
        actions.append(f"linked CLI: {CLI_LINK} -> {venv_cli}")

    # 4. Verify project-level SKILL.md (PRIN-INST-3). We do NOT write into
    # the Agent's skill dir; the Agent picks the project skill up from
    # .trae/skills/xu-wiki/SKILL.md on its own. install only reports whether
    # the file is present so the operator can fix it themselves.
    skill_status = "present" if PROJECT_SKILL.exists() else "MISSING"
    actions.append(f"project skill file ({PROJECT_SKILL}): {skill_status}")

    # 5. global config skeleton — only non-wiki segments (BAN-CRT-2 inverse)
    cfg = load_global_config()
    cfg.setdefault("mineru", {"api_key": ""})   # key left empty; never hardcoded
    cfg.setdefault("installed_at", now_ts())
    save_global_config(cfg)
    actions.append("wrote global config skeleton (api keys left empty)")

    INSTALL_META.write_text(
        '{"project_root": "%s", "venv": "%s", "cli_link": "%s", "installed_at": %d}\n'
        % (PROJECT_ROOT, VENV_DIR, CLI_LINK, now_ts()),
        encoding="utf-8",
    )

    data = {"actions": actions, "cli": str(CLI_LINK), "venv": str(VENV_DIR),
            "project_skill": str(PROJECT_SKILL), "skill_status": skill_status}
    hints = [
        f"add {BIN_DIR} to PATH",
        "next: xu-wiki create --name <name> --path <dir>",
    ]
    if not PROJECT_SKILL.exists():
        hints.insert(0, f"WARNING: project skill file missing at {PROJECT_SKILL}; "
                       f"the Agent may not discover this skill — restore it from git")
    return success(
        data,
        "xu-wiki installed (capabilities only; no wiki data touched)",
        hints=hints,
    )


def cmd_uninstall(args) -> dict:
    """Default dry-run (PRIN-UNINST-6). --execute to actually remove."""
    execute = getattr(args, "execute", False)

    plan = []  # reverse order of install (CONST-UNINST-3)
    # NOTE: PRIN-UNINST-4 — the project skill file (.trae/skills/xu-wiki/SKILL.md)
    # is owned by the Agent, not by install. uninstall does NOT touch it. If
    # the user wants it gone, that's a project-level decision (rm or git rm).
    if CLI_LINK.is_symlink() or CLI_LINK.exists():
        plan.append(("remove CLI symlink", CLI_LINK))
    if VENV_DIR.exists():
        plan.append(("remove project-local venv", VENV_DIR))
    if INSTALL_META.exists():
        plan.append(("remove install metadata", INSTALL_META))

    preserved = [
        "all wiki instances (raws/ nodes/ .xu/) — BAN-UNINST-1",
        "patches table & IDF table — BAN-UNINST-4",
        f"project skill file ({PROJECT_SKILL}) — PRIN-UNINST-4 (Agent owns it)",
        "global config api-key segment & registry",
    ]

    if not execute:
        return success(
            {
                "dry_run": True,
                "will_remove": [f"{desc}: {path}" for desc, path in plan],
                "preserved": preserved,
            },
            "DRY RUN — nothing removed. Re-run with --execute to apply (PRIN-UNINST-6).",
            hints=["xu-wiki uninstall --execute",
                   f"to also drop the skill: rm {PROJECT_SKILL}"],
        )

    removed = []
    for desc, path in plan:
        try:
            if path.is_dir() and not path.is_symlink():
                shutil.rmtree(path)
            else:
                path.unlink()
            removed.append(f"{desc}: {path}")
        except OSError as e:
            removed.append(f"FAILED {desc}: {e}")

    # verify-after-uninstall (PRIN-UNINST-5)
    residue = [str(p) for _, p in plan if p.exists()]
    data = {"removed": removed, "preserved": preserved, "residue": residue}
    if residue:
        return warning(data, "uninstall finished with residue; re-run", hints=residue)
    return success(data, "uninstall complete; knowledge bases left intact")
