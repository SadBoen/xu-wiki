"""Process-layer audit log coverage (CONST-ARCH-6 / PRIN-ARCH-26).

Verifies the dual-path logging contract:
  - commands with a resolvable --wiki  →  <wiki>/.xu/audit.jsonl
  - commands without --wiki (or unresolvable)  →  ~/.xu/global_audit.jsonl

Also verifies the *negative* property: no command module may manually append
to audit.jsonl. The audit log has exactly one writer — the CLI entrypoint's
auto-log block. This prevents the past anti-pattern where album / ingest /
doctor each hand-rolled their own op-log.
"""

import json
import os
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from xu import cli as cli_mod
from xu.commands import create as create_mod
from xu.utils import config as cfg_mod


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def xu_home(monkeypatch, tmp_path):
    """Point global config dir at tmp_path for isolated registry + log."""
    monkeypatch.setattr(cfg_mod, "GLOBAL_DIR", tmp_path)
    monkeypatch.setattr(cfg_mod, "GLOBAL_CONFIG", tmp_path / "config.yaml")
    monkeypatch.setattr(cfg_mod, "GLOBAL_AUDIT_LOG", tmp_path / "global_audit.jsonl")
    return tmp_path


@pytest.fixture
def wiki(xu_home):
    """Create a fresh empty wiki; return (name, root)."""
    name = "log-test-wiki"
    root = xu_home / "wikis" / name
    r = create_mod.cmd_create(
        SimpleNamespace(
            name=name,
            path=str(root),
            alias=None,
        )
    )
    assert r["status"] == "success", r
    return name, root


