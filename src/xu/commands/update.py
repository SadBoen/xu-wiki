"""`xu update` — upgrade xu-wiki program body and re-deploy skill bundles.

Update = install from GitHub main + skill re-deploy. No wiki data is touched (BAN-UNINST-1).

--check mode: fetch latest commit SHA from GitHub main and compare with installed version.
  Returns {status, data: {current, latest, update_available}, message}.

Default mode (no --check): upgrade from GitHub main, then re-deploy skill bundles.

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

from .deploy_skill import _read_manifest

GITHUB_REPO = "SadBoen/xu-wiki"
GIT_INSTALL_URL = f"git+https://github.com/{GITHUB_REPO}.git@main"


def _is_installed() -> bool:
    try:
        import importlib.util
        spec = importlib.util.find_spec("xu")
        return spec is not None
    except Exception:
        return False


def _detect_installer() -> str:
    prefix = Path(sys.prefix).resolve()
    base = Path(sys.base_prefix).resolve()
    pipx_markers = ("/pipx/venvs/", "/local/share/pipx/venvs/")
    if any(m in str(prefix) for m in pipx_markers):
        return "pipx"
    if prefix != base:
        return "pip"
    return "unknown"


def _current_commit() -> str | None:
    try:
        import re
        spec_file = None
        for p in (Path(sys.prefix) / "xu_wiki-*.dist-info" / "direct_url.json").parent.glob("xu_wiki-*.dist-info"):
            spec_file = p / "direct_url.json"
            break
        if spec_file is None:
            for p in (Path(sys.prefix) / "xu-wiki-*.dist-info" / "direct_url.json").parent.glob("xu-wiki-*.dist-info"):
                spec_file = p / "direct_url.json"
                break
        if spec_file and spec_file.exists():
            d = json.loads(spec_file.read_text())
            url = d.get("url", "")
            m = re.search(r"[a-f0-9]{40}", url)
            if m:
                return m.group(0)[:12]
    except Exception:
        pass
    return None


def _pipx_upgrade() -> dict:
    pipx_python = Path(sys.prefix) / "bin" / "python3"
    if not pipx_python.exists():
        pipx_python = Path(sys.prefix) / "bin" / "python"
    cmd = [
        str(pipx_python), "-m", "pip", "install", "--upgrade", "--no-cache-dir", "--no-deps",
        f"git+https://github.com/{GITHUB_REPO}.git@main",
    ]
    if not sys.stdout.isatty():
        cmd.append("--quiet")
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


def _pip_upgrade() -> dict:
    cmd = [
        sys.executable, "-m", "pip", "install", "--upgrade", "--no-cache-dir", "--no-deps",
        f"git+https://github.com/{GITHUB_REPO}.git@main",
    ]
    if not sys.stdout.isatty():
        cmd.append("--quiet")
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


def _fetch_github_version() -> tuple[str | None, str | None]:
    try:
        import urllib.request
        url = f"https://api.github.com/repos/{GITHUB_REPO}/commits/main"
        req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        sha = data.get("sha", "")[:12]
        date = data.get("commit", {}).get("committer", {}).get("date", "")
        return sha, date
    except Exception:
        return None, None


def _check_update() -> dict:
    current = _current_commit() or __version__
    latest, latest_date = _fetch_github_version()
    if latest is None:
        return {
            "current": current,
            "latest": None,
            "update_available": None,
            "note": "could not fetch latest commit from GitHub",
        }
    update_available = latest != current
    return {
        "current": current,
        "latest": latest,
        "latest_date": latest_date,
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
    from ..skills import ALL_SKILL_FILES, SKILL_SRC_DIR

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
    first_install = not _is_installed()

    # --check: only version report, no side effects
    if check_only:
        info = _check_update()
        if info["update_available"] is None:
            note = " (first install — will fetch from GitHub)" if first_install else ""
            return warning(
                info,
                f"could not determine latest commit (GitHub unreachable); "
                f"installed: {info['current']}{note}",
            )
        if info["update_available"]:
            return success(
                info,
                f"update available: {info['current']} → {info['latest']}",
            )
        return success(info, f"up to date ({info['current']})")

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
            targets = [d.agent for d in manifest.deployments]
            if targets:
                redeploy_result = _redeploy_skills(targets)

    # 3) emit result
    all_ok = pip_result.get("ok", False)
    installed = _current_commit() or __version__
    result_data: dict = {"pip": pip_result, "redeploy": redeploy_result}
    if first_install:
        result_data["first_install"] = True
    if all_ok:
        parts = [f"upgraded ({installed})" if not first_install else f"first-time installed ({installed})"]
        if redeploy_result:
            parts.append(
                f"skills re-deployed ({redeploy_result['succeeded']}/{redeploy_result['total']} targets)"
            )
        return success(
            result_data,
            "; ".join(parts),
        )
    return error(
        f"pip upgrade failed (returncode={pip_result.get('returncode')}); "
        f"see result.pip for details",
        "UpgradeFailed",
        data=result_data,
    )
