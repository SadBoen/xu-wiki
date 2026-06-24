"""xu CLI — argparse dispatcher -> Rust _core."""
import argparse
import json
import sys
from xu import __version__

def build_parser():
    p = argparse.ArgumentParser(prog="xu", description="Relation-driven wiki engine")
    p.add_argument("--version", action="version", version=f"xu-wiki {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("create", help="create a new wiki")
    sp.add_argument("--name"); sp.add_argument("--path", required=True); sp.add_argument("--alias")
    sp.set_defaults(func="create")

    sp = sub.add_parser("ingest-file", help="Phase 1: parse file to pending")
    sp.add_argument("--wiki", required=True); sp.add_argument("--file", required=True)
    sp.set_defaults(func="ingest_file")

    sp = sub.add_parser("ingest-context", help="Phase 1->2 bridge")
    sp.add_argument("--wiki", required=True); sp.add_argument("--keywords", required=True)
    sp.set_defaults(func="ingest_context")

    sp = sub.add_parser("ingest-commit", help="Phase 2: commit to L1")
    sp.add_argument("--wiki", required=True); sp.add_argument("--pending"); sp.add_argument("--title")
    sp.add_argument("--content-type", default="article"); sp.add_argument("--raw-path", default="")
    sp.add_argument("--author", default="agent"); sp.add_argument("--relations", default="")
    sp.add_argument("--native", default=""); sp.add_argument("--source", default="")
    sp.set_defaults(func="ingest_commit")

    sp = sub.add_parser("query", help="search wiki")
    sp.add_argument("--wiki", required=True); sp.add_argument("--core", default="")
    sp.add_argument("--expansion", default=""); sp.add_argument("--top-k", type=int, default=50)
    sp.set_defaults(func="query")

    sp = sub.add_parser("expand", help="pull body+relations for UIDs")
    sp.add_argument("--wiki", required=True); sp.add_argument("--uids", required=True)
    sp.set_defaults(func="expand")

    sub.add_parser("selfcheck", help="health check").set_defaults(func="selfcheck")
    sp = sub.add_parser("doctor", help="filesystem integrity"); sp.add_argument("--wiki", required=True)
    sp.set_defaults(func="doctor")

    sp = sub.add_parser("uninstall", help="uninstall (dry-run default)")
    sp.add_argument("--execute", action="store_true"); sp.add_argument("--preserve-config", action="store_true")
    sp.add_argument("--keep-pip", action="store_true")
    sp.set_defaults(func="uninstall")

    return p

def main():
    args = build_parser().parse_args()
    try:
        from xu._core import (py_create, py_selfcheck, py_doctor,
                               py_uninstall_plan, py_uninstall_execute,
                               py_ingest_commit, py_query, py_expand, py_ingest_context)
        dispatch = {
            "create": lambda: json.loads(py_create(args.name or "", args.path, args.alias)),
            "selfcheck": lambda: json.loads(py_selfcheck()),
            "doctor": lambda: json.loads(py_doctor(args.wiki)),
            "uninstall": lambda: json.loads(py_uninstall_execute(args.preserve_config, args.keep_pip) if args.execute else py_uninstall_plan(args.preserve_config, args.keep_pip)),
            "ingest_commit": lambda: json.loads(py_ingest_commit(args.wiki, args.pending or "", args.title or "", args.content_type, args.raw_path, args.author, args.relations)),
            "query": lambda: json.loads(py_query(args.wiki, args.core, args.expansion, args.top_k)),
            "expand": lambda: json.loads(py_expand(args.wiki, args.uids)),
            "ingest_context": lambda: json.loads(py_ingest_context(args.wiki, args.keywords)),
        }
        result = dispatch.get(args.func, lambda: None)()
    except ImportError:
        result = {"status": "error", "message": "_core not built. Install xu-wiki wheel or run maturin develop.", "hints": []}

    if result is None:
        result = {"status": "error", "message": f"unknown command: {args.func}", "hints": []}

    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    sys.exit(0 if result.get("status") in ("success", "warning") else 1)
