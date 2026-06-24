"""Agent SOP test — follows SKILL.md workflow step by step."""
import sys; sys.path.insert(0,'python')
import json, tempfile
from pathlib import Path
from types import SimpleNamespace
from xu.utils import config as cfg

# ========== SETUP ==========
tmp = Path(tempfile.mkdtemp())
cfg.GLOBAL_DIR = tmp
cfg.GLOBAL_CONFIG = tmp / 'config.yaml'

def call(cmd_name, **kw):
    """Agent calls CLI. Returns 4-key JSON."""
    dispatch = {
        'create': lambda: __import__('xu.commands.create', fromlist=['cmd_create']).cmd_create(SimpleNamespace(**kw)),
        'ingest-file': lambda: __import__('xu.commands.ingest', fromlist=['cmd_ingest_file']).cmd_ingest_file(SimpleNamespace(**kw)),
        'ingest-context': lambda: __import__('xu.commands.ingest', fromlist=['cmd_ingest_context']).cmd_ingest_context(SimpleNamespace(**kw)),
        'ingest-commit': lambda: __import__('xu.commands.ingest', fromlist=['cmd_ingest_commit']).cmd_ingest_commit(SimpleNamespace(**kw)),
        'query': lambda: __import__('xu.commands.query', fromlist=['cmd_query']).cmd_query(SimpleNamespace(**kw)),
        'expand': lambda: __import__('xu.commands.query', fromlist=['cmd_expand']).cmd_expand(SimpleNamespace(**kw)),
        'read': lambda: __import__('xu.commands.query', fromlist=['cmd_read']).cmd_read(SimpleNamespace(**kw)),
    }
    r = dispatch[cmd_name]()
    return r

def agent_log(step, resp):
    """Agent reads 4-key JSON and logs decision."""
    s = resp['status']
    d = resp.get('data', {})
    m = resp.get('message', '')
    h = resp.get('hints', [])
    print(f"\n{'='*50}")
    print(f"STEP {step}: {s.upper()}")
    print(f"  message: {m}")
    if h: print(f"  hints: {h}")
    return s == 'success'

# ========== SOP: /xu-wiki create ==========
r = call('create', name='ship-wiki', path=str(tmp/'ship-wiki'), alias=None)
ok = agent_log(1, r)
if not ok: exit(1)

# ========== SOP: /xu-wiki ingest ==========
# Create test documents
wiki_name = 'ship-wiki'
doc1 = tmp / 'ship_spec.md'
doc1.write_text("""# Ship Design Specification

## 1. General
This document specifies the design requirements for commercial vessels.

## 2. Structural Requirements
Hull design must comply with IMO SOLAS standards. Steel grade A36 minimum.

## 3. Propulsion
Diesel-electric propulsion recommended for vessels above 5000 DWT.
""")

doc2 = tmp / 'solas_2024.md'
doc2.write_text("""# SOLAS 2024 Amendments

The International Convention for Safety of Life at Sea (SOLAS) 2024 amendments introduce new requirements for:

- Fire safety systems on passenger ships
- Life-saving appliances minimum standards  
- Cargo securing for container vessels
""")

# === Phase 1: ingest-file ===
r = call('ingest-file', wiki=wiki_name, file=str(doc1), node_path='')
ok = agent_log(2, r)
if not ok:
    print("PARSER FAILED:", r.get('message'))
    exit(1)

pending_file = r['data']['pending']
char_count = r['data'].get('char_count', 0)
print(f"  Agent reads: {char_count} chars parsed. Content preview: Ship Design Specification...")

# === Bridge: ingest-context ===
# Agent extracts keywords from the parsed content
r = call('ingest-context', wiki=wiki_name, keywords='ship,design,specification,vessel,hull,IMO,SOLAS,propulsion')
ok = agent_log(3, r)
raws_tree = r['data'].get('raws_tree', [])
related = r['data'].get('related_nodes', [])
print(f"  Agent sees: raws_tree={raws_tree}, related_nodes={len(related)}")

