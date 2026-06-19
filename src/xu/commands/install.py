"""install / uninstall — software lifecycle (03-install.md / 04-uninstall.md).

install装能力不装数据 (PRIN-INST-1): sets up a project-local venv + CLI symlink,
deploys the packaged skill files (SKILL.md + 5 SOP task files per
design-docs/09-skill-architecture.md) into the Agent's discovery dir, and
writes the global config skeleton. The authoritative skill SOURCE lives
inside the package (`xu/skills/*.md`) so it ships with pip; install only
DEPLOYS a copy into the Agent's directory (PRIN-INST-3 — let the Agent own
its resource location). It NEVER touches any wiki instance data.

uninstall is the inverse function (PRIN-UNINST-3): default dry-run (PRIN-UNINST-6),
removes only what install wrote — including all deployed skill files — and
verifies no residue afterward (PRIN-UNINST-5). It NEVER deletes the knowledge
base (BAN-UNINST-1) nor the packaged skill source.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from ..skills import ALL_SKILL_FILES, SKILL_NAME, SKILL_SRC_DIR
from ..utils.config import GLOBAL_DIR, load_global_config, save_global_config
from ..utils.paths import now_ts
from ..utils.response import error, success, warning

PROJECT_ROOT = Path(__file__).resolve().parents[3]   # xu-wiki/
VENV_DIR = PROJECT_ROOT / ".venv"
BIN_DIR = GLOBAL_DIR / "bin"
CLI_LINK = BIN_DIR / "xu-wiki"
# Agent discovery dir: where the Agent looks for skills in this project.
SKILL_DEPLOY_DIR = PROJECT_ROOT / ".trae" / "skills" / SKILL_NAME
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
    # If pip fails, install must ABORT loudly — silently proceeding yields a
    # venv-without-package that downstream steps can silently mis-detect
    # (CONST-INST-3 / PRIN-INST-5). Also install [parse,nlp,vision] optional
    # groups so the CLI is functional out of the box on VPS.
    from xu import __version__
    venv_py = VENV_DIR / "bin" / "python"
    if venv_py.exists():
        try:
            subprocess.run(
                [str(venv_py), "-m", "pip", "install", "-q", "-e",
                 f"{PROJECT_ROOT}[parse,nlp,vision]"],
                check=True, capture_output=True, text=True,
            )
            actions.append(f"installed xu-wiki {__version__} into venv (editable, +parse,nlp,vision)")
        except subprocess.CalledProcessError as e:
            tail = (e.stderr or "").strip().splitlines()[-5:]
            return error(
                f"pip install failed: {' / '.join(tail) or e}",
                "PipInstallFailed",
                hints=[
                    "ensure network access; check pip can reach PyPI",
                    f"try manually: {venv_py} -m pip install -e '{PROJECT_ROOT}[parse,nlp,vision]'",
                    "on Debian/Ubuntu, ensure python3-venv is installed",
                ],
            )

    # 3. CLI symlink, not a copy (CONST-INST-2)
    venv_cli = VENV_DIR / "bin" / "xu-wiki"
    if venv_cli.exists():
        if CLI_LINK.is_symlink() or CLI_LINK.exists():
            CLI_LINK.unlink()
        CLI_LINK.symlink_to(venv_cli)
        actions.append(f"linked CLI: {CLI_LINK} -> {venv_cli}")

    # 4. Deploy the packaged skill files into the Agent's discovery dir
    # (PRIN-INST-3). The authoritative source ships inside the package
    # (xu/skills/*.md — SKILL.md + 5 SOP task files per PRIN-SKILL-1); we
    # copy them out so the Agent can index them. We do NOT hand-write skill
    # content here — the package source is the single source of truth, and
    # deploy is idempotent (PRIN-INST-4).
    missing_sources = [name for name in ALL_SKILL_FILES
                       if not (SKILL_SRC_DIR / name).exists()]
    if missing_sources:
        skill_status = "SOURCE-MISSING"
        actions.append(f"packaged skill source missing: {missing_sources}")
    else:
        SKILL_DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
        deployed = []
        for rel in ALL_SKILL_FILES:
            src = SKILL_SRC_DIR / rel
            dst = SKILL_DEPLOY_DIR / rel
            # ALL_SKILL_FILES contains paths like "reference/error-catalog.md";
            # ensure the parent subdir exists in the deploy dir.
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
            deployed.append(str(dst))
        skill_status = "deployed"
        actions.append(
            f"deployed {len(deployed)} skill files: "
            f"{SKILL_SRC_DIR} -> {SKILL_DEPLOY_DIR}"
        )

    # 5. global config skeleton — only non-wiki segments (BAN-CRT-2 inverse)
    cfg = load_global_config()
    cfg.setdefault("mineru", {"api_key": ""})   # key left empty; never hardcoded
    cfg.setdefault("installed_at", now_ts())
    save_global_config(cfg)
    actions.append("wrote global config skeleton (api keys left empty)")

    INSTALL_META.write_text(
        '{"version": "%s", "project_root": "%s", "venv": "%s", "cli_link": "%s", "installed_at": %d}\n'
        % (__version__, PROJECT_ROOT, VENV_DIR, CLI_LINK, now_ts()),
        encoding="utf-8",
    )

    data = {"actions": actions, "cli": str(CLI_LINK), "venv": str(VENV_DIR),
            "skill_source_dir": str(SKILL_SRC_DIR),
            "skill_deploy_dir": str(SKILL_DEPLOY_DIR),
            "skill_status": skill_status}
    hints = [
        f"add {BIN_DIR} to PATH",
        "next: xu-wiki create --name <name> --path <dir>",
    ]
    if skill_status != "deployed":
        hints.insert(0, f"WARNING: skill not deployed ({skill_status}); the Agent "
                       f"may not discover this skill — reinstall the package")
    return success(
        data,
        "xu-wiki installed (capabilities only; no wiki data touched)",
        hints=hints,
    )


def cmd_uninstall(args) -> dict:
    """Default dry-run (PRIN-UNINST-6). --execute to actually remove."""
    execute = getattr(args, "execute", False)

    plan = []  # reverse order of install (CONST-UNINST-3)
    # PRIN-UNINST-4: the deployed skill files in the Agent's dir ARE something
    # install wrote, so uninstall removes them (reverse of deploy). The
    # packaged skill SOURCE (xu/skills/*.md) is part of the software itself
    # and is NEVER touched here. Skill is deployed last → torn down first.
    for rel in ALL_SKILL_FILES:
        f = SKILL_DEPLOY_DIR / rel
        if f.exists():
            plan.append((f"remove deployed skill file: {rel}", f))
    if CLI_LINK.is_symlink() or CLI_LINK.exists():
        plan.append(("remove CLI symlink", CLI_LINK))
    if VENV_DIR.exists():
        plan.append(("remove project-local venv", VENV_DIR))
    if INSTALL_META.exists():
        plan.append(("remove install metadata", INSTALL_META))

    preserved = [
        "all wiki instances (raws/ nodes/ .xu/) — BAN-UNINST-1",
        "patches table & IDF table — BAN-UNINST-4",
        f"packaged skill source ({SKILL_SRC_DIR}) — part of the software, not a deploy artifact",
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
            hints=["xu-wiki uninstall --execute"],
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
