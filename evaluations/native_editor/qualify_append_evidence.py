"""Compare append evidence costs, exact outcomes, replay, and engine migrations."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess


COLLECTOR = '''RECORD Labels
  values: list<text>
REQUEST collect labels
  GIVEN labels is list<text>
  GIVEN result is Labels
    values: []
  WHEN collect labels into result
  OUTPUT result is Labels
WHEN collect <labels> into <result>
  GIVEN labels is list<text>
  AND result is Labels
  FOR label in labels
    append label to result.values
'''


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


def profile(observed):
    operations = defaultdict(lambda: {'events': 0, 'bytes': 0, 'valueBytes': 0})
    seen, repeated = set(), 0
    for event in observed['events']:
        value = encoded(event['value'])
        row = operations[event['operation']]
        row['events'] += 1
        row['bytes'] += len(encoded(event))
        row['valueBytes'] += len(value)
        if value in seen:
            repeated += len(value)
        seen.add(value)
    return {'ok': observed['ok'], 'diagnostic': observed['diagnostic'], 'steps': observed['steps'],
            'events': len(observed['events']), 'bytes': sum(row['bytes'] for row in operations.values()),
            'valueBytes': sum(row['valueBytes'] for row in operations.values()),
            'repeatedExactValueBytes': repeated, 'operations': dict(operations)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--previous-engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    native, previous, output = args.native.resolve(), args.previous_engine.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    commands = []

    def save(name, data):
        path = output / name
        path.write_bytes(encoded(data) + b'\n')
        return path

    def run(engine, *arguments):
        command = [str(engine), *map(str, arguments)]
        process = subprocess.run(command, capture_output=True, text=True, timeout=30)
        commands.append({'command': command, 'exitCode': process.returncode, 'stderr': process.stderr})
        save('commands.json', commands)
        assert process.returncode == 0, process.stdout + process.stderr
        return json.loads(process.stdout)

    source = output / 'rules.gwt'
    source.write_text(COLLECTOR)
    profiles, transitions = [], Counter()
    for count in [8, 16, 32, 64, 128]:
        labels = [f'{i:03d}-' + 'x' * 196 for i in range(count)]
        inp = save(f'input-{count}.json', {'labels': labels})
        old = run(previous, 'capture', source, '--request', 'collect labels', '--input', inp)
        path = save(f'old-{count}.json', old)
        assert run(previous, 'replay', path)['verified']
        original_bytes = path.read_bytes()
        proposal = run(native, 'migrate', path, '--previous-engine', previous)
        assert proposal['status'] == 'observation_changed' and not proposal['approved']
        assert path.read_bytes() == original_bytes
        save(f'migration-{count}.json', proposal)
        candidate = save(f'new-{count}.json', proposal['candidate'])
        assert run(native, 'replay', candidate)['verified']
        before, after = old['record']['observed'], proposal['candidate']['record']['observed']
        assert after['ok'] and after['result'] == {'result': {'values': labels}}
        if before['ok']:
            assert before['result'] == after['result'] and before['state'] == after['state']
            transitions['successful_outcome_preserved'] += 1
        else:
            assert before['diagnostic']['code'] == 'evidence_limit'
            transitions['evidence_refusal_to_success'] += 1
        deltas = [event for event in after['events'] if event['operation'] == 'append item']
        assert [event['value']['index'] for event in deltas] == list(range(count))
        assert [event['value']['item'] for event in deltas] == labels
        profiles.append({'items': count, 'old': profile(before), 'new': profile(after)})
    save('collector-profiles.json', profiles)

    portfolio = Path('evaluations/native_editor/2026-10-16-local-records/review-final')
    statuses = Counter()
    for i in range(52):
        path = portfolio / f'constructed-{i}.json'
        before = path.read_bytes()
        proposal = run(native, 'migrate', path, '--previous-engine', previous)
        assert not proposal['approved'] and path.read_bytes() == before
        changes = proposal['changes']
        assert not changes['outcome'] and not changes['state'] and not changes['source']
        had_append = any(event['operation'] == 'append' for event in json.loads(before)['record']['observed']['events'])
        assert changes['evidence'] == had_append
        statuses[proposal['status']] += 1
        save(f'allocation-migration-{i}.json', proposal)
        candidate = save(f'allocation-new-{i}.json', proposal['candidate'])
        assert run(native, 'replay', candidate)['verified']

    # Rerun the allocation pressure inputs: smaller append traces do not erase
    # the separate cost of the repeated largest-remainder scans.
    allocation = output / 'allocation.gwt'
    allocation.write_text(Path('examples/native_weighted_allocation/rules.gwt').read_text())
    allocation_profiles = []
    for count in [8, 16, 32, 64]:
        inp = save(f'allocation-input-{count}.json', {'budget': {'total': f'0.{count - 1:02d}',
            'recipients': [{'label': str(i), 'weight': 1, 'eligible': True} for i in range(count)]}})
        row = {'recipients': count}
        for label, engine in [('old', previous), ('new', native)]:
            case = run(engine, 'capture', allocation, '--request', 'allocate budget', '--input', inp)
            row[label] = profile(case['record']['observed'])
        assert row['old']['ok'] == row['new']['ok'] == (count <= 16)
        allocation_profiles.append(row)
    save('allocation-profiles.json', allocation_profiles)

    candidate = output / 'candidate.gwt'
    candidate.write_text(COLLECTOR.replace('append label to', 'append (label + "!") to'))
    inp = save('review-input.json', {'labels': ['shipment-A', 'café 😀', '</script><svg onload=alert(1)>']})
    case = save('review-case.json', run(native, 'capture', source, '--request', 'collect labels', '--input', inp))
    corpus = save('corpus.json', run(native, 'corpus', case))
    review = run(native, 'review', corpus, '--candidate', candidate, '--html', output / 'review.html')
    assert review['totals']['outcomeChanged'] == review['totals']['stateChanged'] == 1
    assert review['totals']['baselineMismatch'] == review['totals']['unavailable'] == 0
    save('review.json', review)
    save('qualification.json', {'collectorTransitions': dict(transitions), 'allocationMigrations': dict(statuses),
        'reviewTotals': review['totals'], 'allOriginalsUnchanged': True, 'allCandidatesReplay': True,
        'approved': False, 'nativeSha256': hashlib.sha256(native.read_bytes()).hexdigest(),
        'previousSha256': hashlib.sha256(previous.read_bytes()).hexdigest()})
    print(json.dumps({'ok': True, 'collectorTransitions': dict(transitions), 'allocationMigrations': dict(statuses)}))


if __name__ == '__main__':
    main()
