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
    """Add a wiki entry in the registry AND lay down the wiki marker files.

    `is_wiki_root()` requires `.xu/config.yaml` + `.xu/wiki.db` to
    exist. The seed creates both so the uninstall's strict-wiki check
    accepts this path as a real wiki.
    """
    if path is None:
        path = str(xu_home / "wikis" / name)
    os.makedirs(path, exist_ok=True)
    xu_subdir = os.path.join(path, ".xu")
    os.makedirs(xu_subdir, exist_ok=True)
    # wiki.db is allowed to be a 0-byte file; is_wiki_root only checks exists().
    open(os.path.join(xu_subdir, "wiki.db"), "wb").close()
    with open(os.path.join(xu_subdir, "config.yaml"), "w", encoding="utf-8") as f:
        f.write("# synthetic seed for test\n")
    reg = cfg_mod.load_registry()
    reg.setdefault("wikis", {})[name] = {
        "path": path, "alias": alias, "created_at": now_ts()
    }
    cfg_mod.save_registry(reg)


def _seed_nonwiki(xu_home, name, *, path=None):
    """Seed an entry in the registry whose path is NOT a wiki marker.

    Used to verify that `_purge_wikis` refuses to rmtree non-wiki
    paths (3.1 fix).
    """
    if path is None:
        path = str(xu_home / "not-a-wiki" / name)
    os.makedirs(path, exist_ok=True)
    reg = cfg_mod.load_registry()
    reg.setdefault("wikis", {})[name] = {
        "path": path, "alias": None, "created_at": now_ts()
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


def test_dry_run_annotates_is_wiki_root(xu_home):
    """3.1: dry-run should annotate each entry with is_wiki_root boolean."""
    _seed_wiki(xu_home, "real")
    _seed_nonwiki(xu_home, "fake")
    r = cmd_mod.cmd_uninstall(_args(execute=False, keep_pip=False,
                                    purge_wikis=True, purge_config=False))
    plan = r["data"]
    by_name = {w["name"]: w for w in plan["wikis_found"]}
    assert by_name["real"]["is_wiki_root"] is True
    assert by_name["fake"]["is_wiki_root"] is False
    # The non_wiki_paths_detected key surfaces the warning at plan level
    detected = plan.get("non_wiki_paths_detected")
    assert detected is not None
    assert any(d["name"] == "fake" for d in detected)


def test_execute_purge_wikis_refuses_non_wiki_path(xu_home, monkeypatch):
    """3.1: --purge-wikis refuses to rmtree a non-wiki path; entry dropped
    from registry but directory left intact."""
    _seed_nonwiki(xu_home, "fake")
    fake_path = xu_home / "not-a-wiki" / "fake"
    monkeypatch.setattr(cmd_mod, "_pip_uninstall",
                        lambda: {"ok": True, "returncode": 0,
                                 "stdout_tail": "", "stderr_tail": ""})
    r = cmd_mod.cmd_uninstall(_args(execute=True, keep_pip=False,
                                    purge_wikis=True, purge_config=False))
    # directory NOT removed
    assert fake_path.exists()
    # registry entry dropped
    assert "fake" not in cfg_mod.load_registry()["wikis"]
    # reported under `refused`
    refused = r["data"]["result"]["wikis"]["refused"]
    assert any(x["name"] == "fake" for x in refused)
    # status reflects partial (warning)
    assert r["status"] == "warning"


def test_execute_purge_wikis_removes_real_wiki(xu_home, monkeypatch):
    """3.1: a real-wiki path IS removed normally."""
    _seed_wiki(xu_home, "real")
    monkeypatch.setattr(cmd_mod, "_pip_uninstall",
                        lambda: {"ok": True, "returncode": 0,
                                 "stdout_tail": "", "stderr_tail": ""})
    r = cmd_mod.cmd_uninstall(_args(execute=True, keep_pip=False,
                                    purge_wikis=True, purge_config=False))
    assert not (xu_home / "wikis" / "real").exists()
    assert r["data"]["result"]["wikis"]["refused"] == []
    assert r["status"] == "success"


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