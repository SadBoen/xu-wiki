"""Full SOP flow simulation."""
import json, sys, tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, "python")
from xu.utils import config as cfg
from xu.cli import dispatch

tmp = Path(tempfile.mkdtemp())
cfg.GLOBAL_DIR = tmp
cfg.GLOBAL_CONFIG = tmp / "config.yaml"
wiki_path = str(tmp / "ship-wiki")

def step(n, cmd, **kw):
    r = dispatch(SimpleNamespace(**kw))
    s = r.get("status", "?")
    m = r.get("message", "")
    h = r.get("hints", [])
    d = r.get("data", {})
    tag = "OK" if s == "success" else ("WARN" if s == "warning" else "FAIL")
    print(f"\n{'='*50}")
    print(f"STEP {n}: {cmd}")
    print(f"  [{tag}] {s}")
    if m: print(f"  -> {m}")
    if h: print(f"  hints: {h}")
    return d

print("=" * 50)
print("FULL SOP SIMULATION")
print("=" * 50)

# CREATE
d = step(1, "create", func="create", name="ship-wiki", path=wiki_path, alias=None)

# INGEST doc1
doc1 = tmp / "solas.md"
doc1.write_text("# SOLAS 2024\n\n## Fire Safety\nPassenger ship fire detection.\n\n## Life-Saving\nUpdated standards for cargo vessels.\n")
d = step(2, "ingest-file", func="ingest_file", wiki="ship-wiki", file=str(doc1))
pending = d.get("pending", "")

d = step(3, "ingest-context", func="ingest_context", wiki="ship-wiki", keywords="SOLAS,fire,safety,passenger,vessel")
print(f"  raws_tree={d.get('raws_tree',[])} related={len(d.get('related_nodes',[]))}")

d = step(4, "ingest-commit", func="ingest_commit",
    wiki="ship-wiki", pending=pending, title="SOLAS 2024",
    content_type="article", raw_path="ships/solas", author="agent", relations="")
uid1 = d.get("created", [{}])[0].get("uid", "?")
print(f"  UID: {uid1}")

# INGEST doc2
doc2 = tmp / "ship_spec.md"
doc2.write_text("# Vessel Spec\n\n## Hull\nSteel A36. Double hull.\n\n## Propulsion\nDiesel-electric above 5000 DWT.\n")
d = step(5, "ingest-file", func="ingest_file", wiki="ship-wiki", file=str(doc2))
pending2 = d.get("pending", "")
d = step(6, "ingest-context", func="ingest_context", wiki="ship-wiki", keywords="vessel,hull,propulsion,diesel,steel")
print(f"  related={len(d.get('related_nodes',[]))}")

d = step(7, "ingest-commit", func="ingest_commit",
    wiki="ship-wiki", pending=pending2, title="Vessel Spec",
    content_type="article", raw_path="ships/commercial", author="agent", relations="")
uid2 = d.get("created", [{}])[0].get("uid", "?")
print(f"  UID: {uid2}")

# QUERY
d = step(8, "query", func="query",
    wiki="ship-wiki", core="ship,vessel,SOLAS", expansion="hull,tanker", top_k=10)
for h in d.get("related_nodes", []):
    print(f"  [{h.get('score','?')}] {h.get('uid','?')[:8]} | {h.get('snippet','')[:60]}")

# EXPAND
hits = d.get("related_nodes", [])
if hits:
    d = step(9, "expand", func="expand", wiki="ship-wiki", uids=hits[0].get("uid",""))
    for uid, node in d.get("nodes", {}).items():
        body = node.get("body","")[:80] if isinstance(node, dict) else ""
        print(f"  body: {body}...")

# DOCTOR
d = step(10, "doctor", func="doctor", wiki="ship-wiki")
checks = d.get("checks", [])
for c in (checks if isinstance(checks, list) else []):
    print(f"  {'[PASS]' if c.get('ok') else '[FAIL]'} {c.get('check')}")

# UNINSTALL
d = step(11, "uninstall", func="uninstall", execute=False, preserve_config=False, keep_pip=False)
print(f"  mode={d.get('mode')} pip_uninstall={d.get('pip_uninstall')} purge_wikis={d.get('purge_wikis')}")

print(f"\n{'='*50}")
print("COMPLETE")
