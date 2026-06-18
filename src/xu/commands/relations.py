"""query-relation — manage the 50-edge LRU relation list (01-wiki-architecture.md).

50 edges per node, single ordered list, no strong/weak category, no score.
add = touch (head insert + tail eviction); list = ordered view.
"""
from __future__ import annotations

from ..ingest.relations_lru import add_relation, list_relations
from ..utils.config import cfg_get
from ..utils.paths import now_ts
from ..utils.response import error, success, warning
from ..utils.wiki import resolve_wiki


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

    conn = ctx.connect()
    try:
        for uid in (args.from_uid, args.to_uid):
            if not conn.execute("SELECT 1 FROM nodes WHERE uid=?", (uid,)).fetchone():
                return error(f"node not found: {uid}", "NodeNotFound")

        max_edges = cfg_get(ctx.config, "relation.max_edges", 50)
        result = add_relation(conn, args.from_uid, args.to_uid,
                              args.relation_name, args.comment, max_edges)
        conn.commit()

        rels = list_relations(conn, args.from_uid)
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
    finally:
        conn.close()


def _rel_list(args) -> dict:
    ctx = resolve_wiki(args.wiki)
    if not ctx:
        return error(f"wiki not found: {args.wiki!r}", "WikiNotFound")
    conn = ctx.connect()
    try:
        if not conn.execute("SELECT 1 FROM nodes WHERE uid=?", (args.from_uid,)).fetchone():
            return error(f"node not found: {args.from_uid}", "NodeNotFound")
        rels = list_relations(conn, args.from_uid)
        # enrich with target titles
        for r in rels:
            row = conn.execute("SELECT title, layer FROM nodes WHERE uid=?",
                               (r["to_uid"],)).fetchone()
            r["to_title"] = row["title"] if row else "(missing)"
            r["to_layer"] = row["layer"] if row else None
        return success(
            {"from_uid": args.from_uid, "relations": rels, "edge_count": len(rels)},
            f"{len(rels)} edge(s) in LRU order (head = most recently touched)",
        )
    finally:
        conn.close()
