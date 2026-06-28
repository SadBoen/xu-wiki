"""query-relation — manage the 50-edge LRU relation list (01-wiki-architecture.md).

Relations stored in each node's frontmatter `relations` YAML list.
No SQLite; frontmatter is the sole store.
"""
from __future__ import annotations

from ..ingest.relations_lru import add_relation, list_relations
from ..utils.config import cfg_get
from ..utils.response import error, success, warning
from ..utils.wiki import resolve_wiki, find_node_md, write_node_frontmatter


def cmd_query_relation(args) -> dict:
    if args.rel_action == "add":
        return _rel_add(args)
    if args.rel_action == "list":
        return _rel_list(args)
    return error(f"unknown relation action: {args.rel_action}", "UnknownAction")


def _rel_add(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    if args.from_uid == args.to_uid:
        return error("a node cannot relate to itself", "SelfRelation")

    from_result = find_node_md(ctx, args.from_uid)
    if not from_result:
        return error(f"node not found: {args.from_uid}", "NodeNotFound")
    from_fm, _ = from_result
    if not from_fm:
        return error(f"node not found: {args.from_uid}", "NodeNotFound")

    to_result = find_node_md(ctx, args.to_uid)
    if not to_result:
        return error(f"node not found: {args.to_uid}", "NodeNotFound")
    to_fm, _ = to_result
    if not to_fm:
        return error(f"node not found: {args.to_uid}", "NodeNotFound")

    max_edges = cfg_get(ctx.config, "relation.max_edges", 50)
    result = add_relation(from_fm, args.from_uid, args.to_uid,
                          args.relation_name, args.comment, max_edges)

    write_node_frontmatter(ctx, args.from_uid, from_fm)

    rels = list_relations(from_fm, args.from_uid)
    data = {
        "from_uid": args.from_uid,
        "to_uid": args.to_uid,
        "relation_name": args.relation_name,
        "action": result["action"],
        "evicted": result["evicted"],
        "edge_count": len(rels),
    }
    if result["evicted"]:
        return warning(
            data,
            f"relation {result['action']}; LRU full → evicted tail "
            f"{result['evicted']['to_uid']} (PRIN-ARCH-7)",
            hints=["evicted edges are gone; re-add to restore at head"],
        )
    return success(data, f"relation {result['action']} at head (LRU touch)")


def _rel_list(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")

    from_result = find_node_md(ctx, args.from_uid)
    if not from_result:
        return error(f"node not found: {args.from_uid}", "NodeNotFound")
    from_fm, _ = from_result
    if not from_fm:
        return error(f"node not found: {args.from_uid}", "NodeNotFound")

    rels = list_relations(from_fm, args.from_uid)
    for r in rels:
        to_result = find_node_md(ctx, r["to_uid"])
        to_fm = to_result[0] if to_result else None
        r["to_title"] = to_fm.get("title", "(missing)") if to_fm else "(missing)"
        r["to_layer"] = to_fm.get("layer") if to_fm else None
    return success(
        {"from_uid": args.from_uid, "relations": rels, "edge_count": len(rels)},
        f"{len(rels)} edge(s) in LRU order (head = most recently touched)",
    )
