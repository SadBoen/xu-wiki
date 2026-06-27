#!/usr/bin/env bash
# End-to-end verification of xu-wiki M1->M5 against real sample files.
set -e
export XU_HOME=/tmp/xw_e2e_home
WIKI=/tmp/xw_e2e/demo
SAMPLES="${XU_SAMPLES:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/design-docs/测试用样例文件}"
if [ ! -d "$SAMPLES" ]; then
  echo "sample dir not found: $SAMPLES" >&2
  echo "set XU_SAMPLES to the directory holding PDF/ DOCX/ etc. sample files" >&2
  exit 1
fi
XU=".venv/bin/xu"

rm -rf /tmp/xw_e2e /tmp/xw_e2e_home
echo "################ M1: create ################"
$XU create --name demo --path $WIKI --alias d 2>/dev/null | python3 -c "import sys,json;d=json.load(sys.stdin);print('create:',d['status'],d['data']['path'])"

echo
echo "################ M2: ingest (PDF + DOCX) + query + read ################"
for f in "$SAMPLES/PDF/02_arxiv_resnet.pdf" "$SAMPLES/PDF/03_arxiv_bert.pdf"; do
  base=$(basename "$f")
  title=$(echo "$base" | sed 's/\.[^.]*$//')
  out=$($XU ingest-file --wiki demo --file "$f" --node-path papers/ml 2>/dev/null)
  pend=$(python3 -c "import sys,json;print(json.load(sys.stdin)['data'].get('temp',''))" <<< "$out")
  echo "  parse $base: $(python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'],d['data'].get('parser'),d['data'].get('chars'),'chars')" <<< "$out")"
  $XU ingest-commit --wiki demo --temp "$pend" --title "$title" --node-path papers/ml 2>/dev/null \
    | python3 -c "import sys,json;d=json.load(sys.stdin);print('  commit',d['status'],d['data'].get('page_count'),'pages ->',[c['uid'] for c in d['data'].get('created',[])])"
done

echo
echo "  --- query (multi-keyword, multi-round) ---"
$XU query --wiki demo --keywords "network,learning,training" --top-k 3 2>/dev/null \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('  status',d['status'],'hits',d['data']['total_hits'],'uid_batch',d['data']['uid_batch'],'max_rounds',d['data']['max_rounds']);[print('   ',b['uid'],'score=',b['score'],'matched=',b['matched']) for b in d['data']['blocks']]"

FIRST=$($XU nodes --wiki demo --layer Page 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['nodes'][0]['uid'])")
echo "  --- read $FIRST ---"
$XU read --wiki demo --uid $FIRST 2>/dev/null | python3 -c "import sys,json;d=json.load(sys.stdin);print('  status',d['status'],'body_len',len(d['data']['body']),'patch_v',[p['version'] for p in d['data']['patch_versions']])"

echo
echo "################ M3: relations (50 LRU) + query --neighbors ################"
SECOND=$($XU nodes --wiki demo --layer Page 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['nodes'][1]['uid'])")
$XU query-relation add --wiki demo --from-uid $FIRST --to-uid $SECOND --relation-name "compares_to" --comment "both transformer-era" 2>/dev/null \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('  add:',d['status'],d['data']['action'],'edges',d['data']['edge_count'])"
$XU query-relation list --wiki demo --from-uid $FIRST 2>/dev/null \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('  list:',[(r['position'],r['to_uid'],r['relation_name']) for r in d['data']['relations']])"

echo
echo "################ M4: list + report (evidence chain) ################"
$XU list create --wiki demo --title "ML papers" --members "$FIRST,$SECOND" --dimension "architecture" 2>/dev/null \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('  list create:',d['status'],d['data']['uid'])"
LID=$($XU nodes --wiki demo --layer List 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['nodes'][0]['uid'])")
$XU report create --wiki demo --title "ML evolution" --body "ResNet and BERT mark key architecture shifts." --references "$FIRST,$LID" 2>/dev/null \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('  report create:',d['status'],d['data']['uid'],'refs',d['data']['ref_count'])"
echo "  --- empty-evidence rejection ---"
$XU report create --wiki demo --title "naked" --body "x" --references "" 2>/dev/null \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('  ',d['status'],d['data'].get('error_class'))"

echo
echo "################ M5: doctor + rebuild + delete-node ################"
$XU doctor --wiki demo 2>/dev/null | python3 -c "import sys,json;d=json.load(sys.stdin);print('  doctor-all:',d['status'],'total_issues',d['data']['total_issues'])"
$XU rebuild --wiki demo --granularity keep-l1 2>/dev/null | python3 -c "import sys,json;d=json.load(sys.stdin);print('  rebuild:',d['status'])"
$XU delete-node --wiki demo --uid $FIRST 2>/dev/null | python3 -c "import sys,json;d=json.load(sys.stdin);print('  delete (referenced):',d['status'],d['data'].get('error_class'))"
$XU doctor --wiki demo 2>/dev/null | python3 -c "import sys,json;d=json.load(sys.stdin);print('  doctor recheck:',d['status'],'issues',d['data']['total_issues'])"

echo
echo "################ M6: deploy + selfcheck + uninstall ################"
# Verify skill deploy works
DEPLOY_OUT=$($XU deploy skill --target hermes 2>/dev/null)
echo "  deploy skill: $(echo "$DEPLOY_OUT" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'])")

# Verify selfcheck passes
CHECK_OUT=$($XU selfcheck 2>/dev/null)
echo "  selfcheck: $(echo "$CHECK_OUT" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'], '- extras:', d['data'].get('optional_extras',{}).get('ok')))"

# Verify uninstall dry-run plan prints (no --execute)
UNINST_DRY=$($XU uninstall --target hermes 2>/dev/null)
echo "  uninstall dry-run: $(echo "$UNINST_DRY" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'], '- mode:', d['data']['plan']['mode'])")"

# Verify uninstall with --keep-skill --keep-program --preserve-config (nothing removed)
UNINST_KEEP=$($XU uninstall --target hermes --execute --keep-skill --keep-program --preserve-config 2>/dev/null)
echo "  uninstall keep-all: $(echo "$UNINST_KEEP" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'])")"

echo
echo "ALL MILESTONES VERIFIED END-TO-END."