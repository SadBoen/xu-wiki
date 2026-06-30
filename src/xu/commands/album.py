"""Deprecated: ingest-album has been merged into the two-phase ingest flow.

Gallery ingestion now goes through:
  Phase 1: ingest-file --files img1,img2,... --title T --node-path P
  Phase 2: ingest-commit --temp <path> --title T --content-type gallery

This module is kept for backwards compatibility and will be removed in a
future version.
"""

from __future__ import annotations

from ..utils.response import error


def cmd_ingest_album(args) -> dict:
    """Deprecated. Use two-phase ingest instead.

    Gallery ingestion now goes through:
      Phase 1: ingest-file --files img1,img2,... --title T --node-path P \\
                   --layout table --vision --captions C
      Phase 2: ingest-commit --temp <path> --title T --content-type gallery \\
                   --author <A>
    """
    return error(
        "ingest-album is deprecated; use the two-phase ingest flow instead:\n"
        "  Phase 1: ingest-file --files <imgs> --title <t> --node-path <p>\n"
        "  Phase 2: ingest-commit --temp <path> --title <t> --content-type gallery",
        "DeprecatedCommand",
        hints=["see design-docs/05-ingest.md PRIN-ING-14 for the new flow"],
    )


def _scan_fm_index(ctx):
    """Stub: redirects to ingest._scan_fm_index for backwards compat."""
    from ..commands.ingest import _scan_fm_index as _scan

    return _scan(ctx)
