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

from .utils.response import emit, error


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xu",
        description="Relation-driven three-layer wiki engine (xu-wiki)",
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
    sp = sub.add_parser("ingest-file", help="Phase 1: parse a file into pending (no node created)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--file", required=True)
    sp.add_argument("--node-path", default="", help="logical partition path")
    sp.set_defaults(func="ingest_file")

    sp = sub.add_parser("ingest-commit", help="Phase 2: commit pending pages into L1 (only write entry)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--pending", required=False, help="pending file to commit (default: all for the source)")
    sp.add_argument("--title", required=False, help="title (required unless --native with frontmatter)")
    sp.add_argument("--node-path", default="")
    sp.add_argument("--template", default="article", choices=["article", "table", "gallery"])
    sp.add_argument("--digest", default="")
    sp.add_argument("--relations", default="", help="JSON array of {to, relation_name, comment?}")
    sp.add_argument("--native", default="", help="raw markdown string (bypass parse, still validate)")
    sp.add_argument("--author", default="agent")
    sp.set_defaults(func="ingest_commit")

    sp = sub.add_parser("ingest-album",
                        help="Album: N images → 1 L1 Page (single-shot, no two-phase; PRIN-ING-13)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--title", required=True, help="album theme (becomes the L1 title)")
    sp.add_argument("--files", required=True,
                    help="comma-separated absolute image paths")
    sp.add_argument("--node-path", default="", help="logical partition path (album lives under nodes/page/<node-path>/)")
    sp.add_argument("--layout", default="table", choices=["table", "list"],
                    help="body layout: table (default) or list")
    sp.add_argument("--vision", action="store_true",
                    help="mark vision intent (per-photo captions); SOP should ask user first")
    sp.add_argument("--captions", default="",
                    help='JSON object {filename: description} (optional)')
    sp.add_argument("--digest", default="")
    sp.add_argument("--author", default="agent")
    sp.set_defaults(func="ingest_album")

    sp = sub.add_parser("query", help="three-layer retrieval (L1 locate + L2/L3 hints)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--core", default="", help="comma-separated core keywords")
    sp.add_argument("--expansion", default="", help="comma-separated expansion keywords")
    sp.add_argument("--top-k", type=int, default=None)
    sp.add_argument("--neighbors", action="store_true", help="include 1-hop relation neighbors")
    sp.add_argument("--include-inactive", action="store_true")
    sp.set_defaults(func="query")

    sp = sub.add_parser("read", help="read a single node full body (L1 applies patches)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uid", required=True)
    sp.set_defaults(func="read")

    sp = sub.add_parser("nodes", help="DB node metadata query (read-only)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--layer", default=None, choices=["Page", "List", "Report"])
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
    sp = sub.add_parser("list", help="L2 Node_List create/show")
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
    sp.set_defaults(func="list_cmd")

    sp = sub.add_parser("report", help="L3 Node_Report create/show (evidence chain required)")
    rpsub = sp.add_subparsers(dest="report_action", required=True)
    rc = rpsub.add_parser("create")
    rc.add_argument("--wiki", required=True)
    rc.add_argument("--title", required=True)
    rc.add_argument("--body", required=True, help="report body (markdown)")
    rc.add_argument("--references", required=True, help="comma-separated L1/L2 evidence UIDs")
    rc.add_argument("--node-path", default="")
    rs = rpsub.add_parser("show")
    rs.add_argument("--wiki", required=True)
    rs.add_argument("--uid", required=True)
    sp.set_defaults(func="report_cmd")

    # ---- M5: doctor / delete-node / rebuild ----
    for name in [
        "doctor", "doctor-fields", "doctor-files", "doctor-relations",
        "doctor-l1-immutable", "doctor-report-evidence", "doctor-idf", "doctor-all",
    ]:
        spx = sub.add_parser(name, help=f"{name} health check (read-only by default)")
        spx.add_argument("--wiki", required=True)
        spx.add_argument("--fix", action="store_true", help="apply mechanical fixes")
        spx.set_defaults(func="doctor", doctor_kind=name)

    sp = sub.add_parser("delete-node", help="physically delete a node (checks references first)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uid", required=True)
    sp.add_argument("--force", action="store_true", help="proceed despite L2/L3 references")
    sp.set_defaults(func="delete_node")

    sp = sub.add_parser("rebuild", help="rebuild derived layers (never touches L1)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--granularity", default="keep-l1", choices=["keep-l1", "keep-l1-l2", "full"])
    sp.set_defaults(func="rebuild")

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

    # ---- M7: software lifecycle (only uninstall lives here; install = pip) ----
    sp = sub.add_parser("uninstall", help="dry-run by default; --execute to actually uninstall xu-wiki")
    sp.add_argument("--execute", action="store_true",
                    help="actually perform the uninstall (default is dry-run)")
    sp.add_argument("--purge-wikis", action="store_true",
                    help="also wipe all registered wiki data (default: keep wiki data intact)")
    sp.add_argument("--purge-config", action="store_true",
                    help="also remove the global config dir (default: keep ~/.xu/)")
    sp.add_argument("--keep-pip", action="store_true",
                    help="do NOT call pip uninstall (test / dev escape hatch)")
    sp.set_defaults(func="uninstall")

    # ---- M8: post-install health check (坑 6 fix) ----
    sub.add_parser("selfcheck",
                   help="verify xu-wiki install (CLI / Python / skills / ~/.xu/ / extras); "
                        "agent-callable, returns 4-key JSON").set_defaults(func="selfcheck")

    return p


