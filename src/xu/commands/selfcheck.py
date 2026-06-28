"""`xu selfcheck` — post-install / runtime environment health check.

(坑 6 fix): After `pip install "xu-wiki[parse,nlp,vision]"`, there was
no agent-friendly command to verify the install is healthy. Agents had
to assemble checks manually:

    which xu, xu --version, xu skills path, ls ~/.xu-wiki/, pip show ...

`xu selfcheck` consolidates all of those into a single 4-key JSON
response, with per-check `ok: true/false` + actionable `hint` strings.

Checks performed:

 1. **cli_on_path** — is `xu` reachable on `$PATH`?
 2. **python_version** — is `sys.version_info` >= 3.10?
 3. **skill_bundle_readable** — can we resolve the 8 skill files?
  4. **global_dir_writable** — can we create `~/.xu-wiki/`?
 5. **global_config_chmod** — if mineru.api_key present, is mode 600?
  6. **optional_extras** — are `markitdown` / `Pillow>=12` installed?
 7. **ripgrep** — is `rg` on PATH (or fallback scanner is fine)?
 8. **agent_skill_deployment_hint** — print the bash template so the
    agent can self-deploy to ~/.hermes/skills/xu-wiki/

`status` is `success` only if every check passes; `warning` if any
non-critical check fails; `error` if any critical check fails.

Critical (causes `error`): cli_on_path, python_version,
skill_bundle_readable, global_dir_writable.
Non-critical (causes `warning`): the rest.
"""
from __future__ import annotations

import importlib
import os
import shutil
import sys
from pathlib import Path

from ..skills import ALL_SKILL_FILES, SKILL_NAME, SKILL_SRC_DIR
from ..utils import config as cfg_mod
from ..utils.response import error, success, warning


def _global_dir() -> Path:
    return Path(cfg_mod.GLOBAL_DIR)


def _global_config() -> Path:
    return Path(cfg_mod.GLOBAL_CONFIG)


CRITICAL = {"cli_on_path", "python_version", "skill_bundle_readable",
            "global_dir_writable"}


def _check_cli_on_path() -> dict:
    found = shutil.which("xu")
    if found:
        return {"ok": True, "path": found,
                "hint": f"`xu` resolves to {found}"}
    return {"ok": False,
            "hint": "`xu` not found on $PATH. If you used a venv, "
                    "either activate it (`source .venv/bin/activate`) or "
                    "use the absolute path (`.venv/bin/xu`)."}


def _check_python_version() -> dict:
    v = sys.version_info
    if (v.major, v.minor) >= (3, 10):
        return {"ok": True, "version": f"{v.major}.{v.minor}.{v.micro}",
                "executable": sys.executable,
                "hint": f"Python {v.major}.{v.minor}.{v.micro} OK"}
    return {"ok": False, "version": f"{v.major}.{v.minor}.{v.micro}",
            "hint": "Python >= 3.10 required (see README Requirements)."}


def _check_skill_bundle_readable() -> dict:
    src = Path(SKILL_SRC_DIR)
    if not src.is_dir():
        return {"ok": False,
                "hint": f"skill bundle dir missing: {src}. "
                        "Reinstall with `pip install --force-reinstall xu-wiki`."}
    missing = [f for f in ALL_SKILL_FILES if not (src / f).is_file()]
    if missing:
        return {"ok": False, "missing_files": missing,
                "hint": f"{len(missing)} skill file(s) missing under {src}. "
                        "Reinstall xu-wiki."}
    return {"ok": True, "source_dir": str(src), "file_count": len(ALL_SKILL_FILES),
            "skill_name": SKILL_NAME,
            "hint": f"all {len(ALL_SKILL_FILES)} skill files present"}


def _check_global_dir_writable() -> dict:
    gdir = _global_dir()
    try:
        gdir.mkdir(parents=True, exist_ok=True)
        probe = gdir / ".selfcheck_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return {"ok": True, "path": str(gdir),
                "hint": f"global dir writable at {gdir}"}
    except OSError as e:
        return {"ok": False, "error": str(e),
                "hint": f"cannot write to {gdir}. "
                        "Check XU_HOME / HOME permissions."}


def _check_global_config_chmod() -> dict:
    gcfg = _global_config()
    if not gcfg.exists():
        return {"ok": True, "note": "config not yet created; chmod enforced "
                                    "automatically when mineru.api_key is set",
                "hint": "no config yet — nothing to chmod"}
    mode = oct(gcfg.stat().st_mode & 0o777)
    cfg = cfg_mod.load_global_config()
    has_secret = bool(cfg.get("mineru", {}).get("api_key"))
    if has_secret and mode != "0o600":
        return {"ok": False, "mode": mode,
                "hint": f"config has mineru.api_key but mode is {mode} "
                        f"(expected 0o600). Run `chmod 600 {gcfg}`."}
    return {"ok": True, "mode": mode, "has_secret": has_secret,
            "hint": "config permissions OK"}


