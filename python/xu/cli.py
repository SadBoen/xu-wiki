"""xu CLI — argparse dispatcher -> Rust _core."""
import argparse, json, sys, os, tempfile, time
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

    sp = sub.add_parser("update", help="update node body/title/relations")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uid", required=True)
    sp.add_argument("--title")
    sp.add_argument("--body")
    sp.add_argument("--relations", default="")
    sp.add_argument("--author", default="agent")
    sp.set_defaults(func="update")

    sp = sub.add_parser("deactivate", help="soft-delete a node (set active=0)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uid", required=True)
    sp.set_defaults(func="deactivate")

    sp = sub.add_parser("verify", help="integrity check on a node")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uid", required=True)
    sp.set_defaults(func="verify")

    sp = sub.add_parser("list-create", help="create L2 List (aggregation)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--title", required=True)
    sp.add_argument("--members", required=True)
    sp.add_argument("--dimension", default="")
    sp.set_defaults(func="list_create")

    sp = sub.add_parser("list-extend", help="add members to a List")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uid", required=True)
    sp.add_argument("--members", required=True)
    sp.set_defaults(func="list_extend")

    sp = sub.add_parser("report-create", help="create L3 Report (reasoning)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--title", required=True)
    sp.add_argument("--body", required=True)
    sp.add_argument("--evidence", default="")
    sp.add_argument("--dimension", default="")
    sp.set_defaults(func="report_create")
    sp = sub.add_parser("entity-create", help="create Entity node (concept)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--title", required=True)
    sp.add_argument("--body", default="")
    sp.add_argument("--source-page", default="")
    sp.add_argument("--attrs", default="")
    sp.add_argument("--dimension", default="")
    sp.set_defaults(func="entity_create")

    sp = sub.add_parser("ingest-commit", help="Phase 2: commit to L1")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--pending")
    sp.add_argument("--title")
    sp.add_argument("--content-type", default="article")
    sp.add_argument("--raw-path", default="")
    sp.add_argument("--author", default="agent")
    sp.add_argument("--relations", default="")
    sp.set_defaults(func="ingest_commit")

    sp = sub.add_parser("ingest-album", help="single-shot image album -> L1 gallery page")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--title", required=True)
    sp.add_argument("--files", nargs='+', required=True)
    sp.add_argument("--raw-path", default="")
    sp.add_argument("--layout", default="table", choices=["table", "list"])
    sp.add_argument("--captions", default="")
    sp.add_argument("--author", default="agent")
    sp.set_defaults(func="ingest_album")

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

    # `xu skills` — agent-facing skill bundle management.
    # The skill ships inside the wheel as package data; the CLI does not
    # auto-deploy it (we do not know which agent runtime the user is on).
    # `xu skills install` is the one-liner that copies the bundle into the
    # well-known agent skill directory.
    sp_skills = sub.add_parser("skills", help="manage the agent skill bundle")
    sub_skills = sp_skills.add_subparsers(dest="skills_command", required=True)

    sp_skills_list = sub_skills.add_parser("list", help="list skill files bundled in the wheel")
    sp_skills_list.set_defaults(func="skills_list")

    sp_skills_path = sub_skills.add_parser("path", help="print the source path of the bundled skill (on disk inside the wheel)")
    sp_skills_path.set_defaults(func="skills_path")

    sp_skills_install = sub_skills.add_parser("install", help="deploy the skill bundle to the agent's skill directory")
    sp_skills_install.add_argument(
        "--target",
        default=str(Path.home() / ".hermes" / "skills" / "xu-wiki"),
        help="target skill directory (default: ~/.hermes/skills/xu-wiki)",
    )
    sp_skills_install.add_argument(
        "--force", action="store_true",
        help="overwrite existing files in the target directory",
    )
    sp_skills_install.set_defaults(func="skills_install")

    return p

def main():
    args = build_parser().parse_args()
    result = dispatch(args)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    sys.exit(0 if result.get("status") in ("success", "warning") else 1)

