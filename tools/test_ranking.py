import sys;sys.path.insert(0,'python')
from xu.utils import config as cfg;from pathlib import Path;import tempfile,json
tmp=Path(tempfile.mkdtemp());cfg.GLOBAL_DIR=tmp;cfg.GLOBAL_CONFIG=tmp/'config.yaml';wdir=tmp/'w'
from xu.cli import dispatch;from types import SimpleNamespace as SN

r=dispatch(SN(func='create',name='qw',path=str(wdir)))
tf=tmp/'a.md';tf.write_text('Aircraft carriers are large warships.')
r=dispatch(SN(func='ingest_file',wiki='qw',file=str(tf)))
r=dispatch(SN(func='ingest_commit',wiki='qw',pending=r['data']['pending'],title='Carriers'))
page_uid=r['data']['created'][0]['uid']

# Entity: has 'carrier' in body
r=dispatch(SN(func='entity_create',wiki='qw',title='USS Nimitz',body='A nuclear carrier.'))

# Report: has 'carrier' in body
r=dispatch(SN(func='report_create',wiki='qw',title='Analysis',body='Carrier analysis shows...'))

# Query for 'carrier' — Report should rank first (5x), Entity second (3x), Page last (1x)
r=dispatch(SN(func='query',wiki='qw',core='carrier',expansion='',top_k=10))
hits=r['data']['related_nodes']
for h in hits[:5]:
    print(f'  layer={h["layer"]:8s} score={h["score"]:2d} boosted={h["boosted"]:2d} title={h["title"][:30]}')

layers=[h['layer'] for h in hits]
assert layers[0]=='Report', f'Report should be first, got {layers}'
assert layers[1]=='Entity', f'Entity should be second, got {layers}'
assert layers[2]=='Page', f'Page should be last, got {layers}'
print('PASS: Report > Entity > Page')