def _check_optional_extras() -> dict:
    # (name, import_name) — Pillow's import name is PIL, not Pillow.
    extras = (
        ("markitdown", "markitdown", "parse (DOCX/PPTX/PDF parsing)"),
        ("Pillow",     "PIL",        "vision (image EXIF for albums)"),
    )
    found = {}
    for pip_name, import_name, desc in extras:
        try:
            importlib.import_module(import_name)
            found[pip_name] = {"installed": True, "import_name": import_name,
                                "purpose": desc}
        except ImportError:
            found[pip_name] = {"installed": False, "import_name": import_name,
                                "purpose": desc,
                                "hint": f"`pip install xu-wiki[{pip_name.lower()}]` "
                                        f"to enable {desc}"}
    all_installed = all(v["installed"] for v in found.values())
    return {"ok": all_installed, "extras": found,
            "hint": "all optional extras installed" if all_installed
                    else "some optional extras missing — see per-extra hint"}


def _check_ripgrep() -> dict:
    rg = shutil.which("rg")
    if rg:
        return {"ok": True, "path": rg,
                "hint": "ripgrep installed; full-text scan speed OK"}
    return {"ok": True, "note": "rg not found on PATH; the CLI auto-falls-back "
                                "to a pure-Python scanner (slower on large wikis)",
            "hint": "install ripgrep for faster scans: `apt install ripgrep` / "
                    "`brew install ripgrep`"}


# Known agent skill discovery directories. The CLI does not know which
# agent the user is running, so it probes all four. Pass if SKILL.md
# exists at ANY of them; otherwise surface the full list so the agent
# can pick the right one for its platform.
#
# Override with env var `XU_AGENT_SKILL_DIR=/path/to/skill/dir` to
# restrict the check to a single location (e.g. non-standard installs).
KNOWN_AGENT_SKILL_DIRS = (
    ("hermes",   "~/.hermes/skills/xu-wiki"),
    ("trae",     "~/.trae/skills/xu-wiki"),
    ("claude",   "~/Library/Application Support/Claude/skills/xu-wiki"),
    ("cursor",   "~/.cursor/skills/xu-wiki"),
)


def _check_agent_skill_deployed() -> dict:
    """Is the skill bundle actually visible to the user's agent?

    Critical check (Bug 4 / review feedback): without this, `pip install`
    + `xu selfcheck` show green but the agent can't see the skill —
    exactly the "install complete ≠ usable" failure mode.

    Logic:
    - If `XU_AGENT_SKILL_DIR` env var is set, only that one location is
      checked (operator told us which agent to expect).
    - Otherwise probe all 4 known discovery dirs. Pass if SKILL.md
      exists in ANY of them.
    """
    env_override = os.environ.get("XU_AGENT_SKILL_DIR")
    if env_override:
        targets = [("custom", os.path.expanduser(env_override))]
    else:
        targets = [(name, os.path.expanduser(p))
                   for name, p in KNOWN_AGENT_SKILL_DIRS]

    found = []
    missing = []
    for name, path in targets:
        skill_md = Path(path) / "SKILL.md"
        if skill_md.is_file():
            found.append({"agent": name, "path": path})
        else:
            missing.append({"agent": name, "path": path})

    if found:
        return {
            "ok": True,
            "found": found,
            "missing": missing,
            "hint": f"skill deployed at: {[f['path'] for f in found]}",
        }
    return {
        "ok": False,
        "found": found,
        "missing": missing,
        "hint": (
            "skill bundle NOT deployed to any known agent discovery dir. "
            "Run the copy_template_bash in data.agent_deployment_hint "
            "(or set XU_AGENT_SKILL_DIR=<path> to specify a non-standard "
            "location). Probed: " + ", ".join(f"{m['agent']}={m['path']}" for m in missing)
        ),
    }


