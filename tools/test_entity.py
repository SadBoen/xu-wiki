import sys; sys.path.insert(0,'python')
from xu.utils import config as cfg
from pathlib import Path
import tempfile, json

tmp = Path(tempfile.mkdtemp())
cfg.GLOBAL_DIR = tmp
cfg.GLOBAL_CONFIG = tmp / 'config.yaml'
wdir = tmp / 'w'

tf = tmp / 'ships.md'
tf.write_text('# Fleet Report\n\nThe fleet includes USS Enterprise, USS Nimitz, and USS Iowa.')

from xu.cli import dispatch
from types import SimpleNamespace as SN

def run(cmd, **kw):
    r = dispatch(SN(func=cmd, **kw))
    s = r['status']
    m = r.get('message','')[:60]
    extra = ''
    if cmd == 'query' and 'reflection' in r.get('data',{}):
        ref = r['data']['reflection']
        extra = f' hint={ref.get("hint","")[:80]}'
    print(f'  {cmd:20s} {s:8s}  {m}{extra}')
    return r

print('=== Entity + Reflection Test ===')

# Setup
r = run('create', name='fleetwiki', path=str(wdir))
r = run('ingest_file', wiki='fleetwiki', file=str(tf))
r = run('ingest_commit', wiki='fleetwiki', pending=r['data']['pending'], title='Fleet Report')
page_uid = r['data']['created'][0]['uid']
print(f'  page_uid={page_uid}')

# Create entities from the page
r = run('entity_create', wiki='fleetwiki', title='USS Enterprise', body='Nuclear-powered aircraft carrier, CVN-65.', source_page=page_uid)
assert r['status'] == 'success'
e1 = r['data']['uid']

r = run('entity_create', wiki='fleetwiki', title='USS Nimitz', body='Nimitz-class aircraft carrier, CVN-68.', source_page=page_uid)
e2 = r['data']['uid']

r = run('entity_create', wiki='fleetwiki', title='USS Iowa', body='Iowa-class battleship, BB-61.', source_page=page_uid, attrs='{"class":"Iowa","commissioned":1943}')
e3 = r['data']['uid']
print(f'  entities: {e1}, {e2}, {e3}')

# Expand entity (should work cross-layer)
r = run('expand', wiki='fleetwiki', uids=e1)
node = r['data']['nodes'][e1]
assert node['layer'] == 'Entity'
assert 'Nuclear' in node['body']
rels = node['relations']
assert any(r['relation_name'] == 'extracted_from' for r in rels)
print(f'  expand entity: layer={node["layer"]}, rels={len(rels)}')

# Query — should find entities AND have reflection
r = run('query', wiki='fleetwiki', core='carrier', expansion='ship,fleet', top_k=10)
hits = r['data']['related_nodes']
layers = set(h['layer'] for h in hits)
reflection = r['data']['reflection']
print(f'  query: hits={len(hits)}, layers={layers}')
print(f'  reflection: existing_entities={len(reflection["existing_entities"])}, suggest_extract={reflection["suggest_extract_entities"]}')

# Entities should show in reflection
assert len(reflection['existing_entities']) >= 1
assert 'USS' in str(reflection['existing_entities'])

# Query a completely new topic — should suggest entity extraction
r = run('query', wiki='fleetwiki', core='destroyer', expansion='', top_k=10)
ref = r['data']['reflection']
print(f'  query unknown topic: hits={r["data"]["total_hits"]}, reflection hint={ref.get("hint","")[:80]}')

print()
print('ALL ENTITY + REFLECTION TESTS PASSED')
