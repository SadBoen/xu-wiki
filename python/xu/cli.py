"""xu CLI entrypoint — argparse dispatcher calling Rust _core.

Every command returns 4-key JSON. Install: pip install xu-wiki (wheel).
"""
import argparse, json, sys
from xu import __version__

def build_parser():
    p = argparse.ArgumentParser(prog="xu", description="Relation-driven wiki engine")
    p.add_argument("--version", action="version", version=f"xu-wiki {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("create", help="create a new wiki")
    sp.add_argument("--name")
    sp.add_argument("--path", required=True)
    sp.add_argument("--alias")
    sp.set_defaults(func="create")

    sp = sub.add_parser("ingest-file", help="Phase 1: parse file to pending")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--file", required=True)
    sp.set_defaults(func="ingest_file")

    sp = sub.add_parser("ingest-context", help="Phase 1->2 bridge: raws_tree + related_nodes")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--keywords", required=True)
    sp.set_defaults(func="ingest_context")

    sp = sub.add_parser("ingest-commit", help="Phase 2: commit pending to L1 page(s)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--pending")
    sp.add_argument("--title")
    sp.add_argument("--content-type", default="article")
    sp.add_argument("--raw-path", default="")
    sp.add_argument("--author", default="agent")
    sp.add_argument("--relations", default="")
    sp.add_argument("--native", default="")
    sp.add_argument("--source", default="")
    sp.set_defaults(func="ingest_commit")

    sp = sub.add_parser("query", help="search wiki")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--core", default="")
    sp.add_argument("--expansion", default="")
    sp.add_argument("--top-k", type=int, default=50)
    sp.set_defaults(func="query")

    sp = sub.add_parser("expand", help="pull full body + relations for UIDs")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uids", required=True)
    sp.set_defaults(func="expand")

    sp = sub.add_parser("selfcheck", help="health check")
    sp.set_defaults(func="selfcheck")

    sp = sub.add_parser("doctor", help="filesystem integrity check")
    sp.add_argument("--wiki", required=True)
    sp.set_defaults(func="doctor")

    sp = sub.add_parser("uninstall", help="uninstall xu-wiki (dry-run default)")
    sp.add_argument("--execute", action="store_true")
    sp.add_argument("--preserve-config", action="store_true")
    sp.add_argument("--keep-pip", action="store_true")
    sp.set_defaults(func="uninstall")

    return p

def main():
    p = build_parser()
    args = p.parse_args()
    func = args.func

    try:
        from xu._core import (py_create, py_selfcheck, py_doctor,
                               py_uninstall_plan, py_uninstall_execute,
                               py_ingest_commit, py_query, py_expand, py_ingest_context)
        _core_available = True
    except ImportError:
        _core_available = False

    result = None

    if func == "create" and _core_available:
        result = json.loads(py_create(args.name or "", args.path, args.alias))
    elif func == "selfcheck" and _core_available:
        result = json.loads(py_selfcheck())
    elif func == "doctor" and _core_available:
        result = json.loads(py_doctor(args.wiki))
    elif func == "uninstall" and _core_available:
        if args.execute:
            result = json.loads(py_uninstall_execute(args.preserve_config, args.keep_pip))
        else:
            result = json.loads(py_uninstall_plan(args.preserve_config, args.keep_pip))
    elif func == "ingest_commit" and _core_available and args.pending:
        result = json.loads(py_ingest_commit(
            args.wiki, args.pending, args.title or "",
            args.content_type, args.raw_path, args.author, args.relations))
    elif func == "query" and _core_available:
        result = json.loads(py_query(args.wiki, args.core, args.expansion, args.top_k))
    elif func == "expand" and _core_available:
        result = json.loads(py_expand(args.wiki, args.uids))
    elif func == "ingest_context" and _core_available:
        result = json.loads(py_ingest_context(args.wiki, args.keywords))
    else:
        # Fallback: use Python command modules
        result = _dispatch_python(args)

    if result:
        sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
        sys.stdout.write("\n")
        sys.exit(0 if result.get("status") in ("success", "warning") else 1)

def _dispatch_python(args):
    """Fallback dispatch to Python command modules."""
    func = args.func
    if func == "create":
        from xu.commands.create import cmd_create; return cmd_create(args)
    if func == "ingest_file":
        from xu.commands.ingest import cmd_ingest_file; return cmd_ingest_file(args)
    if func == "ingest_commit":
        from xu.commands.ingest import cmd_ingest_commit; return cmd_ingest_commit(args)
    if func == "ingest_context":
        from xu.commands.ingest import cmd_ingest_context; return cmd_ingest_context(args)
    if func == "query":
        from xu.commands.query import cmd_query; return cmd_query(args)
    if func == "expand":
        from xu.commands.query import cmd_expand; return cmd_expand(args)
    if func == "selfcheck":
        from xu.commands.selfcheck import cmd_selfcheck; return cmd_selfcheck(args)
    if func == "doctor":
        from xu.commands.doctor import cmd_doctor; return cmd_doctor(args)
    if func == "uninstall":
        from xu.commands.uninstall import cmd_uninstall; return cmd_uninstall(args)
    return {"status": "error", "data": {}, "message": f"unknown command: {func}", "hints": []}
