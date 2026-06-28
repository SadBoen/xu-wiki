"""`xu update` — upgrade xu-wiki program body and re-deploy skill bundles.

Update = pip upgrade + skill re-deploy. No wiki data is touched (BAN-UNINST-1).

--check mode: fetch latest version from PyPI and compare with installed version.
  Returns {status, data: {current, latest, update_available}, message}.
  Works for both PyPI-installed and git-installed packages.

Default mode (no --check): upgrade the pip package in-place, then re-deploy
  skill bundles to every target recorded in the manifest.

Flags:
  --check       Only check for updates; do not install anything.
  --no-redeploy Skip skill re-deploy step (only upgrade the pip package).
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from .. import __version__
from ..utils.response import error, success, warning

MANIFEST_PATH = Path("~/.local/share/xu-wiki/manifest.json").expanduser()


def _read_manifest() -> dict | None:
    if not MANIFEST_PATH.exists():
        return None
    try:
        return json.loads(MANIFEST_PATH.read_text())
    except Exception:
        return None


def _detect_installer() -> str:
    prefix = Path(sys.prefix).resolve()
    base = Path(sys.base_prefix).resolve()
    pipx_markers = ("/pipx/venvs/", "/local/share/pipx/venvs/")
    if any(m in str(prefix) for m in pipx_markers):
        return "pipx"
    if prefix != base:
        return "pip"
    return "unknown"


def _pipx_upgrade() -> dict:
    cmd = ["python3", "-m", "pipx", "upgrade", "xu-wiki"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        return {
            "command": " ".join(cmd),
            "returncode": proc.returncode,
            "stdout_tail": (proc.stdout or "")[-500:],
            "stderr_tail": (proc.stderr or "")[-500:],
            "ok": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"command": " ".join(cmd), "error": "timeout after 180s", "ok": False}
    except Exception as e:
        return {"command": " ".join(cmd), "error": str(e), "ok": False}


def _pip_upgrade(extra_index: str | None = None) -> dict:
    cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "xu-wiki"]
    if extra_index:
        cmd.extend(["--extra-index-url", extra_index])
    if not sys.stdout.isatty():
        cmd.append("--quiet")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        stdout_tail = (proc.stdout or "")[-500:]
        stderr_tail = (proc.stderr or "")[-500:]
        return {
            "command": " ".join(cmd),
            "returncode": proc.returncode,
            "stdout_tail": stdout_tail,
            "stderr_tail": stderr_tail,
            "ok": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"command": " ".join(cmd), "error": "timeout after 180s", "ok": False}
    except Exception as e:
        return {"command": " ".join(cmd), "error": str(e), "ok": False}


def _fetch_pypi_version() -> str | None:
    try:
        import urllib.request
        url = "https://pypi.org/pypi/xu-wiki/json"
        with urllib.request.urlopen(url, timeout=10) as r:
            data = json.loads(r.read())
        return data.get("info", {}).get("version")
    except Exception:
        return None


def _check_update() -> dict:
    current = __version__
    latest = _fetch_pypi_version()
    if latest is None:
        return {
            "current": current,
            "latest": None,
            "update_available": None,
            "note": "could not fetch latest version from PyPI",
        }
    update_available = latest != current
    return {
        "current": current,
        "latest": latest,
        "update_available": update_available,
    }


def _redeploy_skills(targets: list[str]) -> dict:
    results = []
    for target in targets:
        r = _redeploy_one(target)
        results.append(r)
    failures = [r for r in results if r.get("status") == "error"]
    successes = [r for r in results if r.get("status") == "success"]
    return {
        "total": len(targets),
        "succeeded": len(successes),
        "failed": len(failures),
        "results": results,
    }


def _redeploy_one(target: str) -> dict:
    from .deploy_skill import _resolve_target, _filter_bundle_files, _write_manifest
    from ..skills import ALL_SKILL_FILES, SKILL_NAME, SKILL_SRC_DIR

    try:
        target_name, desc, dest = _resolve_target(target)
    except ValueError as e:
        return {"status": "error", "target": target, "error": str(e)}

    src = Path(SKILL_SRC_DIR)
    if not src.is_dir():
        return {"status": "error", "target": target_name, "error": f"skill src dir not found: {src}"}

    deployed = []
    failures = []
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

    _write_manifest(target_name, dest, "copy", None)
    return {
        "status": "success" if not failures else "partial",
        "target": target_name,
        "destination": str(dest),
        "file_count": len(deployed),
        "files_deployed": deployed,
        "files_failed": failures,
    }


def cmd_update(args) -> dict:
    check_only = bool(getattr(args, "check", False))
    redeploy = not bool(getattr(args, "no_redeploy", False))

    # --check: only version report, no side effects
    if check_only:
        info = _check_update()
        if info["update_available"] is None:
            return warning(
                info,
                f"could not determine latest version (PyPI unreachable); "
                f"installed: {info['current']}",
            )
        if info["update_available"]:
            return success(
                info,
                f"update available: {info['current']} → {info['latest']}",
            )
        return success(info, f"up to date (v{info['current']})")

    # --- execute update ---
    installer = _detect_installer()

    # 1) pip upgrade
    if installer == "pipx":
        pip_result = _pipx_upgrade()
    else:
        pip_result = _pip_upgrade()

    # 2) skill re-deploy
    redeploy_result = None
    if redeploy:
        manifest = _read_manifest()
        if manifest:
            targets = [d["agent"] for d in manifest.get("deployments", [])]
            if targets:
                redeploy_result = _redeploy_skills(targets)

    # 3) emit result
    all_ok = pip_result.get("ok", False)
    if all_ok:
        parts = [f"upgraded (v{__version__})"]
        if redeploy_result:
            parts.append(
                f"skills re-deployed ({redeploy_result['succeeded']}/{redeploy_result['total']} targets)"
            )
        return success(
            {"pip": pip_result, "redeploy": redeploy_result},
            "; ".join(parts),
        )
    return error(
        f"pip upgrade failed (returncode={pip_result.get('returncode')}); "
        f"see result.pip for details",
        "UpgradeFailed",
        data={"pip": pip_result, "redeploy": redeploy_result},
    )