def dispatch(args):
    f = args.func

    # Phase 1: ingest-file 鈥?Python parser chain (third-party: MinerU, markitdown, Pillow)
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
            py_update, py_deactivate, py_verify,
            py_list_create, py_list_extend, py_report_create,
            py_entity_create,
        )
    except ImportError:
        return {"status": "error", "message": "_core not built. Install wheel or run maturin develop.", "hints": []}

    if f == "create":
        r = json.loads(py_create(args.name or "", args.path, getattr(args, 'alias', None)))
        if r["status"] == "success":
            _register_wiki(args.name, args.path, getattr(args, 'alias', None))
        return r
    if f == "selfcheck":
        return json.loads(py_selfcheck())
    if f == "doctor":
        wp = _resolve_or_err(args.wiki)
        return wp if isinstance(wp, dict) else json.loads(py_doctor(wp))
    if f == "uninstall":
        if args.execute:
            return json.loads(py_uninstall_execute(args.preserve_config, args.keep_pip))
        return json.loads(py_uninstall_plan(args.preserve_config, args.keep_pip))
    if f == "ingest_commit":
        wp = _resolve_or_err(args.wiki)
        if isinstance(wp, dict):
            return wp
        pending = getattr(args, 'pending', '') or ''
        # If pending is a file path (from ingest-file), read and convert to text
        pending_text = _read_pending(pending)
        if pending_text is None:
            return {"status": "error", "message": f"cannot read pending: {pending}", "hints": []}
        return json.loads(py_ingest_commit(
            wp, pending_text,
            getattr(args, 'title', '') or '',
            getattr(args, 'content_type', 'article') or 'article',
            getattr(args, 'raw_path', '') or '',
            getattr(args, 'author', 'agent') or 'agent',
            getattr(args, 'relations', '') or '',
        ))
    if f == "ingest_album":
        wp = _resolve_or_err(args.wiki)
        if isinstance(wp, dict):
            return wp
        return _handle_ingest_album(
            wiki_path=wp,
            title=args.title,
            files=args.files,
            raw_path=getattr(args, 'raw_path', '') or '',
            layout=getattr(args, 'layout', 'table') or 'table',
            captions_json=getattr(args, 'captions', '') or '',
            author=getattr(args, 'author', 'agent') or 'agent',
            py_ingest_commit=py_ingest_commit,
        )
    if f == "query":
        wp = _resolve_or_err(args.wiki)
        if isinstance(wp, dict):
            return wp
        return json.loads(py_query(wp, args.core, args.expansion, args.top_k))
    if f == "expand":
        wp = _resolve_or_err(args.wiki)
        if isinstance(wp, dict):
            return wp
        return json.loads(py_expand(wp, args.uids))
    if f == "ingest_context":
        wp = _resolve_or_err(args.wiki)
        if isinstance(wp, dict):
            return wp
        return json.loads(py_ingest_context(wp, args.keywords))
    if f == "update":
        wp = _resolve_or_err(args.wiki)
        if isinstance(wp, dict):
            return wp
        return json.loads(py_update(
            wp,
            args.uid,
            getattr(args, 'title', None) or None,
            getattr(args, 'body', None) or None,
            getattr(args, 'relations', '') or '',
            getattr(args, 'author', 'agent') or 'agent',
        ))
    if f == "deactivate":
        wp = _resolve_or_err(args.wiki)
        if isinstance(wp, dict):
            return wp
        return json.loads(py_deactivate(wp, args.uid))
    if f == "verify":
        wp = _resolve_or_err(args.wiki)
        if isinstance(wp, dict):
            return wp
        return json.loads(py_verify(wp, args.uid))
    if f == "list_create":
        wp = _resolve_or_err(args.wiki)
        if isinstance(wp, dict):
            return wp
        return json.loads(py_list_create(wp, args.title, args.members, getattr(args, 'dimension', '') or ''))
    if f == "list_extend":
        wp = _resolve_or_err(args.wiki)
        if isinstance(wp, dict):
            return wp
        return json.loads(py_list_extend(wp, args.uid, args.members))
    if f == "report_create":
        wp = _resolve_or_err(args.wiki)
        if isinstance(wp, dict):
            return wp
        return json.loads(py_report_create(
            wp, args.title, args.body,
            getattr(args, 'evidence', '') or '',
            getattr(args, 'dimension', '') or '',
        ))
    if f == "entity_create":
        wp = _resolve_or_err(args.wiki)
        if isinstance(wp, dict):
            return wp
        return json.loads(py_entity_create(
            wp, args.title,
            getattr(args, 'body', '') or '',
            getattr(args, 'source_page', '') or '',
            getattr(args, 'attrs', '') or '',
            getattr(args, 'dimension', '') or '',
        ))

    # ---- skill bundle management (no Rust required) ----
    if f in ("skills_list", "skills_path", "skills_install"):
        return _handle_skills(args)

    return {"status": "error", "message": f"unknown command: {f}", "hints": []}


