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

import os
import shutil
import sys
from pathlib import Path

from ..skills import ALL_SKILL_FILES, SKILL_NAME, SKILL_SRC_DIR
from ..utils.response import error, success

# Reuse the same filter the `xu skills list` command uses, so the
# deploy output is provably the same set as what the agent sees in
# `xu skills list`.
from .skills import _filter_bundle_files


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
    target = getattr(args, "target", None) or "auto"
    try:
        target_name, desc, dest = _resolve_target(target)
    except ValueError as e:
        # `auto` with no agent detected vs an explicitly bad target name
        err_class = "NoAgentDetected" if target == "auto" else "UnknownTarget"
        return error(str(e), err_class)

    src = Path(SKILL_SRC_DIR)
    if not src.is_dir():
        return error(
            f"skill source dir not found: {src}", "BundleMissing",
            data={"source_dir": str(src)},
        )

    dest.mkdir(parents=True, exist_ok=True)

    clean_files = _filter_bundle_files(ALL_SKILL_FILES)
    copied = []
    failures = []
    for rel in clean_files:
        src_file = src / rel
        dst_file = dest / rel
        if not src_file.is_file():
            failures.append({"file": rel, "error": "source file missing"})
            continue
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src_file, dst_file)
            copied.append(rel)
        except Exception as e:
            failures.append({"file": rel, "error": str(e)})

    # Compute a verification hint: SKILL.md at dest + count
    skill_md_at_dest = (dest / "SKILL.md").is_file()
    return success(
        {
            "target": target_name,
            "target_description": desc,
            "source_dir": str(src),
            "destination": str(dest),
            "skill_md_at_dest": skill_md_at_dest,
            "files_copied": copied,
            "files_skipped": failures,
            "file_count": len(copied),
            "next_action": (
                "reload the agent's skill index / restart the agent so it "
                "picks up the new files at " + str(dest)
            ),
        },
        f"deployed {len(copied)} files to {dest} (target={target_name})",
    )