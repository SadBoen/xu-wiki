import sys; sys.path.insert(0,'python')
from xu.utils import config as cfg
from pathlib import Path
import tempfile, json

tmp = Path(tempfile.mkdtemp())
cfg.GLOBAL_DIR = tmp
cfg.GLOBAL_CONFIG = tmp / 'config.yaml'
wdir = tmp / 'w'

from xu.cli import dispatch
from types import SimpleNamespace as SN

def run(cmd, **kw):
    r = dispatch(SN(func=cmd, **kw))
    s = r['status']
    m = r.get('message','')[:60]
    print(f'  {cmd:20s} {s:8s}  {m}')
    return r

print('=== Doctor Test ===')

r = run('create', name='docwiki', path=str(wdir), alias='dw')

r = run('doctor', wiki='docwiki')
print('1.doctor (empty):', r['status'], 'issues:', r['data']['issues'])
stats = r['data']['stats']
assert stats['page_total'] == 0
assert stats['entity_count'] == 0
print('  empty wiki: stats correct')

# Populate
tf = tmp / 'doc.md'
tf.write_text('# Fleet\n\nShips at sea.')
r = run('ingest_file', wiki='docwiki', file=str(tf))
r = run('ingest_commit', wiki='docwiki', pending=r['data']['pending'], title='Fleet')
uid = r['data']['created'][0]['uid']

r = run('entity_create', wiki='docwiki', title='Ship A', body='Fast frigate', source_page=uid)
r = dispatch(SN(func='entity_create', wiki='docwiki', title='Ship B', body='Slow tanker'))

r = run('list_create', wiki='docwiki', title='All Ships', members=uid, dimension='type')

r = run('doctor', wiki='docwiki')
print('2.doctor (populated):', r['status'], 'issues:', r['data']['issues'])
stats = r['data']['stats']
assert stats['page_total'] == 1
assert stats['entity_count'] == 2
assert stats['list_count'] == 1
assert stats['relation_count'] == 2
print('  populated stats: correct')

# orphan_entities: Entity B has no source page or relations — correctly detected
for c in r['data']['checks']:
    if c['group'] == 'integrity':
        print(f'    {c["check"]}: ok={c["ok"]}  {c["detail"]}')
orphan_check = next(c for c in r['data']['checks'] if c['check'] == 'orphan_entities')
assert orphan_check['ok'] == False
print('  integrity: detected orphan entity (expected)')

# Deactivate page -> should detect broken relation
r = run('deactivate', wiki='docwiki', uid=uid)
r = run('doctor', wiki='docwiki')
print('3.doctor (after deactivate):', r['status'], 'issues:', r['data']['issues'])
for c in r['data']['checks']:
    if c['group'] == 'integrity':
        print(f'    {c["check"]}: ok={c["ok"]}  {c["detail"]}')

any_broken = any(c['check'] == 'broken_to_uid' and c['ok'] == False for c in r['data']['checks'])
assert any_broken, 'should detect deactivated page in list as broken'
print('  integrity: detected deactivated page in list')

print()
print('ALL DOCTOR TESTS PASSED')
