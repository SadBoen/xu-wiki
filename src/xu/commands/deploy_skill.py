"""`xu deploy skill --target <agent>` — copy the skill bundle to the
agent's discovery directory in one step.

Why this command exists:

The CLI ships 8 markdown files (SKILL.md + 5 SOPs + 2 reference)
as `package_data` under `<site-packages>/xu/skills/`.
The CLI does NOT deploy them to any agent — that's an agent concern
because only the agent knows its own discovery directory layout.

The README previously told agents to do this with a hand-rolled
`cp -r` command. That had three real failure modes:

1. `cp -r SRC/. DEST/` flattens the `reference/` subdirectory
   because the per-file list `cp SRC/... DEST/` doesn't preserve
   relative paths.
2. The skills source dir is a regular Python package, so a naive
   `cp -r` copies `__init__.py` and `__pycache__/` into the agent's
   discovery dir — pure noise that may confuse the agent's skill
   parser.
3. The agent has to know which discovery dir maps to which agent
   platform (Hermes / Trae / Claude Desktop / Cursor / …).

`xu deploy skill` closes all three: it uses the curated
`ALL_SKILL_FILES` list (Python artifacts filtered at the skills.py
layer), copies each file to `$DEST/<relative-path>` preserving the
`reference/` subdir, and provides built-in target → discovery-dir
mappings.

Targets:

- `hermes`  → `~/.hermes/skills/xu-wiki/`
- `trae`    → `<cwd>/.trae/skills/xu-wiki/`  (project-local)
- `claude`  → `~/Library/Application Support/Claude/skills/xu-wiki/`
              (macOS only; error elsewhere)
- `cursor`  → `<cwd>/.cursor/skills/xu-wiki/`  (project-local)
- `auto`    → probe all four; deploy to the FIRST one whose parent
              exists (means the agent is already installed there).

The command is always explicit — no default. The agent must declare
which target it serves.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..skills import ALL_SKILL_FILES, SKILL_NAME, SKILL_SRC_DIR
from ..utils.response import error, success
from .skills import _filter_bundle_files


@dataclass
class Deployment:
    agent: str
    skill_path: str
    mode: str = "copy"
    link_target: str | None = None
    installed_at: str = ""


@dataclass
class Manifest:
    version: str = "0.1.0"
    deployments: list[Deployment] = field(default_factory=list)
    pip_installer: str = "unknown"
    pip_package: str = "xu-wiki"

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Manifest":
        deployments = []
        for d in data.get("deployments", []):
            if isinstance(d, dict):
                deployments.append(Deployment(
                    agent=str(d.get("agent", "")),
                    skill_path=str(d.get("skill_path", "")),
                    mode=str(d.get("mode", "copy")),
                    link_target=d.get("link_target"),
                    installed_at=str(d.get("installed_at", "")),
                ))
        return cls(
            version=str(data.get("version", "0.1.0")),
            deployments=deployments,
            pip_installer=str(data.get("pip_installer", "unknown")),
            pip_package=str(data.get("pip_package", "xu-wiki")),
        )


def _read_manifest() -> Manifest | None:
    """Read and validate manifest.json. Returns None if absent or corrupt."""
    if not MANIFEST_PATH.exists():
        return None
    try:
        data = json.loads(MANIFEST_PATH.read_text())
        return Manifest.from_json(data)
    except Exception:
        return None

CANONICAL_SKILLS = Path("~/.local/share/xu-wiki/skills").expanduser()
MANIFEST_PATH = Path("~/.local/share/xu-wiki/manifest.json").expanduser()


# Target → (description, path template, project_local_bool)
# `path_template` uses `~` and `{cwd}`; expanded at call time.
TARGETS: dict[str, tuple[str, str, bool]] = {
    "hermes": ("Hermes (cross-platform)",
               "~/.hermes/skills/{name}", False),
    "trae":   ("Trae IDE (project-local)",
               "{cwd}/.trae/skills/{name}", True),
    "claude": ("Claude Desktop (macOS only)",
               "~/Library/Application Support/Claude/skills/{name}", False),
    "cursor": ("Cursor (project-local)",
               "{cwd}/.cursor/skills/{name}", True),
}


def _resolve_target(target: str, *, cwd: str | None = None) -> tuple[str, str, Path]:
    """Return (name, description, expanded_dest_path) for the target.

    `auto` is resolved by probing which target's PARENT dir already
    exists — that means the agent is installed there. The first match
    wins. If no known agent is detected, `auto` raises ValueError
    (explicit over implicit) so the user must pass --target explicitly
    rather than silently deploying to an agent they may not use.

    `cwd` (test hook): overrides the current working directory used in
    {cwd} placeholders for project-local targets (trae, cursor). At
    runtime this is None → os.getcwd() is used.
    """
    if cwd is None:
        cwd = os.getcwd()

    if target == "auto":
        for tname, (_desc, tpl, _pl) in TARGETS.items():
            expanded = Path(os.path.expanduser(tpl.format(name=SKILL_NAME, cwd=cwd)))
            parent = expanded.parent
            if parent.exists():
                return tname, TARGETS[tname][0], expanded
        # No known agent detected — do NOT silently deploy to hermes.
        raise ValueError(
            "no known agent detected (probed: "
            + ", ".join(TARGETS.keys())
            + "); pass --target explicitly, e.g. `--target hermes`. "
            "For an agent not in this list, see README §Agent skill deployment."
        )

    if target not in TARGETS:
        raise ValueError(f"unknown target: {target!r}; "
                         f"choose from {sorted(list(TARGETS.keys()) + ['auto'])}")

    desc, tpl, _pl = TARGETS[target]
    expanded = Path(os.path.expanduser(tpl.format(name=SKILL_NAME, cwd=cwd)))
    return target, desc, expanded


def cmd_deploy_skill(args) -> dict:
    targets = getattr(args, "target", None)
    if not targets:
        targets = ["auto"]
    elif isinstance(targets, str):
        targets = [targets]
    use_copy = bool(getattr(args, "copy", False))

    src = Path(SKILL_SRC_DIR)
    if not src.is_dir():
        return error(
            f"skill source dir not found: {src}", "BundleMissing",
            data={"source_dir": str(src)},
        )

    results = []
    for target in targets:
        r = _deploy_one(target, use_copy, src)
        results.append(r)

    failures = [r for r in results if r["status"] == "error"]
    successes = [r for r in results if r["status"] == "success"]
    if not successes:
        return error(f"all {len(targets)} target(s) failed", "DeployFailed",
                     data={"results": results, "total": len(targets),
                           "succeeded": len(successes), "failed": len(failures)})
    msg_parts = [f"{len(successes)}/{len(targets)} target(s) deployed"]
    if failures:
        msg_parts.append(f"{len(failures)} failed: {[r['target'] for r in failures]}")
    return success(
        {"results": results, "total": len(targets),
         "succeeded": len(successes), "failed": len(failures)},
        "; ".join(msg_parts),
    )


def _deploy_one(target: str, use_copy: bool, src: Path) -> dict:
    try:
        target_name, desc, dest = _resolve_target(target)
    except ValueError as e:
        err_class = "NoAgentDetected" if target == "auto" else "UnknownTarget"
        return {"status": "error", "target": target, "error": str(e), "err_class": err_class}

    mode = "copy" if use_copy else "symlink"
    deployed = []
    failures = []

    if use_copy:
        dest.mkdir(parents=True, exist_ok=True)
        clean_files = _filter_bundle_files(ALL_SKILL_FILES)
        for rel in clean_files:
            src_file = src / rel
            dst_file = dest / rel
            if not src_file.is_file():
                failures.append({"file": rel, "error": "source file missing"})
                continue
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src_file, dst_file)
                deployed.append(rel)
            except Exception as e:
                failures.append({"file": rel, "error": str(e)})
        link_target = None
    else:
        CANONICAL_SKILLS.mkdir(parents=True, exist_ok=True)
        clean_files = _filter_bundle_files(ALL_SKILL_FILES)
        for rel in clean_files:
            src_file = src / rel
            dst_file = CANONICAL_SKILLS / rel
            if not src_file.is_file():
                failures.append({"file": rel, "error": "source file missing"})
                continue
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            try:
                if dst_file.is_symlink() or dst_file.exists():
                    dst_file.unlink()
                shutil.copy2(src_file, dst_file)
                deployed.append(rel)
            except Exception as e:
                failures.append({"file": rel, "error": str(e)})
        link_target = str(CANONICAL_SKILLS)
        if dest.is_symlink() or dest.exists():
            try:
                dest.unlink()
            except OSError:
                pass
        try:
            dest.symlink_to(CANONICAL_SKILLS, target_is_directory=True)
        except OSError:
            dest.mkdir(parents=True, exist_ok=True)
            for rel in clean_files:
                src_file = src / rel
                dst_file = dest / rel
                if not src_file.is_file():
                    continue
                dst_file.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copy2(src_file, dst_file)
                except Exception:
                    pass
            link_target = None
            mode = "copy"

    _write_manifest(target_name, dest, mode, link_target)
    skill_md_at_dest = (dest / "SKILL.md").is_file()
    return {
        "status": "success",
        "target": target_name,
        "target_description": desc,
        "destination": str(dest),
        "mode": mode,
        "link_target": link_target,
        "file_count": len(deployed),
        "files_deployed": deployed,
        "files_skipped": failures,
        "skill_md_at_dest": skill_md_at_dest,
    }


def _write_manifest(target: str, dest: Path, mode: str, link_target: str | None) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest = _read_manifest() or Manifest()
    manifest.pip_installer = _detect_installer_for_manifest()

    manifest.deployments = [d for d in manifest.deployments if d.agent != target]
    manifest.deployments.append(Deployment(
        agent=target,
        skill_path=str(dest),
        mode=mode,
        link_target=link_target,
        installed_at=datetime.now(timezone.utc).isoformat(),
    ))

    data = {
        "version": manifest.version,
        "deployments": [
            {
                "agent": d.agent,
                "skill_path": d.skill_path,
                "mode": d.mode,
                "link_target": d.link_target,
                "installed_at": d.installed_at,
            }
            for d in manifest.deployments
        ],
        "pip_installer": manifest.pip_installer,
        "pip_package": manifest.pip_package,
    }
    MANIFEST_PATH.write_text(json.dumps(data, indent=2))


def _detect_installer_for_manifest() -> str:
    prefix = Path(sys.prefix).resolve()
    base = Path(sys.base_prefix).resolve()
    pipx_markers = ("/pipx/venvs/", "/local/share/pipx/venvs/")
    if any(m in str(prefix) for m in pipx_markers):
        return "pipx"
    if prefix != base:
        return "pip"
    return "unknown"