"""xu-wiki: relation-driven three-layer wiki engine for AI agents."""
__version__ = "0.1.0"

# Re-export Rust core functions for convenience
try:
    from xu._core import (
        gen_uid, is_valid_uid, sha256_text, sha256_file,
        safe_slug, safe_node_path, parse_frontmatter,
        render_frontmatter, split_pages, extract_nouns_fallback,
        make_slice, scan_bodies,
    )
except ImportError:
    pass  # _core not built yet; fall back to pure-Python implementations
