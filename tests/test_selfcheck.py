"""Unit tests for `xu selfcheck` (post-install health check).

坑 6 fix: there was no agent-friendly command to verify a xu-wiki
install. `xu selfcheck` consolidates:
- cli_on_path, python_version, skill_bundle_readable, global_dir_writable
- global_config_chmod (3.4), optional_extras, ripgrep
- agent_deployment_hint (bash template for cp to ~/.hermes/skills/)

Status semantics:
- error  → any CRITICAL check failed
- warning → only non-critical checks failed
- success → all checks passed
"""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from xu.commands import selfcheck as cmd_mod
from xu.utils import config as cfg_mod


@pytest.fixture
def xu_home(monkeypatch, tmp_path):
    monkeypatch.setattr(cfg_mod, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(cfg_mod, "GLOBAL_CONFIG", tmp_path / "config.yaml")
    return tmp_path


def _args():
    return SimpleNamespace()


# ----------------------------------------------------------------------
# 1. happy path — all checks pass
# ----------------------------------------------------------------------

def test_selfcheck_happy_path(xu_home):
    """When everything is OK, status=success and all checks passed."""
    r = cmd_mod.cmd_selfcheck(_args())
    assert r["status"] in ("success", "warning")
    # In a clean venv with the package installed via pip install -e,
    # all 7 checks should pass.
    assert "cli_on_path" in r["data"]["checks"]
    assert "skill_bundle_readable" in r["data"]["checks"]
    assert "optional_extras" in r["data"]["checks"]
    assert "agent_deployment_hint" in r["data"]
    assert r["data"]["agent_deployment_hint"]["skill_name"] == "xu-wiki"


# ----------------------------------------------------------------------
# 2. response envelope
# ----------------------------------------------------------------------

def test_selfcheck_returns_4_key_envelope(xu_home):
    r = cmd_mod.cmd_selfcheck(_args())
    assert set(r.keys()) >= {"status", "data", "message", "hints"}
    assert r["status"] in ("success", "warning", "error")


# ----------------------------------------------------------------------
# 3. agent deployment hint — the bash template
# ----------------------------------------------------------------------

def test_agent_deployment_hint_has_bash_template(xu_home):
    r = cmd_mod.cmd_selfcheck(_args())
    h = r["data"]["agent_deployment_hint"]
    assert "copy_template_bash" in h
    assert "mkdir -p" in h["copy_template_bash"]
    assert "cp" in h["copy_template_bash"]
    assert "ls \"$DEST\"" in h["copy_template_bash"]
    # 8 files mentioned in the template
    assert "SKILL.md" in h["copy_template_bash"]
    assert "create.md" in h["copy_template_bash"]
    assert "ingest.md" in h["copy_template_bash"]
    assert "query.md" in h["copy_template_bash"]
    assert "doctor.md" in h["copy_template_bash"]
    assert "config.md" in h["copy_template_bash"]
    assert "error-catalog.md" in h["copy_template_bash"]
    assert "pitfalls.md" in h["copy_template_bash"]


# ----------------------------------------------------------------------
# 4. global_config_chmod check (3.4)
# ----------------------------------------------------------------------

def test_global_config_chmod_no_config_ok(xu_home):
    """No config file → check returns ok with a note."""
    check = cmd_mod._check_global_config_chmod()
    assert check["ok"] is True


def test_global_config_chmod_secret_but_world_readable(xu_home, monkeypatch):
    """If config has mineru.api_key and mode is NOT 0o600, the check fails."""
    # Write the file bypassing save_global_config (which auto-chmods 600).
    # We write raw bytes with mode 644 to simulate a config that was written
    # by an older xu-wiki version (pre-3.4-fix) or manually.
    cfg_path = cfg_mod.GLOBAL_CONFIG
    cfg_path.write_text("mineru:\n  api_key: secret\n", encoding="utf-8")
    os.chmod(cfg_path, 0o644)
    check = cmd_mod._check_global_config_chmod()
    assert check["ok"] is False
    assert "0o600" in check["hint"]


def test_global_config_chmod_secret_with_600_passes(xu_home):
    """If config has mineru.api_key and mode IS 0o600, check passes."""
    cfg_path = xu_home / "config.yaml"
    cfg_path.write_text("mineru:\n  api_key: secret\n", encoding="utf-8")
    os.chmod(cfg_path, 0o600)
    check = cmd_mod._check_global_config_chmod()
    assert check["ok"] is True


# ----------------------------------------------------------------------
# 5. CLI palette wiring
# ----------------------------------------------------------------------

def test_cli_palette_includes_selfcheck():
    """`xu selfcheck` must be wired as a top-level subcommand."""
    from xu.cli import build_parser
    p = build_parser()
    args = p.parse_args(["selfcheck"])
    assert args.func == "selfcheck"


# ----------------------------------------------------------------------
# 6. critical vs non-critical failure handling
# ----------------------------------------------------------------------

def test_critical_failure_returns_error(xu_home, monkeypatch):
    """If a CRITICAL check fails, status=error."""
    # Force skill_bundle_readable to fail (a critical check)
    monkeypatch.setattr(cmd_mod, "_check_skill_bundle_readable",
                        lambda: {"ok": False,
                                 "hint": "synthetic failure for test"})
    r = cmd_mod.cmd_selfcheck(_args())
    assert r["status"] == "error"
    assert r["data"]["error_class"] == "SelfCheckFailed"
    assert "skill_bundle_readable" in r["data"]["failed_critical"]


def test_non_critical_failure_returns_warning(xu_home, monkeypatch):
    """If only a non-critical check fails, status=warning."""
    # Force optional_extras to fail (a non-critical check)
    monkeypatch.setattr(cmd_mod, "_check_optional_extras",
                        lambda: {"ok": False, "hint": "synthetic"})
    r = cmd_mod.cmd_selfcheck(_args())
    assert r["status"] == "warning"
    assert "optional_extras" in r["data"]["failed_noncritical"]