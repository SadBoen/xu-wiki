"""Mock _core module — provides Python fallback when Rust extension isn't built.
This file is ONLY loaded when `from xu._core import ...` fails (ImportError).
It does NOT expose raw DB access — all writes go through the same command functions.
"""
import json

def _not_built():
    return json.dumps({"status":"error","message":"_core not compiled. Install wheel or run: maturin develop","hints":[]})

def py_create(name, path, alias=None): return _not_built()
def py_selfcheck(): return _not_built()
def py_doctor(wiki): return _not_built()
def py_uninstall_plan(preserve_config, keep_pip): return _not_built()
def py_uninstall_execute(preserve_config, keep_pip): return _not_built()
def py_ingest_commit(wiki, pending, title, content_type, raw_path, author, relations): return _not_built()
def py_query(wiki, core, expansion, top_k): return _not_built()
def py_expand(wiki, uids): return _not_built()
def py_ingest_context(wiki, keywords): return _not_built()
