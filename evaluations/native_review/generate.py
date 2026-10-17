"""Generate native review fixtures from independent acceptance cases; no browser dependency."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('output', type=Path)
parser.add_argument('--native', type=Path, default=ROOT / 'target/debug/gwt')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)

def invoke(*arguments, allowed=(0,)):
    result = subprocess.run([str(args.native.resolve()), *map(str, arguments)], cwd=ROOT, text=True, capture_output=True)
    if result.returncode not in allowed:
        raise RuntimeError(result.stdout + result.stderr)
    return json.loads(result.stdout)

def capture(source, request, facts, directory):
    path = directory / 'input.json'
    path.write_text(json.dumps(facts))
    return invoke('capture', source, '--request', request, '--input', path)

def review(directory, cases, candidate):
    corpus = directory / 'corpus.json'
    corpus.write_text(json.dumps({'kind':'gwt.native-corpus','schemaVersion':1,'cases':cases}, ensure_ascii=False))
    result = invoke('review', corpus, '--candidate', candidate, '--html', directory / 'review.html', allowed=(0,1))
    (directory / 'review.json').write_text(json.dumps(result, ensure_ascii=False))
    return result

manifest = json.loads((ROOT / 'evaluations/maintenance/manifest.json').read_text())
results = []
for task in manifest['cases']:
    if task['kind'] != 'maintain':
        continue
    directory = args.output / task['id']
    directory.mkdir(exist_ok=True)
    source = (ROOT / 'evaluations/maintenance' / task['starter']['gwt']).resolve()
    candidate = (ROOT / 'evaluations/maintenance' / task['gold']['gwt']).resolve()
    cases = [{'id':f"{task['id']}-{index:03}",'label':f"{probe['kind']} acceptance case {index}",'case':capture(source, task['request'], probe['input'], directory)} for index,probe in enumerate(task['probes'])]
    result = review(directory, cases, candidate)
    assert result['complete']
    assert result['totals']['total'] == len(task['probes'])
    assert result['totals']['outcomeChanged'] == sum(p['kind']=='changed' for p in task['probes'])
    for row, probe in zip(result['cases'], task['probes']):
        assert row['comparison']['candidate']['result'] == probe['expected']
    results.append({'workflow':task['id'],'totals':result['totals']})

faults = args.output / 'faults'
faults.mkdir(exist_ok=True)
source = ROOT / 'crates/gwt-core/tests/fixtures/invoice.gwt'
good = capture(source, 'price invoice', {'invoice':{'unit_price':'19.95','quantity':2}}, faults)
failed = capture(source, 'price invoice', {'invoice':{'unit_price':'19.95','quantity':0}}, faults)
big = capture(source, 'price invoice', {'invoice':{'unit_price':'0','quantity':9007199254740993}}, faults)
def clone(case): return json.loads(json.dumps(case))
def resign(case):
    case.pop('integrity',None)
    encoded = json.dumps(case,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    case['integrity'] = 'sha256:' + hashlib.sha256(b'gwt-native-case-sha256-v1\0'+encoded).hexdigest()
    return case
mismatch = clone(good)
mismatch['record']['observed']['result']['decision']['total'] = '999'
corrupt = clone(good)
corrupt['integrity'] = 'corrupted'
engine = clone(good)
engine['record']['engine']['profile'] = 'different-engine'
cases = [{'id':name,'label':label,'case':case} for name,label,case in [
    ('good','Matching successful run',good),('failed','Matching execution failure',failed),
    ('huge','<img src=x onerror="globalThis.injected=true"> </script><script>globalThis.injected=true</script>',big),
    ('mismatch','Recomputed hash over a false observation',resign(mismatch)),
    ('corrupt','Corrupted integrity digest',corrupt),('engine','Incompatible engine',resign(engine)),('invalid','Invalid case data',None)]]
result = review(faults,cases,source)
assert not result['complete']
assert result['totals']['total']==7 and result['totals']['compared']==3
assert result['totals']['unavailable']==3 and result['totals']['baselineMismatch']==1
results.append({'workflow':'faults','totals':result['totals']})

reservation = args.output / 'stock-reservation'
reservation.mkdir(exist_ok=True)
source = ROOT / 'examples/native_reservation/rules.gwt'
candidate = reservation / 'candidate.gwt'
candidate.write_text(source.read_text().replace(
    'stock.available >= line.quantity', 'stock.available > line.quantity'))
cases = []
expected_results = []
for available in range(6):
    for quantity in range(1, 7):
        facts = {'order': {'lines': [
            {'sku': 'widget', 'quantity': quantity}, {'sku': 'unknown', 'quantity': 1}
        ]}, 'inventory': {'items': [{'sku': 'widget', 'available': available}]}}
        cases.append({'id': f'stock-{available}-request-{quantity}',
                      'label': f'{available} available; {quantity} requested',
                      'case': capture(source, 'reserve order', facts, reservation)})
        reserved = quantity if available > quantity else 0
        expected_results.append({
            'decision': {'line_count': 2, 'requested': quantity + 1, 'reserved': reserved,
                         'remaining': available - reserved, 'missing': ['unknown'],
                         'shortages': [] if reserved else ['widget']},
            'inventory': {'items': [{'sku': 'widget', 'available': available - reserved}]}
        })
cases.append({'id': 'empty', 'label': 'Empty order and inventory', 'case': capture(
    source, 'reserve order', {'order': {'lines': []}, 'inventory': {'items': []}}, reservation)})
expected_results.append({'decision': {'line_count': 0, 'requested': 0, 'reserved': 0,
                                     'remaining': 0, 'missing': [], 'shortages': []},
                         'inventory': {'items': []}})
result = review(reservation, cases, candidate)
assert result['complete'] and result['totals']['total'] == 37
assert result['totals']['outcomeChanged'] == 5
for row, expected in zip(result['cases'], expected_results):
    assert row['comparison']['candidate']['result'] == expected
results.append({'workflow': 'stock-reservation', 'totals': result['totals']})
(args.output / 'generation-report.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results))
