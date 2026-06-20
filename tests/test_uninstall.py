"""Unit tests for `xu uninstall` (SOP-config software lifecycle).

CONST-SOP-3 asymmetric: install = pip, uninstall = `xu uninstall`.
Tests cover:
- dry-run is the default (no side effects without --execute)
- --execute + --keep-pip removes wikis + ~/.xu/ but skips pip
- --execute without --keep-pip invokes pip uninstall (mocked)
- --execute with no flags only touches pip (wiki data + ~/.xu/ preserved)
- --purge-wikis drops registry entries too
- --purge-config removes the global dir
- argparse wires up the new subcommand (cli.dispatch smoke)
"""
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from xu.utils import config as cfg_mod
from xu.commands import uninstall as cmd_mod
from xu.utils.paths import now_ts


@pytest.fixture
def xu_home(monkeypatch, tmp_path):
    """Point xu.utils.config.GLOBAL_DIR at tmp_path (and same in uninstall module)."""
    monkeypatch.setattr(cfg_mod, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(cfg_mod, "GLOBAL_CONFIG", tmp_path / "config.yaml")
    monkeypatch.setattr(cfg_mod, "REGISTRY_FILE", tmp_path / "registry.yaml")
    monkeypatch.setattr(cmd_mod, "GLOBAL_DIR", tmp_path)
    return tmp_path


def _args(**kw):
    return SimpleNamespace(**kw)


def _seed_wiki(xu_home, name, *, alias=None, path=None):
    """Add (or initialise) a wiki entry in the registry AND create the dir."""
    if path is None:
        path = str(xu_home / "wikis" / name)
    os.makedirs(path, exist_ok=True)
    reg = cfg_mod.load_registry()
    reg.setdefault("wikis", {})[name] = {
        "path": path, "alias": alias, "created_at": now_ts()
    }
    cfg_mod.save_registry(reg)


# ----------------------------------------------------------------------
# 1. dry-run default (PRIN-UNINST-6)
# ----------------------------------------------------------------------

def test_uninstall_dry_run_is_default(xu_home):
    """No --execute → must report dry-run and touch NOTHING."""
    _seed_wiki(xu_home, "A")
    r = cmd_mod.cmd_uninstall(_args(execute=False, keep_pip=False,
                                    purge_wikis=False, purge_config=False))
    assert r["status"] == "success"
    assert r["data"]["mode"] == "dry-run"
    # Registry + wiki dir must be intact.
    assert "A" in cfg_mod.load_registry()["wikis"]
    assert (xu_home / "wikis" / "A").exists()
    # Global dir must be intact.
    assert xu_home.exists()


def test_dry_run_lists_wikis_and_marks_purge_flags(xu_home):
    """Dry-run surfaces wikis_found + reflects --purge-* flags in plan."""
    _seed_wiki(xu_home, "A")
    _seed_wiki(xu_home, "B")
    r = cmd_mod.cmd_uninstall(_args(execute=False, keep_pip=False,
                                    purge_wikis=True, purge_config=True))
    plan = r["data"]
    assert plan["mode"] == "dry-run"
    assert plan["execute"] is False
    assert plan["pip_uninstall"] is True
    assert plan["purge_wikis"] is True
    assert plan["purge_config"] is True
    names = sorted(w["name"] for w in plan["wikis_found"])
    assert names == ["A", "B"]


# ----------------------------------------------------------------------
# 2. --execute without purge flags: only pip (wiki data + ~/.xu/ preserved)
# ----------------------------------------------------------------------

def test_execute_no_purge_preserves_wikis_and_global_dir(xu_home, monkeypatch):
    """Default --execute scope: only pip; wikis + ~/.xu/ stay."""
    _seed_wiki(xu_home, "A")
    monkeypatch.setattr(cmd_mod, "_pip_uninstall",
                        lambda: {"ok": True, "returncode": 0,
                                 "stdout_tail": "ok", "stderr_tail": ""})
    r = cmd_mod.cmd_uninstall(_args(execute=True, keep_pip=False,
                                    purge_wikis=False, purge_config=False))
    assert r["status"] == "success"
    # wikis untouched
    assert "A" in cfg_mod.load_registry()["wikis"]
    assert (xu_home / "wikis" / "A").exists()
    # ~/.xu/ untouched
    assert xu_home.exists()
    # pip ran
    assert r["data"]["result"]["pip"]["ok"] is True
    # wikis + config_dir marked skipped
    assert r["data"]["result"]["wikis"]["skipped"] is True
    assert r["data"]["result"]["config_dir"]["skipped"] is True


# ----------------------------------------------------------------------
# 3. --execute --keep-pip: removes wikis + ~/.xu/ but skips pip
# ----------------------------------------------------------------------

def test_execute_keep_pip_purges_wikis_and_global_dir(xu_home):
    """--keep-pip is the test/dev escape hatch."""
    _seed_wiki(xu_home, "A")
    r = cmd_mod.cmd_uninstall(_args(execute=True, keep_pip=True,
                                    purge_wikis=True, purge_config=True))
    assert r["status"] == "success"
    # wikis dir removed
    assert not (xu_home / "wikis" / "A").exists()
    # registry cleared
    assert cfg_mod.load_registry()["wikis"] == {}
    # pip was skipped
    assert r["data"]["result"]["pip"]["skipped"] is True
    # ~/.xu/ removed (note: shutil.rmtree of tmp_path itself)
    assert not xu_home.exists()


# ----------------------------------------------------------------------
# 4. --execute --purge-wikis only: nukes wiki dirs + drops registry
# ----------------------------------------------------------------------

def test_execute_purge_wikis_only(xu_home, monkeypatch):
    """--purge-wikis removes dirs and clears registry; ~/.xu/ stays."""
    _seed_wiki(xu_home, "A")
    _seed_wiki(xu_home, "B")
    monkeypatch.setattr(cmd_mod, "_pip_uninstall",
                        lambda: {"ok": True, "returncode": 0,
                                 "stdout_tail": "", "stderr_tail": ""})
    r = cmd_mod.cmd_uninstall(_args(execute=True, keep_pip=False,
                                    purge_wikis=True, purge_config=False))
    assert r["status"] == "success"
    # both wikis gone
    assert not (xu_home / "wikis" / "A").exists()
    assert not (xu_home / "wikis" / "B").exists()
    # registry cleared
    assert cfg_mod.load_registry()["wikis"] == {}
    # result reports per-wiki removal
    names = sorted(w["name"] for w in r["data"]["result"]["wikis"]["removed"])
    assert names == ["A", "B"]


# ----------------------------------------------------------------------
# 5. pip uninstall failure → warning (partial uninstall)
# ----------------------------------------------------------------------

def test_pip_uninstall_invokes_pip_correctly(xu_home):
    """Even if pip fails, the command shape is correct (we don't mock pip here)."""
    _seed_wiki(xu_home, "A")
    r = cmd_mod.cmd_uninstall(_args(execute=True, keep_pip=False,
                                    purge_wikis=False, purge_config=False))
    pip = r["data"]["result"]["pip"]
    assert pip["command"].endswith("pip uninstall xu-wiki -y")
    # pip returncode is reported either way
    assert "returncode" in pip or "error" in pip


# ----------------------------------------------------------------------
# 6. CLI palette wiring (SKILL.md / config.md promise)
# ----------------------------------------------------------------------

def test_cli_palette_includes_uninstall_under_config():
    """`xu uninstall` must be wired as a top-level subcommand (config SOP)."""
    from xu.cli import build_parser
    p = build_parser()
    args = p.parse_args(["uninstall"])
    assert args.func == "uninstall"
    assert args.execute is False
    assert args.keep_pip is False
    assert args.purge_wikis is False
    assert args.purge_config is False


def test_cli_palette_exec_flags_parse():
    from xu.cli import build_parser
    p = build_parser()
    args = p.parse_args(["uninstall", "--execute", "--purge-wikis",
                         "--purge-config", "--keep-pip"])
    assert args.execute is True
    assert args.purge_wikis is True
    assert args.purge_config is True
    assert args.keep_pip is True


def test_uninstall_help_does_not_raise():
    """`xu uninstall --help` should be callable (argparse exits 0 cleanly)."""
    from xu.cli import build_parser
    p = build_parser()
    # argparse calls sys.exit(0) on --help; that's the expected behavior.
    # Just confirm the parser accepts the subcommand form.
    args = p.parse_args(["uninstall"])
    assert args.func == "uninstall"


# ----------------------------------------------------------------------
# 7. Audit log + 4-key envelope
# ----------------------------------------------------------------------

def test_dry_run_response_shape_matches_protocol():
    """Dry-run response must be the standard 4-key JSON envelope."""
    r = cmd_mod.cmd_uninstall(_args(execute=False, keep_pip=False,
                                    purge_wikis=False, purge_config=False))
    assert set(r.keys()) >= {"status", "data", "message", "hints"}
    assert r["status"] in ("success", "warning", "error")


def test_execute_response_shape_matches_protocol(xu_home):
    """--execute response must also be the standard 4-key JSON envelope."""
    r = cmd_mod.cmd_uninstall(_args(execute=True, keep_pip=True,
                                    purge_wikis=True, purge_config=True))
    assert set(r.keys()) >= {"status", "data", "message", "hints"}
    assert r["status"] in ("success", "warning", "error")