def _read_jsonl(p: Path):
    if not p.exists():
        return []
    return [
        json.loads(line)
        for line in p.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# dual-path: per-wiki vs global
# ---------------------------------------------------------------------------


def test_wiki_command_writes_to_per_wiki_log(xu_home, wiki):
    """A command with a resolvable --wiki writes to <wiki>/.xu/audit.jsonl
    and NOT to the global log."""
    name, root = wiki
    audit_per_wiki = root / ".xu" / "audit.jsonl"
    assert not audit_per_wiki.exists()

    cli_mod.main(["nodes", "--wiki", name])

    # per-wiki log: 1 line
    per_wiki_lines = _read_jsonl(audit_per_wiki)
    assert len(per_wiki_lines) == 1
    rec = per_wiki_lines[0]
    assert rec["command"] == "nodes"
    assert rec["wiki"] == name
    assert rec["status"] == "success"
    assert "ts" in rec and "elapsed_ms" in rec

    # global log: untouched
    assert not (xu_home / "global_audit.jsonl").exists()


def test_no_wiki_command_writes_to_global_log(xu_home):
    """A command without --wiki (here: `wikis`) writes to global_audit.jsonl."""
    audit_global = xu_home / "global_audit.jsonl"
    assert not audit_global.exists()

    cli_mod.main(["wikis"])

    lines = _read_jsonl(audit_global)
    assert len(lines) == 1
    rec = lines[0]
    assert rec["command"] == "wikis"
    assert rec["wiki"] is None
    assert rec["status"] == "success"


def test_unresolvable_wiki_falls_back_to_global(xu_home):
    """A command with --wiki that does NOT resolve must NOT silently drop
    the log line — it falls back to global_audit.jsonl with wiki=<ref>."""
    cli_mod.main(["nodes", "--wiki", "no-such-wiki"])

    lines = _read_jsonl(xu_home / "global_audit.jsonl")
    assert len(lines) == 1
    rec = lines[0]
    assert rec["command"] == "nodes"
    assert rec["wiki"] == "no-such-wiki"
    assert rec["status"] == "error"
    assert "error_class" in rec  # unknown wiki → CLI returns error response


# ---------------------------------------------------------------------------
# failure path: error_class on failure
# ---------------------------------------------------------------------------


def test_failed_command_includes_error_class(xu_home):
    """On error, the audit record carries error_class from response.data."""
    cli_mod.main(
        ["create", "--name", "missing", "--path", ""]
    )  # missing --path → error
    lines = _read_jsonl(xu_home / "global_audit.jsonl")
    assert len(lines) == 1
    rec = lines[0]
    assert rec["status"] == "error"
    assert "error_class" in rec
    assert rec["error_class"]  # non-empty


# ---------------------------------------------------------------------------
# anti-regression: no command module may manually append audit
# ---------------------------------------------------------------------------


def test_no_command_module_imports_append_jsonl():
    """PRIN-ARCH-26: the audit log has exactly one writer — the CLI entrypoint.
    album / ingest / doctor (or any future command module) MUST NOT import
    `append_jsonl` to hand-roll op-logs. Verify by AST scan."""
    src_dir = Path(__file__).resolve().parent.parent / "src" / "xu" / "commands"
    offenders = []
    for py in src_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if re.search(
            r"^\s*from\s+\.\.?utils\.paths\s+import\s+.*\bappend_jsonl\b",
            text,
            re.MULTILINE,
        ):
            offenders.append(str(py.relative_to(src_dir.parent.parent)))
        if re.search(
            r"^\s*from\s+\.\.?\.?\s+import\s+.*\bappend_jsonl\b", text, re.MULTILINE
        ):
            offenders.append(str(py.relative_to(src_dir.parent.parent)))
    assert not offenders, (
        "Manual append_jsonl calls are forbidden in command modules "
        "(see PRIN-ARCH-26 / CONST-ARCH-6). Offenders:\n  " + "\n  ".join(offenders)
    )


def test_no_command_module_calls_append_jsonl_directly():
    """Backup static check: even if a module re-imports append_jsonl under
    a different alias, it must not call it."""
    src_dir = Path(__file__).resolve().parent.parent / "src" / "xu" / "commands"
    offenders = []
    for py in src_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        if re.search(r"\bappend_jsonl\s*\(", text):
            offenders.append(str(py.relative_to(src_dir.parent.parent)))
    assert not offenders, (
        "Direct append_jsonl(...) calls are forbidden in command modules. "
        "Offenders:\n  " + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# coverage: every CLI subcommand emits exactly one audit line
# ---------------------------------------------------------------------------


def _all_subcommands():
    parser = cli_mod.build_parser()
    cmds = []
    # Top-level subparsers
    for action in parser._actions:
        if isinstance(action, type(parser._subparsers).__base__):
            for name, sp in action.choices.items():
                cmds.append(name)
    return cmds


def _iter_subcommands(parser):
    """Yield (display_name, parser, required_dest_overrides) for every
    subcommand, recursively descending into nested subparsers (query-relation,
    list, report, alias, config)."""

    def _descend(p, prefix):
        sub_actions = [
            a
            for a in p._actions
            if hasattr(a, "choices") and isinstance(a.choices, dict)
        ]
        if not sub_actions:
            yield prefix, p
            return
        for name, sp in sub_actions[0].choices.items():
            new_prefix = f"{prefix} {name}" if prefix else name
            yield from _descend(sp, new_prefix)

    return list(_descend(parser, ""))


def _build_argv(sp, *, wiki_name):
    """Build an argv list that lets the parser accept the subcommand (using
    benign placeholders for required flags) so the auto-log block fires.
    Nested sub-action flags are filled with their first valid choice."""
    argv = []
    for a in sp._actions:
        if a.dest == "func":
            continue
        if hasattr(a, "choices") and isinstance(a.choices, dict):
            # Nested subparser: pick the first action and recurse
            first_sub = next(iter(a.choices.values()))
            argv.append(next(iter(a.choices)))
            argv += _build_argv(first_sub, wiki_name=wiki_name)
            continue
        if a.required:
            argv.append(f"--{a.dest.replace('_', '-')}")
            argv.append("x")
    return argv


def test_every_cli_subcommand_emits_exactly_one_audit_line(xu_home, wiki):
    """Walk every registered subcommand (recursively, including nested
    subparsers), invoke it once, and verify exactly one JSONL line is
    appended for that command."""
    name, root = wiki
    parser = cli_mod.build_parser()
    subcommands = _iter_subcommands(parser)
    assert subcommands, "parser must expose subparsers"

    for cmd_label, sp in subcommands:
        per_wiki_log = root / ".xu" / "audit.jsonl"
        per_wiki_before = len(_read_jsonl(per_wiki_log))
        glob_log = xu_home / "global_audit.jsonl"
        glob_before = len(_read_jsonl(glob_log))

        argv = cmd_label.split()
        if any(a.dest == "wiki" for a in sp._actions):
            argv += ["--wiki", name]
        argv += _build_argv(sp, wiki_name=name)

        try:
            cli_mod.main(argv)
        except SystemExit:
            pass

        per_count = len(_read_jsonl(per_wiki_log)) - per_wiki_before
        glob_count = len(_read_jsonl(glob_log)) - glob_before
        total = per_count + glob_count
        assert total == 1, (
            f"command {cmd_label!r} emitted {total} audit lines "
            f"(per_wiki={per_count}, global={glob_count}); expected exactly 1"
        )


# ---------------------------------------------------------------------------
# append semantics: not overwrite
# ---------------------------------------------------------------------------


def test_audit_log_appends_not_overwrites(xu_home):
    """Two invocations should produce 2 lines, not 1 — append semantics."""
    cli_mod.main(["wikis"])
    cli_mod.main(["wikis"])
    lines = _read_jsonl(xu_home / "global_audit.jsonl")
    assert len(lines) == 2


def test_audit_record_fields_stable(xu_home):
    """Every audit record MUST carry the documented field set."""
    cli_mod.main(["wikis"])
    rec = _read_jsonl(xu_home / "global_audit.jsonl")[0]
    expected = {"ts", "command", "wiki", "status", "elapsed_ms"}
    assert expected <= set(rec.keys()), (
        f"audit record missing required fields: {expected - set(rec.keys())}"
    )
    assert isinstance(rec["ts"], int)
    assert isinstance(rec["elapsed_ms"], int)
    assert rec["status"] in ("success", "warning", "error")
