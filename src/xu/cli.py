"""xu CLI entrypoint — argparse dispatcher.

Every command prints a 4-key JSON response (CONST-ARCH-1) and logs to audit.

Install:  handled by pip — `pip install "xu-wiki[parse,nlp,vision]"`.
Uninstall: handled by THIS CLI — `xu uninstall`. Default dry-run.
          The agent invokes it (never the user) via /xu-wiki config.
Skills: NOT handled by this CLI. The agent uses its own skill manager and
copies the source markdown files (location: `xu skills path`).
"""
from __future__ import annotations

from . import __version__
import argparse
import sys
import time
import traceback
import logging
import logging.handlers
from pathlib import Path

from .utils.response import emit, error


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xu",
        description="Relation-driven wiki engine: Page (knowledge) + Entity/List/Report (learning)",
    )
    # Bug 3 fix: every reasonable CLI has `--version`. Without it the
    # agent (and the user) has no way to confirm "did pip actually
    # install the package I think it did?" beyond running `--help`.
    p.add_argument("--version", action="version",
                   version=f"%(prog)s-wiki {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    # ---- M1: skills / create ----
    sp = sub.add_parser("skills", help="skill bundle location (for agents to cp)")
    ssub = sp.add_subparsers(dest="skills_action", required=True)
    ssub.add_parser("path", help="print source dir of the xu-wiki skill bundle").set_defaults(func="skills_path")
    ssub.add_parser("list", help="list files in the xu-wiki skill bundle").set_defaults(func="skills_list")
    sp.set_defaults(func="skills_default")

    sp = sub.add_parser("create", help="create a new empty wiki instance")
    sp.add_argument("--name", required=False, help="wiki name (required, explicit)")
    sp.add_argument("--path", required=True, help="target directory for the wiki")
    sp.add_argument("--alias", required=False, help="optional alias")
    sp.set_defaults(func="create")

    sp = sub.add_parser("wikis", help="list registered wikis (read-only)")
    sp.set_defaults(func="wikis")

    # ---- M2: ingest / query / read ----
    sp = sub.add_parser("ingest-file", help="Phase 1: parse a file (or images) into temp file (no node created)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--file", help="single source file (for article/table content)")
    sp.add_argument("--files", help="comma-separated absolute image paths (for gallery/album content)")
    sp.add_argument("--title", required=True, help="title for the node")
    sp.add_argument("--node-path", default="", help="logical partition path")
    sp.add_argument("--layout", default="table", choices=["table", "list"],
                    help="body layout for gallery content (default table)")
    sp.add_argument("--vision", action="store_true",
                    help="mark vision intent (per-photo captions); SOP should ask user first")
    sp.add_argument("--captions", default="",
                    help='JSON object {filename: description} (optional)')
    sp.add_argument("--author", default="agent")
    sp.set_defaults(func="ingest_file")

    sp = sub.add_parser("ingest-commit", help="Phase 2: commit temp file into wiki (only write entry)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--temp", required=False, help="Phase 1 temp file to commit")
    sp.add_argument("--title", required=False, help="title (required unless --native with frontmatter)")
    sp.add_argument("--node-path", default="")
    sp.add_argument("--content-type", default="article", choices=["article", "table", "gallery"],
                    help="body form: article (prose) | table | gallery")
    sp.add_argument("--relations", default="", help="JSON array of {to, relation_name, comment?}")
    sp.add_argument("--native", default="", help="raw markdown string (bypass parse, still validate)")
    sp.add_argument("--source", default="", help="abs path to source file (required when --native is used, for PRIN-ING-6 raws copy)")
    sp.add_argument("--author", default="agent")
    sp.set_defaults(func="ingest_commit")

    sp = sub.add_parser("ingest-verify",
                        help="Verify a committed node's integrity (DB / nodes/ / raws/ / body format)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uid", required=True, help="uid of the node to verify")
    sp.set_defaults(func="ingest_verify")

    sp = sub.add_parser("query", help="search wiki: returns top N indexed blocks (UID/title/layer/position)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--keywords", required=True, help="comma-separated keywords (LLM generates these)")
    sp.add_argument("--include-inactive", action="store_true")
    sp.add_argument("--top-k", type=int, default=None,
                    help="override query.blocks config (default: 50)")
    sp.set_defaults(func="query")

    sp = sub.add_parser("expand", help="fetch body + relations for specific UIDs (Path B)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uids", required=True, help="comma-separated UIDs to expand")
    sp.add_argument("--limit", type=int, default=None,
                    help="max relations per UID (default: all)")
    sp.add_argument("--relation-names", default=None,
                    help="comma-separated relation names to follow (default: all)")
    sp.set_defaults(func="expand")

    sp = sub.add_parser("read", help="read a single node full body")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uid", required=True)
    sp.set_defaults(func="read")

    sp = sub.add_parser("nodes", help="DB node metadata query (read-only)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--layer", default=None, choices=["Page", "List", "Report", "Entity"])
    sp.add_argument("--include-inactive", action="store_true")
    sp.set_defaults(func="nodes")

    # ---- M3: relations ----
    sp = sub.add_parser("query-relation", help="manage the 50-edge LRU relation list")
    rsub = sp.add_subparsers(dest="rel_action", required=True)
    radd = rsub.add_parser("add")
    radd.add_argument("--wiki", required=True)
    radd.add_argument("--from-uid", required=True)
    radd.add_argument("--to-uid", required=True)
    radd.add_argument("--relation-name", required=True)
    radd.add_argument("--comment", default="")
    rlist = rsub.add_parser("list")
    rlist.add_argument("--wiki", required=True)
    rlist.add_argument("--from-uid", required=True)
    sp.set_defaults(func="query_relation")

    # ---- M4: list / report ----
    sp = sub.add_parser("list", help="Node_List create/show")
    lsub = sp.add_subparsers(dest="list_action", required=True)
    lc = lsub.add_parser("create")
    lc.add_argument("--wiki", required=True)
    lc.add_argument("--title", required=True)
    lc.add_argument("--members", required=True, help="comma-separated member UIDs")
    lc.add_argument("--dimension", default="", help="comparison dimension")
    lc.add_argument("--node-path", default="")
    ls = lsub.add_parser("show")
    ls.add_argument("--wiki", required=True)
    ls.add_argument("--uid", required=True)
    lm = lsub.add_parser("modify")
    lm.add_argument("--wiki", required=True)
    lm.add_argument("--uid", required=True)
    lm.add_argument("--title", default=None)
    lm.add_argument("--members", default=None, help="comma-separated member UIDs")
    lm.add_argument("--dimension", default=None)
    sp.set_defaults(func="list_cmd")

    sp = sub.add_parser("report", help="Node_Report create/show (evidence chain required)")
    rpsub = sp.add_subparsers(dest="report_action", required=True)
    rc = rpsub.add_parser("create")
    rc.add_argument("--wiki", required=True)
    rc.add_argument("--title", required=True)
    rc.add_argument("--body", required=True, help="report body (markdown)")
    rc.add_argument("--references", required=True, help="comma-separated evidence UIDs")
    rc.add_argument("--node-path", default="")
    rs = rpsub.add_parser("show")
    rs.add_argument("--wiki", required=True)
    rs.add_argument("--uid", required=True)
    rm = rpsub.add_parser("modify")
    rm.add_argument("--wiki", required=True)
    rm.add_argument("--uid", required=True)
    rm.add_argument("--title", default=None)
    rm.add_argument("--body", default=None, help="report body (markdown)")
    rm.add_argument("--references", default=None, help="comma-separated evidence UIDs")
    sp.set_defaults(func="report_cmd")

    sp = sub.add_parser("entity", help="Node_Entity create/show")
    espec = sp.add_subparsers(dest="entity_action", required=True)
    ec = espec.add_parser("create")
    ec.add_argument("--wiki", required=True)
    ec.add_argument("--title", required=True)
    ec.add_argument("--source-page", dest="source_page", default=None,
                   help="UID of the Page this entity was extracted from")
    ec.add_argument("--body", default="", help="entity notes (markdown)")
    ec.add_argument("--node-path", default="")
    es = espec.add_parser("show")
    es.add_argument("--wiki", required=True)
    es.add_argument("--uid", required=True)
    eem = espec.add_parser("modify")
    eem.add_argument("--wiki", required=True)
    eem.add_argument("--uid", required=True)
    eem.add_argument("--title", default=None)
    eem.add_argument("--body", default=None, help="entity notes (markdown)")
    sp.set_defaults(func="entity_cmd")

    # ---- M5: doctor / delete-node / rebuild ----
    for name in [
        "doctor", "doctor-fields", "doctor-files", "doctor-relations",
        "doctor-l1-immutable", "doctor-report-evidence",
        "doctor-node-path-organization", "doctor-all",
    ]:
        spx = sub.add_parser(name, help=f"{name} health check (read-only by default)")
        spx.add_argument("--wiki", required=True)
        spx.add_argument("--fix", action="store_true", help="apply mechanical fixes")
        spx.set_defaults(func="doctor", doctor_kind=name)

    sp = sub.add_parser("delete-node", help="physically delete a node (checks references first)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uid", required=True)
    sp.add_argument("--force", action="store_true", help="proceed despite derived-layer references")
    sp.set_defaults(func="delete_node")

    sp = sub.add_parser("rebuild", help="rebuild derived layers (never touches Page)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--granularity", default="keep-l1", choices=["keep-l1", "keep-l1-l2", "full"])
    sp.set_defaults(func="rebuild")

    sp = sub.add_parser("reorganize",
                        help="atomically move a Page to a new node_path partition (PRIN-ARCH-25)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uid", required=True)
    sp.add_argument("--new-node-path", required=True,
                    help="target node_path (e.g. certificates/qsa)")
    sp.set_defaults(func="reorganize")

    # ---- M6: SOP-config (alias / register / unregister / config) ----
    sp = sub.add_parser("alias", help="manage wiki aliases (set / unset / show)")
    asub = sp.add_subparsers(dest="alias_action", required=True)
    asp_set = asub.add_parser("set", help="set or change the alias of a registered wiki")
    asp_set.add_argument("--wiki", required=True, help="wiki name OR alias")
    asp_set.add_argument("--alias", required=True)
    asp_set.set_defaults(func="alias_set")
    asp_unset = asub.add_parser("unset", help="remove the alias from a wiki")
    asp_unset.add_argument("--wiki", required=True)
    asp_unset.set_defaults(func="alias_unset")
    asp_show = asub.add_parser("show", help="show the current alias of a wiki")
    asp_show.add_argument("--wiki", required=True)
    asp_show.set_defaults(func="alias_show")

    sp = sub.add_parser("register", help="register an existing directory as a wiki (no files written)")
    sp.add_argument("--name", required=True)
    sp.add_argument("--path", required=True)
    sp.add_argument("--alias", required=False)
    sp.set_defaults(func="register")

    sp = sub.add_parser("unregister", help="remove a wiki from the registry (wiki files untouched)")
    sp.add_argument("--name", required=True, help="wiki name OR alias")
    sp.set_defaults(func="unregister")

    sp = sub.add_parser("config", help="manage global config (MinerU key, paths)")
    csub = sp.add_subparsers(dest="config_action", required=True)
    csub.add_parser("set-mineru-key", help="set MinerU key from MINERU_API_KEY env").set_defaults(func="config_set_mineru_key")
    csub.add_parser("show", help="show global config (secrets masked)").set_defaults(func="config_show")
    csub.add_parser("path", help="print global config file paths").set_defaults(func="config_path")

    # ---- M7: software lifecycle (install = pip; update / uninstall = CLI) ----
    sp = sub.add_parser("update", help="upgrade xu-wiki in-place (pip) and re-deploy skill bundles")
    sp.add_argument("--check", action="store_true",
                    help="only check for updates; do not install anything")
    sp.add_argument("--no-redeploy", action="store_true",
                    help="skip skill re-deploy step after pip upgrade")
    sp.set_defaults(func="update")

    sp = sub.add_parser("uninstall", help="dry-run by default; --execute to actually uninstall xu-wiki")
    g_dry = sp.add_mutually_exclusive_group()
    g_dry.add_argument("--dry-run", dest="dry_run", action="store_true",
                       default=None,
                       help="explicit dry-run (default; provided for clarity — "
                            "explicit > implicit for script users)")
    g_dry.add_argument("--execute", dest="execute", action="store_true",
                       default=None,
                       help="actually perform the uninstall")
    sp.add_argument("--preserve-config", action="store_true",
                    help="keep ~/.xu-wiki/ config dir after uninstall (default: remove it)")
    sp.add_argument("--keep-pip", action="store_true",
                    help="do NOT call pip uninstall (test / dev escape hatch)")
    sp.add_argument("--keep-skill", action="store_true",
                    help="keep skill bundle(s) after uninstall (default: remove them)")
    sp.add_argument("--target", action="append", default=[],
                    dest="targets",
                    help="agent harness to target (hermes / trae / claude / cursor); "
                         "can be specified multiple times; default: all deployed targets")
    sp.set_defaults(func="uninstall")

    # ---- M8: post-install health check (坑 6 fix) ----
    sub.add_parser("selfcheck",
                   help="verify xu-wiki install (CLI / Python / skills / ~/.xu-wiki/ / extras); "
                        "agent-callable, returns 4-key JSON").set_defaults(func="selfcheck")

    # ---- M9: skill deployment helper (agent-callable, replaces manual cp -r) ----
    sp_deploy = sub.add_parser("deploy",
                                help="deploy artefacts to agent-visible locations "
                                     "(currently: skill bundle)")
    deploy_sub = sp_deploy.add_subparsers(dest="deploy_action", required=True)
    sp_skill = deploy_sub.add_parser("skill",
                                      help="copy the skill bundle to <target>'s discovery dir")
    sp_skill.add_argument("--target",
                          choices=("hermes", "trae", "claude", "cursor", "auto"),
                          default="auto",
                          help="agent platform to deploy to (default: auto)")
    sp_skill.add_argument("--copy",
                          action="store_true",
                          help="copy files instead of symlinking (symlink is default)")
    sp_skill.set_defaults(func="deploy_skill")

    return p


_DISPATCH_TABLE: dict[str, tuple[str, str]] = {
    "skills_path": ("commands.skills", "cmd_skills"),
    "skills_list": ("commands.skills", "cmd_skills"),
    "skills_default": ("commands.skills", "cmd_skills"),
    "create": ("commands.create", "cmd_create"),
    "wikis": ("_inline", "wikis"),
    "ingest_file": ("commands.ingest", "cmd_ingest_file"),
    "ingest_commit": ("commands.ingest", "cmd_ingest_commit"),
    "ingest_verify": ("commands.ingest", "cmd_ingest_verify"),
    "query": ("commands.query", "cmd_query"),
    "expand": ("commands.query", "cmd_expand"),
    "read": ("commands.query", "cmd_read"),
    "nodes": ("commands.query", "cmd_nodes"),
    "query_relation": ("commands.relations", "cmd_query_relation"),
    "list_cmd": ("commands.layers", "cmd_list"),
    "report_cmd": ("commands.layers", "cmd_report"),
    "entity_cmd": ("commands.layers", "cmd_entity"),
    "doctor": ("commands.doctor", "cmd_doctor"),
    "delete_node": ("commands.doctor", "cmd_delete_node"),
    "rebuild": ("commands.doctor", "cmd_rebuild"),
    "reorganize": ("commands.reorganize", "cmd_reorganize"),
    "alias_set": ("commands.config", "cmd_alias_set"),
    "alias_unset": ("commands.config", "cmd_alias_unset"),
    "alias_show": ("commands.config", "cmd_alias_show"),
    "register": ("commands.config", "cmd_register"),
    "unregister": ("commands.config", "cmd_unregister"),
    "config_set_mineru_key": ("commands.config", "cmd_config_set_mineru_key"),
    "config_show": ("commands.config", "cmd_config_show"),
    "config_path": ("commands.config", "cmd_config_path"),
    "uninstall": ("commands.uninstall", "cmd_uninstall"),
    "update": ("commands.update", "cmd_update"),
    "selfcheck": ("commands.selfcheck", "cmd_selfcheck"),
    "deploy_skill": ("commands.deploy_skill", "cmd_deploy_skill"),
}


def _dispatch(args) -> dict:
    import importlib
    func = args.func
    entry = _DISPATCH_TABLE.get(func)
    if entry is None:
        return error(f"unknown command function: {func}", "UnknownCommand")
    module_path, func_name = entry
    if module_path == "_inline":
        if func == "wikis":
            from .utils.config import load_registry
            from .utils.response import success
            return success(load_registry().get("wikis", {}), "registered wikis")
    mod = importlib.import_module(f"xu.{module_path}")
    return getattr(mod, func_name)(args)


def main(argv: list[str] | None = None) -> int:
    _log_dir = Path.home() / ".xu-wiki"
    _log_dir.mkdir(exist_ok=True)
    _handler = logging.handlers.RotatingFileHandler(
        _log_dir / "xu-wiki.log",
        maxBytes=5*1024*1024, backupCount=3)
    _handler.setLevel(logging.ERROR)
    logging.root.addHandler(_handler)

    parser = build_parser()
    # CONST-ARCH-1: every CLI invocation MUST emit a 4-key JSON response,
    # including argparse-level errors (missing/unknown args). Override
    # parser.error so it raises instead of calling sys.exit(2)+stderr.
    class _ArgParseError(Exception):
        def __init__(self, message):
            super().__init__(message)
            self.message = message

    def _parser_error(message):
        raise _ArgParseError(message)

    parser.error = _parser_error
    # Subparsers have their own .error method; override on every subparser too.
    for action in parser._actions:
        if isinstance(action, __import__("argparse")._SubParsersAction):
            for sub in action.choices.values():
                sub.error = _parser_error
    try:
        args = parser.parse_args(argv)
    except _ArgParseError as e:
        # Map argparse error → 4-key JSON; do not pollute stdout with usage banner.
        response = error(
            e.message,
            "ArgParseError",
            hints=["check the command name + flags; see `xu <subcommand> --help`"],
        )
        try:
            from .utils.config import GLOBAL_AUDIT_LOG
            from .utils.paths import append_jsonl
            record = {
                "ts": int(time.time()),
                "command": "<argparse>",
                "wiki": None,
                "status": "error",
                "elapsed_ms": 0,
                "error_class": "ArgParseError",
            }
            append_jsonl(GLOBAL_AUDIT_LOG, record, mkdir=False)
        except Exception:
            pass
        return emit(response)
    start = time.time()
    try:
        response = _dispatch(args)
    except Exception as e:  # never crash without a 4-key response
        logging.error("[xu] command=%s %s: %s",
                      getattr(args, "command", "?"), type(e).__name__, e)
        response = error(
            f"unhandled exception: {e}",
            type(e).__name__,
            data={"traceback": traceback.format_exc().splitlines()[-5:]},
        )
    # PRIN-LOG-1 process-layer audit: ALL CLI commands emit exactly one line.
    # - commands with a resolvable --wiki → <wiki>/.xu/audit.jsonl
    # - commands without wiki OR unresolvable wiki → GLOBAL_AUDIT_LOG
    try:
        from .utils.config import GLOBAL_AUDIT_LOG
        from .utils.paths import append_jsonl
        from .utils.wiki import resolve_wiki

        wiki_ref = getattr(args, "wiki", None)
        audit_path = GLOBAL_AUDIT_LOG
        wiki_for_log = None

        if wiki_ref:
            # Preserve the wiki reference in the log even when it doesn't
            # resolve — an unresolvable wiki is itself a diagnostic signal
            # (typo'd name, missing registry entry, wrong CWD).
            wiki_for_log = wiki_ref
            ctx = resolve_wiki(wiki_ref)
            if ctx:
                audit_path = ctx.log_path

        record = {
            "ts": int(start),
            "command": args.command,
            "wiki": wiki_for_log,
            "status": response.get("status"),
            "elapsed_ms": int((time.time() - start) * 1000),
        }
        if response.get("status") == "error":
            err_data = response.get("data") or {}
            if "error_class" in err_data:
                record["error_class"] = err_data["error_class"]
        append_jsonl(audit_path, record, mkdir=(audit_path != GLOBAL_AUDIT_LOG))
    except Exception:
        pass
    return emit(response)


if __name__ == "__main__":
    sys.exit(main())