def _agent_deployment_hint() -> dict:
    """Return a bash template the agent can run to deploy the skill.

    Uses a for loop with per-file mkdir + cp so `reference/` subdir is
    preserved AND Python artifacts (__init__.py, __pycache__/) are excluded.
    """
    src = str(SKILL_SRC_DIR)
    lines = [
        f"SRC='{src}'",
        f"DEST=\"$HOME/.hermes/skills/{SKILL_NAME}\"",
        "mkdir -p \"$DEST\"",
        'for f in "$SRC"/*; do',
        '  base="$(basename "$f")"',
        '  # skip Python package artifacts',
        '  if [ "$base" = "__init__.py" ] || [ "$base" = "__pycache__" ]; then',
        '    continue',
        '  fi',
        '  if [ -d "$f" ]; then',
        '    mkdir -p "$DEST/$base"',
        '    for sf in "$f"/*; do',
        '      cp "$sf" "$DEST/$base/"',
        '    done',
        '  else',
        '    cp "$f" "$DEST/"',
        '  fi',
        'done',
        'ls "$DEST"            # verify top-level files',
        'ls "$DEST/reference"  # verify 2 reference files',
    ]
    return {
        "skill_name": SKILL_NAME,
        "source_dir": src,
        "copy_template_bash": "\n".join(lines),
        "hint": "run the copy_template_bash to deploy the skill to Hermes; "
                "substitute $HOME/.hermes/skills/ for your agent's discovery dir "
                "(see README §Agent compatibility matrix).",
    }


def cmd_selfcheck(_args) -> dict:
    checks = {
        "cli_on_path": _check_cli_on_path(),
        "python_version": _check_python_version(),
        "skill_bundle_readable": _check_skill_bundle_readable(),
        "agent_skill_deployed": _check_agent_skill_deployed(),
        "global_dir_writable": _check_global_dir_writable(),
        "global_config_chmod": _check_global_config_chmod(),
        "optional_extras": _check_optional_extras(),
        "ripgrep": _check_ripgrep(),
    }

    failed_critical = [k for k in CRITICAL if not checks[k]["ok"]]
    failed_noncritical = [k for k, v in checks.items()
                          if k not in CRITICAL and not v["ok"]]
    passed = [k for k, v in checks.items() if v["ok"]]

    # Build a high-signal "what's still left to do" list. The agent
    # uses this to avoid announcing "done" prematurely (case study
    # review feedback: agent saw green checks and stopped).
    next_actions: list[str] = []
    if not checks["cli_on_path"]["ok"]:
        next_actions.append(
            "activate the venv (`source .venv/bin/activate`) or use "
            "the absolute `xu` path. For pipx installs the binary is "
            "already at ~/.local/bin/xu — check `command -v xu`."
        )
    if not checks["skill_bundle_readable"]["ok"]:
        next_actions.append(
            "reinstall xu-wiki: `pip install --force-reinstall "
            "\"xu-wiki[parse,nlp,vision]\"` (or `pipx reinstall xu-wiki`)."
        )
    if not checks["agent_skill_deployed"]["ok"]:
        next_actions.append(
            "deploy the skill bundle to your agent: `xu deploy skill "
            "--target <hermes|trae|claude|cursor|auto>`"
        )
    if not checks["global_dir_writable"]["ok"]:
        next_actions.append(
            "fix XU_HOME / HOME permissions so ~/.xu-wiki/ is writable "
            "(see checks.global_dir_writable.hint)"
        )
    if failed_noncritical:
        for name in failed_noncritical:
            next_actions.append(
                f"optional: fix `{name}` — see checks.{name}.hint"
            )

    # Installer + smoke-test snapshot for the user.
    # Lazy import to avoid circular dependency: uninstall.py imports
    # from response.py (which is OK), selfcheck.py imports nothing
    # from uninstall — but if the import order ever flips, the
    # deferred call keeps things resilient.
    try:
        from .uninstall import _detect_installer
        installer = _detect_installer()
    except Exception:
        installer = "unknown"
    skill_deployed_to = [
        f["agent"] for f in checks["agent_skill_deployed"].get("found", [])
    ]

    deployment_status = {
        "installer": installer,                            # pipx | pip | unknown
        "binary_on_path": checks["cli_on_path"]["ok"],
        "skill_deployed_to": skill_deployed_to,            # e.g. ["hermes"]
        "smoke_test_run": False,                           # future: auto-run
        "wiki_data_present": False,                        # future: read registry
    }

    data = {
        "passed": passed,
        "failed_critical": failed_critical,
        "failed_noncritical": failed_noncritical,
        "checks": checks,
        "deployment_status": deployment_status,
        "next_actions": next_actions,
        "agent_deployment_hint": _agent_deployment_hint(),
    }

    if failed_critical:
        return error(
            f"{len(failed_critical)} critical check(s) failed; "
            "see data.checks for per-check hints",
            "SelfCheckFailed",
            data=data,
        )
    if failed_noncritical:
        return warning(
            data,
            f"{len(failed_noncritical)} non-critical check(s) failed; "
            "xu-wiki is usable but suboptimal",
        )
    return success(data, "all checks passed; xu-wiki ready to use")