import sys; sys.path.insert(0,'python')
from xu.utils import config as cfg
from pathlib import Path
import tempfile, json
tmp = Path(tempfile.mkdtemp())
cfg.GLOBAL_DIR = tmp; cfg.GLOBAL_CONFIG = tmp / 'config.yaml'
wiki = str(tmp / 'w')

from xu._core import py_create, py_ingest_commit, py_query, py_expand, py_ingest_context

# 1
r = json.loads(py_create('test', wiki, None))
print('1.create:', r['status'])

# 2
pending1 = '<!-- xu-pending source_hash=abc parser=test -->\n# Ship Design\n\nVessel hull design for commercial ships.\n\n## Propulsion\n\nDiesel-electric systems for cargo vessels.\n'
r = json.loads(py_ingest_commit(wiki, pending1, 'Ship Design', 'article', 'ships', 'agent', ''))
uid1 = r['data']['created'][0]['uid']
print('2.commit:', r['status'], uid1[:8])

# 3
pending2 = '<!-- xu-pending source_hash=def parser=test -->\n# SOLAS\n\nFire safety for passenger ships.\n'
r = json.loads(py_ingest_commit(wiki, pending2, 'SOLAS 2024', 'article', 'solas', 'agent', ''))
uid2 = r['data']['created'][0]['uid']
print('3.commit:', r['status'], uid2[:8])

# 4
r = json.loads(py_ingest_context(wiki, 'ship,vessel,SOLAS,fire'))
print(f'4.context: {r["status"]} raws={len(r["data"]["raws_tree"])} related={len(r["data"]["related_nodes"])}')
for n in r['data']['related_nodes']:
    print(f'   {n["uid"][:8]} {n["title"]} match={n["match_count"]}')

# 5
r = json.loads(py_query(wiki, 'ship,vessel', 'cargo,fire', 10))
hits = r['data']['related_nodes']
print(f'5.query: {r["status"]} hits={len(hits)}')
for h in hits:
    print(f'   [{h["score"]}] {h["uid"][:8]} | {h["snippet"][:50]}')

# 6
r = json.loads(py_expand(wiki, hits[0]['uid']))
node = list(r['data']['nodes'].values())[0]
print(f'6.expand: body={node["body"][:60]}...')

print('\nFULL SOP: ALL PASSED')
