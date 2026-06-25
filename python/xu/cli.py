"""xu CLI — argparse dispatcher -> Rust _core. No Python fallback."""
import argparse, json, sys
from pathlib import Path
from xu import __version__

def build_parser():
    p = argparse.ArgumentParser(prog="xu", description="Relation-driven wiki engine")
    p.add_argument("--version", action="version", version=f"xu-wiki {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    # create
    sp = sub.add_parser("create", help="create a wiki")
    sp.add_argument("--name")
    sp.add_argument("--path", required=True)
    sp.add_argument("--alias")
    sp.set_defaults(func="create")

    # alias
    sp = sub.add_parser("alias-set", help="set wiki alias")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--alias", required=True)
    sp.set_defaults(func="alias_set")

    sp = sub.add_parser("alias-unset", help="unset wiki alias")
    sp.add_argument("--wiki", required=True)
    sp.set_defaults(func="alias_unset")

    sp = sub.add_parser("alias-show", help="show wiki alias")
    sp.add_argument("--wiki", required=True)
    sp.set_defaults(func="alias_show")

    # register
    sp = sub.add_parser("register", help="register a wiki in global registry")
    sp.add_argument("--name", required=True)
    sp.add_argument("--path", required=True)
    sp.add_argument("--alias")
    sp.set_defaults(func="register")

    sp = sub.add_parser("unregister", help="unregister a wiki")
    sp.add_argument("--name", required=True)
    sp.set_defaults(func="unregister")

    # config
    sp = sub.add_parser("config", help="show global config")
    sp.set_defaults(func="config_show")

    sp = sub.add_parser("config-path", help="print global config path")
    sp.set_defaults(func="config_path")

    sp = sub.add_parser("config-set-mineru-key", help="set mineru API key from MINERU_API_KEY env")
    sp.set_defaults(func="config_set_mineru_key")

    # wikis
    sp = sub.add_parser("wikis", help="list all registered wikis")
    sp.set_defaults(func="wikis")

    # selfcheck / doctor
    sp = sub.add_parser("selfcheck", help="health check")
    sp.set_defaults(func="selfcheck")

    sp = sub.add_parser("doctor", help="filesystem integrity check")
    sp.add_argument("--wiki", required=True)
    sp.set_defaults(func="doctor")

    # ingest
    sp = sub.add_parser("ingest-commit", help="commit page to L1")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--pending", default="")
    sp.add_argument("--title", default="")
    sp.add_argument("--content-type", default="article")
    sp.add_argument("--raw-path", default="")
    sp.add_argument("--author", default="agent")
    sp.add_argument("--relations", default="")
    sp.set_defaults(func="ingest_commit")

    sp = sub.add_parser("ingest-context", help="build context from keywords")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--keywords", required=True)
    sp.set_defaults(func="ingest_context")

    # query
    sp = sub.add_parser("query", help="search wiki")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--core", default="")
    sp.add_argument("--expansion", default="")
    sp.add_argument("--top-k", type=int, default=50)
    sp.set_defaults(func="query")

    sp = sub.add_parser("expand", help="pull body+relations by uid(s)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uids", required=True)
    sp.set_defaults(func="expand")

    # update/deactivate/verify
    sp = sub.add_parser("update", help="update node body/title/relations")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uid", required=True)
    sp.add_argument("--title")
    sp.add_argument("--body")
    sp.add_argument("--relations", default="")
    sp.add_argument("--author", default="agent")
    sp.set_defaults(func="update")

    sp = sub.add_parser("deactivate", help="soft-delete a node (active=0)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uid", required=True)
    sp.set_defaults(func="deactivate")

    sp = sub.add_parser("verify", help="integrity check on a node")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uid", required=True)
    sp.set_defaults(func="verify")

    # list / report
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

    sp = sub.add_parser("list-show", help="show List members")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uid", required=True)
    sp.set_defaults(func="list_show")

    sp = sub.add_parser("report-create", help="create L3 Report (reasoning)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--title", required=True)
    sp.add_argument("--body", required=True)
    sp.add_argument("--evidence", default="")
    sp.add_argument("--dimension", default="")
    sp.set_defaults(func="report_create")

    sp = sub.add_parser("report-show", help="show Report details + dangling evidence")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uid", required=True)
    sp.set_defaults(func="report_show")

    sp = sub.add_parser("entity-create", help="create Entity node (concept)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--title", required=True)
    sp.add_argument("--body", default="")
    sp.add_argument("--source-page", default="")
    sp.add_argument("--attrs", default="")
    sp.add_argument("--dimension", default="")
    sp.set_defaults(func="entity_create")

    # nodes / query-relation
    sp = sub.add_parser("nodes", help="DB metadata query")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--layer")
    sp.add_argument("--active-only", action="store_true")
    sp.add_argument("--limit", type=int, default=100)
    sp.set_defaults(func="nodes")

    sp = sub.add_parser("query-relation", help="list relations from a node")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--from-uid", required=True)
    sp.set_defaults(func="query_relation")

    # delete-node
    sp = sub.add_parser("delete-node", help="physically delete a node (reference-safe)")
    sp.add_argument("--wiki", required=True)
    sp.add_argument("--uid", required=True)
    sp.set_defaults(func="delete_node")

    # uninstall
    sp = sub.add_parser("uninstall", help="uninstall (dry-run default)")
    sp.add_argument("--execute", action="store_true")
    sp.add_argument("--preserve-config", action="store_true")
    sp.add_argument("--keep-pip", action="store_true")
    sp.set_defaults(func="uninstall")

    # skills (agent-side, pure Python)
    sp_skills = sub.add_parser("skills", help="manage agent skill bundle")
    sub_skills = sp_skills.add_subparsers(dest="skills_command", required=True)

    sp_skills_list = sub_skills.add_parser("list", help="list skill files bundled in wheel")
    sp_skills_list.set_defaults(func="skills_list")

    sp_skills_path = sub_skills.add_parser("path", help="print bundled skill source path")
    sp_skills_path.set_defaults(func="skills_path")

    sp_skills_install = sub_skills.add_parser("install", help="deploy skill bundle to agent dir")
    sp_skills_install.add_argument(
        "--target",
        default=str(Path.home() / ".hermes" / "skills" / "xu-wiki"),
        help="target skill directory (default: ~/.hermes/skills/xu-wiki)",
    )
    sp_skills_install.add_argument("--force", action="store_true")
    sp_skills_install.set_defaults(func="skills_install")

    return p

def main():
    args = build_parser().parse_args()
    result = dispatch(args)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2))
    sys.stdout.write("\n")
    sys.exit(0 if result.get("status") in ("success", "warning") else 1)

