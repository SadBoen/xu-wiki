import sys; sys.path.insert(0,'python')
from xu.utils import config as cfg
from pathlib import Path
import tempfile, json

tmp = Path(tempfile.mkdtemp())
cfg.GLOBAL_DIR = tmp
cfg.GLOBAL_CONFIG = tmp / 'config.yaml'
wdir = tmp / 'w'

tf = tmp / 'doc.md'
tf.write_text('# Ship\n\nA frigate in the harbor.')

from xu.cli import dispatch
from types import SimpleNamespace as SN

def run(cmd, **kw):
    r = dispatch(SN(func=cmd, **kw))
    s = r['status']
    m = r.get('message','')[:60]
    print(f'  {cmd:20s} {s:8s}  {m}')
    return r

print('=== CRUD + VERIFY ===')

r = run('create', name='crudwiki', path=str(wdir), alias='cw')
r = run('ingest_file', wiki='crudwiki', file=str(tf))
r = run('ingest_commit', wiki='crudwiki', pending=r['data']['pending'], title='Frigate Doc')
uid = r['data']['created'][0]['uid']
print(f'    uid={uid}')

# VERIFY after ingest
r = run('verify', wiki='crudwiki', uid=uid)
if r['status'] != 'success':
    print('VERIFY FAILED:', json.dumps(r.get('data',{}), default=str, indent=2))
    sys.exit(1)
print('    verify after ingest: PASS')

# UPDATE
r = run('update', wiki='crudwiki', uid=uid, title='Destroyer', body='A destroyer patrols.')
assert 'title' in r['data']['changed'] and 'body' in r['data']['changed']
assert r['data']['version'] == 2
print('    update v2: PASS')

# VERIFY after update
r = run('verify', wiki='crudwiki', uid=uid)
assert r['status'] == 'success'
print('    verify after update: PASS')

# READ
r = run('expand', wiki='crudwiki', uids=uid)
assert 'destroyer' in r['data']['nodes'][uid]['body'].lower()
print('    expand new body: PASS')

# Relations
tf2 = tmp / 'doc2.md'
tf2.write_text('# Harbor\n\nThe port is busy.')
r = run('ingest_file', wiki='crudwiki', file=str(tf2))
r = run('ingest_commit', wiki='crudwiki', pending=r['data']['pending'], title='Harbor')
uid2 = r['data']['created'][0]['uid']
r = run('update', wiki='crudwiki', uid=uid,
        relations=json.dumps([{'to_uid':uid2,'relation_name':'mentions','comment':'ref'}]))
assert r['status'] == 'success'
r = run('verify', wiki='crudwiki', uid=uid)
assert r['status'] == 'success'
print('    update relations + verify: PASS')

# Deactivate
r = run('deactivate', wiki='crudwiki', uid=uid)
assert r['status'] == 'success'
r = run('verify', wiki='crudwiki', uid=uid)
assert r['status'] == 'warning'
print('    deactivate + verify warning: PASS')

# Query excludes deactivated
r = run('query', wiki='crudwiki', core='destroyer', expansion='', top_k=10)
assert r['data']['total_hits'] == 0
print('    query excludes deactivated: PASS')

print()
print('ALL CRUD + VERIFY PASSED')