def _dispatch(args) -> dict:
    func = args.func
    if func in ("skills_path", "skills_list", "skills_default"):
        from .commands.skills import cmd_skills
        return cmd_skills(args)
    if func == "create":
        from .commands.create import cmd_create
        return cmd_create(args)
    if func == "wikis":
        from .utils.config import load_registry
        from .utils.response import success
        return success(load_registry().get("wikis", {}), "registered wikis")
    if func == "ingest_file":
        from .commands.ingest import cmd_ingest_file
        return cmd_ingest_file(args)
    if func == "ingest_commit":
        from .commands.ingest import cmd_ingest_commit
        return cmd_ingest_commit(args)
    if func == "ingest_album":
        from .commands.album import cmd_ingest_album
        return cmd_ingest_album(args)
    if func == "query":
        from .commands.query import cmd_query
        return cmd_query(args)
    if func == "read":
        from .commands.query import cmd_read
        return cmd_read(args)
    if func == "nodes":
        from .commands.query import cmd_nodes
        return cmd_nodes(args)
    if func == "query_relation":
        from .commands.relations import cmd_query_relation
        return cmd_query_relation(args)
    if func == "list_cmd":
        from .commands.layers import cmd_list
        return cmd_list(args)
    if func == "report_cmd":
        from .commands.layers import cmd_report
        return cmd_report(args)
    if func == "doctor":
        from .commands.doctor import cmd_doctor
        return cmd_doctor(args)
    if func == "delete_node":
        from .commands.doctor import cmd_delete_node
        return cmd_delete_node(args)
    if func == "rebuild":
        from .commands.doctor import cmd_rebuild
        return cmd_rebuild(args)
    if func == "alias_set":
        from .commands.config import cmd_alias_set
        return cmd_alias_set(args)
    if func == "alias_unset":
        from .commands.config import cmd_alias_unset
        return cmd_alias_unset(args)
    if func == "alias_show":
        from .commands.config import cmd_alias_show
        return cmd_alias_show(args)
    if func == "register":
        from .commands.config import cmd_register
        return cmd_register(args)
    if func == "unregister":
        from .commands.config import cmd_unregister
        return cmd_unregister(args)
    if func == "config_set_mineru_key":
        from .commands.config import cmd_config_set_mineru_key
        return cmd_config_set_mineru_key(args)
    if func == "config_show":
        from .commands.config import cmd_config_show
        return cmd_config_show(args)
    if func == "config_path":
        from .commands.config import cmd_config_path
        return cmd_config_path(args)
    if func == "uninstall":
        from .commands.uninstall import cmd_uninstall
        return cmd_uninstall(args)
    if func == "selfcheck":
        from .commands.selfcheck import cmd_selfcheck
        return cmd_selfcheck(args)
    return error(f"unknown command function: {func}", "UnknownCommand")


def main(argv: list[str] | None = None) -> int:
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
            append_jsonl(GLOBAL_AUDIT_LOG, record)
        except Exception:
            pass
        return emit(response)
    start = time.time()
    try:
        response = _dispatch(args)
    except Exception as e:  # never crash without a 4-key response
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
        append_jsonl(audit_path, record)
    except Exception:
        pass
    return emit(response)


if __name__ == "__main__":
    sys.exit(main())
