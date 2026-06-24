"""SQLite-first keyword scanner (T6). Queries node_page.body column directly."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..utils.wiki import WikiContext


def scan(ctx: "WikiContext", keywords: list[str], timeout: float = 10.0) -> dict:
    """Return {keyword: [{uid, char_pos, match_text, snippet}]} for all hits.

    Directly queries node_page.body from SQLite (authoritative L1 storage).
    Each keyword is scanned in parallel via ThreadPoolExecutor.
    Python str.find() provides precise character offsets.
    Snippet = 50 chars of context around the match.
    """
    keywords = [k for k in keywords if k.strip()]
    if not keywords:
        return {}

    conn = ctx.connect()
    try:
        rows = conn.execute(
            "SELECT uid, body FROM node_page WHERE body IS NOT NULL AND body != ''"
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        return {}

    # uid -> body map
    uid_body: dict[str, str] = {row["uid"]: row["body"] for row in rows}

    results: dict[str, list] = {k: [] for k in keywords}

    def scan_keyword(kw: str) -> list[dict]:
        hits: list[dict] = []
        kw_lower = kw.lower()
        for uid, body in uid_body.items():
            pos = 0
            while True:
                pos = body.lower().find(kw_lower, pos)
                if pos == -1:
                    break
                # verify exact-case match
                if body[pos:pos + len(kw)] != kw:
                    pos += 1
                    continue
                snippet = body[max(0, pos - 50):pos + len(kw) + 50]
                hits.append({
                    "uid": uid,
                    "char_pos": pos,
                    "match": kw,
                    "snippet": snippet,
                })
                pos += 1
        return hits

    with ThreadPoolExecutor(max_workers=len(keywords)) as executor:
        futures = {executor.submit(scan_keyword, kw): kw for kw in keywords}
        for future in futures:
            kw = futures[future]
            results[kw] = future.result()

    return results