def _read_pending(pending: str):
    """Convert pending file path (from ingest-file) to pending_text format.

    If `pending` is a path to a JSON file written by ingest-file,
    read content_markdown + source_hash and return a `<!-- xu-pending ... -->`
    header + body.  If `pending` already starts with `<!-- xu-pending`,
    return as-is.
    """
    if pending.startswith("<!-- xu-pending"):
        return pending
    pp = Path(pending)
    if not pp.is_file():
        return pending  # assume it's already content text
    try:
        data = json.loads(pp.read_text(encoding="utf-8"))
        body = data.get("content_markdown", "")
        source_hash = data.get("source_hash", "")
        return f"<!-- xu-pending source_hash={source_hash} -->\n{body}"
    except (json.JSONDecodeError, OSError):
        return pending


def _resolve_or_err(name: str):
    """Resolve wiki name/alias -> absolute path. Returns dict on error."""
    from xu.utils.config import registry_find
    found = registry_find(name)
    if found is None:
        return {"status": "error", "message": f"wiki not found: {name}", "hints": []}
    _name, entry = found
    return str(entry["path"])


def _handle_ingest_album(*, wiki_path, title, files, raw_path, layout, captions_json, author, py_ingest_commit):
    """Build a single L1 gallery page from multiple image files."""
    import hashlib, yaml as _yaml
    from xu.parsers.image_meta import read_image_meta

    # --- validate files ---
    resolved = []
    for p in files:
        fp = Path(p).expanduser()
        if not fp.is_absolute():
            return {"status": "error", "message": f"absolute path required: {p}", "hints": []}
        if not fp.is_file():
            return {"status": "error", "message": f"file not found: {p}", "hints": []}
        resolved.append(fp)

    # --- captions ---
    captions: dict = {}
    if captions_json.strip():
        try:
            captions = json.loads(captions_json)
            if not isinstance(captions, dict):
                captions = {}
        except json.JSONDecodeError:
            return {"status": "error", "message": "captions must be valid JSON object", "hints": []}

    # --- collect metadata per image ---
    items = []
    hashes = []
    for fp in resolved:
        meta = read_image_meta(str(fp))
        entry = {
            "filename": fp.name,
            "size_bytes": fp.stat().st_size,
            "width": meta.get("width"),
            "height": meta.get("height"),
            "datetime": meta.get("datetime"),
            "make": meta.get("make"),
            "model": meta.get("model"),
        }
        cap = captions.get(fp.name, "").strip()
        if cap:
            entry["caption"] = cap
        entry = {k: v for k, v in entry.items() if v is not None}
        items.append(entry)
        hashes.append(hashlib.sha256(fp.read_bytes()).hexdigest())

    # --- source_hash: aggregate ---
    source_hash = hashlib.sha256("".join(hashes).encode()).hexdigest()

    # --- build body ---
    body = _yaml.dump(items, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # --- pending text: must match parse_pending_header format ---
    pending_text = f"<!-- xu-pending source_hash={source_hash} parser=album -->\n{body}"

    # --- delegate to ingest-commit (pass text directly, not file path) ---
    result = json.loads(py_ingest_commit(
        wiki_path,
        pending_text,  # pending 鈥?raw text with xu-pending header
        title,         # title
        "gallery",     # content_type
        raw_path,      # raw_path
        author,        # author
        "",            # relations
    ))

    return result


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


def _handle_skills(args):
    """Dispatch the three `xu skills {list,path,install}` subcommands.

    The skill bundle ships as package data alongside the wheel
    (see `xu/skills/__init__.py`). `xu skills install` is the official
    one-liner that copies SKILL.md + references/ into the agent's
    skill directory (default: ``~/.hermes/skills/xu-wiki/``).
    """
    from xu.skills import (
        SKILL_NAME, SKILL_SRC_DIR, ALL_SKILL_FILES,
    )

    if args.func == "skills_path":
        return {
            "status": "success",
            "data": {
                "source_dir": str(SKILL_SRC_DIR),
                "skill_name": SKILL_NAME,
                "files": list(ALL_SKILL_FILES),
            },
            "message": f"skill bundle is at {SKILL_SRC_DIR}",
            "hints": [
                "next: xu skills install",
                f"  (or copy {SKILL_SRC_DIR}/SKILL.md to your agent's skill dir)",
            ],
        }

    if args.func == "skills_list":
        return {
            "status": "success",
            "data": {
                "skill_name": SKILL_NAME,
                "source_dir": str(SKILL_SRC_DIR),
                "files": list(ALL_SKILL_FILES),
            },
            "message": f"{len(ALL_SKILL_FILES)} file(s) bundled",
            "hints": ["next: xu skills install"],
        }

    if args.func == "skills_install":
        target = Path(args.target).expanduser()
        if not target.is_absolute():
            return {
                "status": "error",
                "message": f"--target must be absolute: {target}",
                "hints": ["omit --target to use default ~/.hermes/skills/xu-wiki/"],
            }

        target.mkdir(parents=True, exist_ok=True)

        # Sanity: source files must exist on disk (wheel has them as
        # package_data — importlib.resources is the robust check, but
        # the editable wheel always extracts them to disk).
        if not (SKILL_SRC_DIR / "SKILL.md").is_file():
            return {
                "status": "error",
                "message": f"SKILL.md not found in wheel package data ({SKILL_SRC_DIR})",
                "hints": [
                    "this wheel may be corrupted; reinstall with: pipx reinstall xu-wiki",
                ],
            }

        copied, skipped = [], []
        for rel in ALL_SKILL_FILES:
            src = SKILL_SRC_DIR / rel
            dst = target / rel
            if not src.is_file():
                # Missing optional reference (e.g. error-catalog.md) —
                # skip silently rather than fail the install.
                continue
            if dst.exists() and not args.force:
                skipped.append(rel)
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
            copied.append(rel)

        # Drop a tiny installation marker so the agent / user can see
        # when the bundle was last refreshed.
        marker = target / ".xu-skill-installed"
        marker.write_text(
            f"installed_at={int(time.time())}\nsource={SKILL_SRC_DIR}\n"
            f"files={','.join(copied)}\n",
            encoding="utf-8",
        )

        return {
            "status": "success",
            "data": {
                "target": str(target),
                "copied": copied,
                "skipped": skipped,
                "marker": str(marker),
            },
            "message": f"installed {len(copied)} file(s) to {target}"
                       + (f", skipped {len(skipped)} (use --force to overwrite)"
                          if skipped else ""),
            "hints": [
                "restart your agent so it picks up the new skill",
                "verify: ls -la " + str(target),
            ],
        }

    return {"status": "error", "message": f"unknown skills subcommand: {args.func}", "hints": []}
