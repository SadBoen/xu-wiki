"""xu CLI — argparse dispatcher -> Rust _core."""
import argparse, json, sys, os, tempfile
from pathlib import Path
from xu import __version__

def build_parser():
    p = argparse.ArgumentParser(prog="xu", description="Relation-driven wiki engine")
    p.add_argument("--version", action="version", version=f"xu-wiki {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("create", help="create a wiki")
    sp.add_argument("--name")
    sp.add_argument("--path", required=True)
    sp.add_argument("--alias")
    sp.set_defaults(func="create")

    sp = sub.add_parser("ingest-file", help="Phase 1: parse file to pending")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--file", required=True)
    sp.set_defaults(func="ingest_file")

    sp = sub.add_parser("ingest-context", help="Phase 1->2 bridge")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--keywords", required=True)
    sp.set_defaults(func="ingest_context")

    sp = sub.add_parser("ingest-commit", help="Phase 2: commit to L1")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--pending")
    sp.add_argument("--title")
    sp.add_argument("--content-type", default="article")
    sp.add_argument("--raw-path", default="")
    sp.add_argument("--author", default="agent")
    sp.add_argument("--relations", default="")
    sp.set_defaults(func="ingest_commit")

    sp = sub.add_parser("query", help="search wiki")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--core", default="")
    sp.add_argument("--expansion", default="")
    sp.add_argument("--top-k", type=int, default=50)
    sp.set_defaults(func="query")

    sp = sub.add_parser("expand", help="pull body+relations")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uids", required=True)
    sp.set_defaults(func="expand")

    sp = sub.add_parser("selfcheck", help="health check")
    sp.set_defaults(func="selfcheck")

    sp = sub.add_parser("doctor", help="filesystem integrity")
    sp.add_argument("--wiki", required=True)
    sp.set_defaults(func="doctor")

    sp = sub.add_parser("uninstall", help="uninstall (dry-run default)")
    sp.add_argument("--execute", action="store_true")
    sp.add_argument("--preserve-config", action="store_true")
    sp.add_argument("--keep-pip", action="store_true")
    sp.set_defaults(func="uninstall")

    return p

def main():
    args = build_parser().parse_args()
    result = dispatch(args)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    sys.exit(0 if result.get("status") in ("success", "warning") else 1)

def dispatch(args):
    f = args.func

    # Phase 1: ingest-file — Python parser chain (third-party: MinerU, markitdown, Pillow)
    if f == "ingest_file":
        from xu.parsers.registry import parse_file
        src = Path(args.file).expanduser()
        if not src.is_absolute():
            return {"status": "error", "message": "absolute path required", "hints": []}
        if not src.is_file():
            return {"status": "error", "message": f"file not found: {src}", "hints": []}
        import hashlib
        source_hash = hashlib.sha256(src.read_bytes()).hexdigest()
        parsed = parse_file(str(src))
        if not parsed.ok:
            return {"status": "error", "message": f"parse failed: {parsed.skipped_reason}", "hints": []}
        tmpf = Path(tempfile.gettempdir()) / f"xu-pending-{os.urandom(4).hex()}.json"
        tmpf.write_text(json.dumps({
            "content_markdown": parsed.text,
            "metadata": {"parser": parsed.parser, "source": str(src)},
            "source_hash": source_hash
        }), encoding="utf-8")
        return {
            "status": "success",
            "data": {"pending": str(tmpf), "parser": parsed.parser, "char_count": len(parsed.text)},
            "message": f"parsed via {parsed.parser}",
            "hints": ["next: xu ingest-context --keywords '...'", "then: xu ingest-commit --pending ..."]
        }

    # All other commands: Rust _core
    try:
        from xu._core import (
            py_create, py_selfcheck, py_doctor,
            py_uninstall_plan, py_uninstall_execute,
            py_ingest_commit, py_query, py_expand, py_ingest_context,
        )
    except ImportError:
        return {"status": "error", "message": "_core not built. Install wheel or run maturin develop.", "hints": []}

    if f == "create":
        r = json.loads(py_create(args.name or "", args.path, args.alias))
        if r["status"] == "success":
            _register_wiki(args.name, args.path, args.alias)
        return r
    if f == "selfcheck":
        return json.loads(py_selfcheck())
    if f == "doctor":
        return json.loads(py_doctor(args.wiki))
    if f == "uninstall":
        if args.execute:
            return json.loads(py_uninstall_execute(args.preserve_config, args.keep_pip))
        return json.loads(py_uninstall_plan(args.preserve_config, args.keep_pip))
    if f == "ingest_commit":
        return json.loads(py_ingest_commit(
            args.wiki, args.pending or "", args.title or "",
            args.content_type, args.raw_path, args.author, args.relations,
        ))
    if f == "query":
        return json.loads(py_query(args.wiki, args.core, args.expansion, args.top_k))
    if f == "expand":
        return json.loads(py_expand(args.wiki, args.uids))
    if f == "ingest_context":
        return json.loads(py_ingest_context(args.wiki, args.keywords))

    return {"status": "error", "message": f"unknown command: {f}", "hints": []}


def _register_wiki(name, path, alias):
    """Write wiki to global registry (~/.xu-wiki/config.yaml)."""
    import time
    from xu.utils.config import load_registry, save_registry
    reg = load_registry()
    reg.setdefault("wikis", {})
    reg["wikis"][name] = {
        "path": path,
        "alias": alias,
        "created_at": int(time.time()),
    }
    save_registry(reg)
