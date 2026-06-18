"""Experience-reference default values (00-index.md "原则 ↔ 具体值对照").

These are STARTING POINTS, tunable via wiki-internal config — not contracts.
"""
from __future__ import annotations

WIKI_FORMAT_VERSION = "1.0.0"

# Frontmatter field names (CONST-ARCH-2). Implementation-chosen names.
FM_UID = "uid"
FM_TITLE = "title"
FM_LAYER = "layer"          # ∈ {Page, List, Report}
FM_TEMPLATE = "template"    # ∈ {article, table, gallery, ...}
FM_ACTIVE = "active"        # bool (not 0/1)
FM_CREATED = "created_at"
FM_CONTENT_HASH = "content_hash"
FM_NODE_PATH = "node_path"
FM_RAW_PATH = "raw_path"
FM_SOURCE_HASH = "source_hash"

REQUIRED_FM_FIELDS = [FM_UID, FM_TITLE, FM_LAYER, FM_TEMPLATE, FM_ACTIVE, FM_CREATED, FM_CONTENT_HASH]

LAYERS = {"Page", "List", "Report"}
TEMPLATES = {"article", "table", "gallery"}

# Ingest (PRIN-ING-4)
PAGE_SPLIT_LINES = 300

# Query scoring (PRIN-QRY-10, experience reference values)
CORE_WEIGHT = 2000
EXPANSION_WEIGHT = 500
DENSITY_BONUS = 1.5            # CONST-QRY-5: must be > 1
IDF_CONSTANT = 10000          # PRIN-QRY-11: weight = const / (freq + 1)

# Slicing (DESIGN-ARCH-6/7)
SLICE_SOFT_LIMIT = 80
SLICE_HARD_LIMIT = 150
MERGE_RADIUS = 80

# Fast Pass (PRIN-QRY-12, CONST-QRY-6)
FAST_PASS_K = 3.0
FAST_PASS_LOW_HIT = 3
TOP_K = 10                    # CONST-QRY-7

# Relations (PRIN-ARCH-7)
MAX_EDGES = 50

# Assets
COMPRESS_OVER_BYTES = 2 * 1024 * 1024

QUERY_TIMEOUT_SECONDS = 10    # CONST-QRY-9

REBUILD_GRANULARITY = ["keep-l1", "keep-l1-l2", "full"]


def default_wiki_config(name: str) -> dict:
    return {
        "version": WIKI_FORMAT_VERSION,
        "name": name,
        "templates": {},
        "query": {
            "slice": {
                "soft_limit": SLICE_SOFT_LIMIT,
                "hard_limit": SLICE_HARD_LIMIT,
                "merge_radius": MERGE_RADIUS,
            },
            "scoring": {
                "core_weight": CORE_WEIGHT,
                "expansion_weight": EXPANSION_WEIGHT,
                "density_bonus": DENSITY_BONUS,
                "idf_constant": IDF_CONSTANT,
            },
            "fast_pass": {
                "enabled": True,
                "dynamic": True,
                "k": FAST_PASS_K,
                "low_hit": FAST_PASS_LOW_HIT,
            },
            "top_k": TOP_K,
            "timeout_seconds": QUERY_TIMEOUT_SECONDS,
        },
        "relation": {
            "max_edges": MAX_EDGES,
            "policy": "lru",
        },
        "asset": {
            "compress_over": COMPRESS_OVER_BYTES,
            "preserve_exif": True,
        },
        "ingest": {
            "page_split_lines": PAGE_SPLIT_LINES,
        },
        "rebuild": {
            "granularity": REBUILD_GRANULARITY,
        },
    }
