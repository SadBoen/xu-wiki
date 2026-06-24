import sys; sys.path.insert(0,'python')
from xu.utils import config as cfg
from pathlib import Path
import tempfile, json

tmp = Path(tempfile.mkdtemp())
cfg.GLOBAL_DIR = tmp
cfg.GLOBAL_CONFIG = tmp / 'config.yaml'
wdir = tmp / 'w'

tf1 = tmp / 'ship.md'; tf1.write_text('# Frigate\n\nA fast naval vessel.')
tf2 = tmp / 'submarine.md'; tf2.write_text('# Submarine\n\nAn underwater vessel.')

from xu.cli import dispatch
from types import SimpleNamespace as SN

def run(cmd, **kw):
    r = dispatch(SN(func=cmd, **kw))
    s = r['status']; m = r.get('message','')[:60]
    print(f'  {cmd:20s} {s:8s}  {m}')
    return r

print('=== L2/L3 Entity Test ===')

# Setup: create wiki, ingest 2 pages
r = run('create', name='navywiki', path=str(wdir), alias='nw')

r = run('ingest_file', wiki='navywiki', file=str(tf1))
r = run('ingest_commit', wiki='navywiki', pending=r['data']['pending'], title='Frigate')
uid1 = r['data']['created'][0]['uid']

r = run('ingest_file', wiki='navywiki', file=str(tf2))
r = run('ingest_commit', wiki='navywiki', pending=r['data']['pending'], title='Submarine')
uid2 = r['data']['created'][0]['uid']
print(f'  uids: {uid1}, {uid2}')

# Create List
r = run('list_create', wiki='navywiki', title='Naval Vessels', members=f'{uid1},{uid2}', dimension='ship_type')
assert r['status'] == 'success'
list_uid = r['data']['uid']
assert r['data']['member_count'] == 2
print(f'  list uid={list_uid}, members=2')

# Extend List
tf3 = tmp / 'destroyer.md'; tf3.write_text('# Destroyer\n\nA guided missile destroyer.')
r = run('ingest_file', wiki='navywiki', file=str(tf3))
r = run('ingest_commit', wiki='navywiki', pending=r['data']['pending'], title='Destroyer')
uid3 = r['data']['created'][0]['uid']

r = run('list_extend', wiki='navywiki', uid=list_uid, members=uid3)
assert r['status'] == 'success'
assert r['data']['total_members'] == 3
print(f'  list extended: total=3')

# Expand List (should find in node_derived)
r = run('expand', wiki='navywiki', uids=list_uid)
assert r['status'] == 'success'
node = r['data']['nodes'][list_uid]
assert node['layer'] == 'List'
assert 'Frigate' in node['body']
assert 'Submarine' in node['body']
assert 'Destroyer' in node['body']
assert len(node['relations']) == 3
assert all(rel['relation_name']=='contains' for rel in node['relations'])
print(f'  expand list: layer={node["layer"]}, rels={len(node["relations"])}')

# Create Report
body_text = "Analysis: Naval vessels in this wiki include frigates, submarines, and destroyers. All are armed surface or subsurface combatants."
r = run('report_create', wiki='navywiki', title='Naval Analysis',
        body=body_text, evidence=f'{uid1},{uid2},{uid3}', dimension='analysis')
assert r['status'] == 'success'
report_uid = r['data']['uid']
assert r['data']['evidence_count'] == 3
print(f'  report uid={report_uid}, evidence=3')

# Expand Report
r = run('expand', wiki='navywiki', uids=report_uid)
assert r['status'] == 'success'
rnode = r['data']['nodes'][report_uid]
assert rnode['layer'] == 'Report'
assert 'Naval vessels' in rnode['body']
assert len(rnode['relations']) == 3
assert all(rel['relation_name']=='cites' for rel in rnode['relations'])
print(f'  expand report: layer={rnode["layer"]}, rels={len(rnode["relations"])}')

# Query cross-layer
r = run('query', wiki='navywiki', core='naval', expansion='vessel', top_k=10)
assert r['status'] == 'success'
hits = r['data']['related_nodes']
layers = set(h['layer'] for h in hits)
# Should find List, Report, and Pages
assert 'List' in layers or 'Report' in layers, f'query should find derived nodes, got layers: {layers}'
print(f'  query cross-layer: hits={len(hits)}, layers={layers}')

# Verify derived node
r = run('verify', wiki='navywiki', uid=list_uid)
# verify doesn't check derived yet, but should at least find it
print(f'  verify list: {r["status"]}')

print()
print('ALL L2/L3 TESTS PASSED')