def dispatch(args):
    from xu._core import (
        py_create,
        py_alias_set, py_alias_unset, py_alias_show,
        py_register, py_unregister,
        py_config_show, py_config_path, py_config_set_mineru_key,
        py_wikis,
        py_selfcheck, py_doctor,
        py_ingest_commit, py_ingest_context,
        py_query, py_expand, py_update, py_deactivate, py_verify,
        py_list_create, py_list_extend, py_list_show,
        py_report_create, py_report_show,
        py_entity_create,
        py_nodes, py_query_relation, py_delete_node,
        py_uninstall_plan, py_uninstall_execute,
    )

    f = args.func

    if f == "create":
        r = json.loads(py_create(args.name or "", args.path, getattr(args, 'alias', None)))
        return r

    if f == "alias_set":
        return json.loads(py_alias_set(args.wiki, args.alias))

    if f == "alias_unset":
        return json.loads(py_alias_unset(args.wiki))

    if f == "alias_show":
        return json.loads(py_alias_show(args.wiki))

    if f == "register":
        return json.loads(py_register(args.name, args.path, getattr(args, 'alias', None)))

    if f == "unregister":
        return json.loads(py_unregister(args.name))

    if f == "config_show":
        return json.loads(py_config_show())

    if f == "config_path":
        return json.loads(py_config_path())

    if f == "config_set_mineru_key":
        return json.loads(py_config_set_mineru_key())

    if f == "wikis":
        return json.loads(py_wikis())

    if f == "selfcheck":
        return json.loads(py_selfcheck())

    if f == "doctor":
        return json.loads(py_doctor(args.wiki))

    if f == "ingest_commit":
        return json.loads(py_ingest_commit(
            args.wiki,
            getattr(args, 'pending', '') or '',
            getattr(args, 'title', '') or '',
            getattr(args, 'content_type', 'article') or 'article',
            getattr(args, 'raw_path', '') or '',
            getattr(args, 'author', 'agent') or 'agent',
            getattr(args, 'relations', '') or '',
        ))

    if f == "ingest_context":
        return json.loads(py_ingest_context(args.wiki, args.keywords))

    if f == "query":
        return json.loads(py_query(args.wiki, args.core, args.expansion, args.top_k))

    if f == "expand":
        return json.loads(py_expand(args.wiki, args.uids))

    if f == "update":
        return json.loads(py_update(
            args.wiki, args.uid,
            getattr(args, 'title', None) or None,
            getattr(args, 'body', None) or None,
            getattr(args, 'relations', '') or '',
            getattr(args, 'author', 'agent') or 'agent',
        ))

    if f == "deactivate":
        return json.loads(py_deactivate(args.wiki, args.uid))

    if f == "verify":
        return json.loads(py_verify(args.wiki, args.uid))

    if f == "list_create":
        return json.loads(py_list_create(
            args.wiki, args.title, args.members,
            getattr(args, 'dimension', '') or '',
        ))

    if f == "list_extend":
        return json.loads(py_list_extend(args.wiki, args.uid, args.members))

    if f == "list_show":
        return json.loads(py_list_show(args.wiki, args.uid))

    if f == "report_create":
        return json.loads(py_report_create(
            args.wiki, args.title, args.body,
            getattr(args, 'evidence', '') or '',
            getattr(args, 'dimension', '') or '',
        ))

    if f == "report_show":
        return json.loads(py_report_show(args.wiki, args.uid))

    if f == "entity_create":
        return json.loads(py_entity_create(
            args.wiki, args.title,
            getattr(args, 'body', '') or '',
            getattr(args, 'source_page', '') or '',
            getattr(args, 'attrs', '') or '',
            getattr(args, 'dimension', '') or '',
        ))

    if f == "nodes":
        return json.loads(py_nodes(
            args.wiki,
            getattr(args, 'layer', None),
            getattr(args, 'active_only', False),
            getattr(args, 'limit', 100),
        ))

    if f == "query_relation":
        return json.loads(py_query_relation(args.wiki, args.from_uid))

    if f == "delete_node":
        return json.loads(py_delete_node(args.wiki, args.uid))

    if f == "uninstall":
        if args.execute:
            return json.loads(py_uninstall_execute(args.preserve_config, args.keep_pip))
        return json.loads(py_uninstall_plan(args.preserve_config, args.keep_pip))

    # skills (pure Python, no Rust needed)
    if f in ("skills_list", "skills_path", "skills_install"):
        return _handle_skills(args)

    return {"status": "error", "message": f"unknown command: {f}", "hints": []}


def _handle_skills(args):
    """Dispatch `xu skills {list,path,install}` subcommands."""
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
            "hints": ["next: xu skills install"],
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

        if not (SKILL_SRC_DIR / "SKILL.md").is_file():
            return {
                "status": "error",
                "message": f"SKILL.md not found in wheel package data ({SKILL_SRC_DIR})",
                "hints": ["reinstall: pipx reinstall xu-wiki"],
            }

        copied, skipped = [], []
        for rel in ALL_SKILL_FILES:
            src = SKILL_SRC_DIR / rel
            dst = target / rel
            if dst.exists() and not args.force:
                skipped.append(str(rel))
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(src, dst)
            copied.append(str(rel))

        return {
            "status": "success",
            "data": {"copied": copied, "skipped": skipped, "target": str(target)},
            "message": f"{len(copied)} copied, {len(skipped)} skipped",
            "hints": [f"installed to {target}"],
        }