# Agent decision based on context:
# raws_tree is empty (first ingest) -> use "ships/specs" as raw_path
# related_nodes is empty -> no relations to add
raw_path = "ships/specs"
title = "Ship Design Specification"
print(f"  Agent decides: raw_path={raw_path}, title={title}")

# === Phase 2: ingest-commit ===
r = call('ingest-commit', wiki=wiki_name, pending=pending_file, 
         title=title, content_type='article', relations='',
         native='', source='', raw_path=raw_path, author='agent')
ok = agent_log(4, r)
if not ok:
    print("COMMIT FAILED:", r.get('message'))
    # Try without raw_path to narrow down issue
    print("Retrying without raw_path...")
    r = call('ingest-commit', wiki=wiki_name, pending=pending_file,
             title=title, content_type='article', relations='',
             native='', source='', raw_path='', author='agent')
    ok = agent_log('4b (retry)', r)

if not ok:
    exit(1)

uid1 = r['data'].get('created', [{}])[0].get('uid', '?')
print(f"  UID: {uid1}")

# === Ingest second doc ===
r = call('ingest-file', wiki=wiki_name, file=str(doc2), node_path='')
ok = agent_log(5, r)
pending2 = r['data']['pending']

# Agent reads: SOLAS content -> keywords
r = call('ingest-context', wiki=wiki_name, keywords='SOLAS,safety,fire,passenger,life-saving,cargo,IMO')
ok = agent_log(6, r)
raws_tree2 = r['data'].get('raws_tree', [])
related2 = r['data'].get('related_nodes', [])
print(f"  Agent sees: raws_tree={raws_tree2}, related={len(related2)}")
if related2:
    for n in related2:
        print(f"    {n['uid'][:6]} {n['title'][:40]} match={n['match_count']}")

# Agent decides: raw_path=ships/solas, and maybe relate to uid1
raw_path2 = "ships/solas"
relations = json.dumps([{"to_uid": uid1, "relation_name": "属于同一主题"}]) if uid1 != '?' else ''
print(f"  Agent: raw_path={raw_path2}, relations={relations[:60]}...")

r = call('ingest-commit', wiki=wiki_name, pending=pending2,
         title="SOLAS 2024 Amendments", content_type='article',
         relations=relations, native='', source='', raw_path=raw_path2, author='agent')
ok = agent_log(7, r)
if ok:
    uid2 = r['data'].get('created', [{}])[0].get('uid', '?')
    print(f"  UID: {uid2}")
else:
    print(f"  FAILED: {r.get('message', '')}")
    # Try without relations
    r = call('ingest-commit', wiki=wiki_name, pending=pending2,
             title="SOLAS 2024 Amendments", content_type='article',
             relations='', native='', source='', raw_path=raw_path2, author='agent')
    ok = agent_log('7b', r)
    if ok: uid2 = r['data'].get('created', [{}])[0].get('uid', '?')

# ========== SOP: /xu-wiki query ==========
print(f"\n{'='*50}")
print("QUERY: 'What ships are in the database?'")
print(f"{'='*50}")

# Agent grades: core=ship,vessel,设计; expansion=boat,SOLAS,规范,货轮
r = call('query', wiki=wiki_name, core='ship,vessel,SOLAS', expansion='design,specification,boat',
         top_k=10, neighbors=False, include_inactive=False)
ok = agent_log(8, r)
hits = r['data'].get('related_nodes', [])
if hits:
    for h in hits:
        print(f"  [{h['score']:>4}] {h['uid'][:8]} | {h['title'][:40]}")
        print(f"        snippet: {h['snippet'][:80]}")

    # Agent reads top hit -> xu expand
    top_uid = hits[0]['uid']
    r = call('expand', wiki=wiki_name, uids=top_uid)
    ok = agent_log(9, r)
    if ok and r['data'].get('nodes'):
        node = list(r['data']['nodes'].values())[0]
        print(f"  body: {node['body'][:100]}...")
        print(f"  relations: {node.get('relations', [])}")
else:
    print("  No hits found")

print(f"\n{'='*50}")
print("AGENT SOP TEST COMPLETE")
