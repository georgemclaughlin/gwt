"""Qualify native collection-filter facts and a deliberate guard migration."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--previous-engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    native, previous, output = args.native.resolve(), args.previous_engine.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    commands = []

    def run(engine, *arguments):
        command = [str(engine), *map(str, arguments)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=30)
        commands.append({'command': command, 'exitCode': result.returncode, 'stderr': result.stderr})
        (output / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)

    def write(name, data):
        path = output / name
        path.write_text(json.dumps(data, indent=2) + '\n')
        return path

    original = Path('examples/native_filter_proofs/rules.gwt').read_text()
    source, candidate = output / 'rules.gwt', output / 'candidate.gwt'
    source.write_text(original)
    candidate.write_text(original.replace(' and parcel.route.ready', ''))
    validation = run(native, 'validate', source, '--html', output / 'validation.html')
    assert validation['ok']
    write('validation.json', validation)
    routes = [None, {'kind': 'courier', 'tracking': 'T'},
              {'kind': 'counter', 'code': '', 'ready': False}, {'kind': 'counter', 'code': '', 'ready': True},
              {'kind': 'counter', 'code': 'A', 'ready': False}, {'kind': 'counter', 'code': 'A', 'ready': True},
              {'kind': 'counter', 'code': 'B', 'ready': True}]
    queues = [[]]
    for first in routes:
        queues.append([first])
        queues.extend([first, second] for second in routes)
    cases, expectations = [], []
    for index, queue in enumerate(queues):
        items = [{'label': f'parcel-{i}', 'route': route, 'prepared': i % 2 == 1} for i, route in enumerate(queue)]
        expected_items, codes = copy.deepcopy(items), []
        for item in expected_items:
            route = item['route']
            if route is not None and route['kind'] == 'counter' and route['ready'] and route['code']:
                item['prepared'] = True
                codes.append(route['code'])
        expected = {'queue': {'parcels': expected_items}, 'dispatch': {'codes': codes, 'first_code': codes[0] if codes else ''}}
        input_path = write(f'input-{index}.json', {'queue': {'parcels': items}})
        case = run(native, 'capture', source, '--request', 'prepare pickups', '--input', input_path)
        observed = case['record']['observed']
        assert observed['ok'] and observed['result'] == expected
        path = write(f'case-{index}.json', case)
        replay = run(native, 'replay', path)
        assert replay['verified'] and replay['actual'] == observed
        write(f'replay-{index}.json', replay)
        cases.append(path)
        expectations.append({'case': index, 'input': json.loads(input_path.read_text()), 'expected': expected})
    assert len(cases) == 57
    write('independent-expectations.json', expectations)
    corpus = write('corpus.json', run(native, 'corpus', *cases))
    review = run(native, 'review', corpus, '--candidate', candidate, '--html', output / 'review.html')
    write('review.json', review)
    assert review['totals']['compared'] == 57 and review['totals']['outcomeChanged'] == 14, review['totals']
    assert review['totals']['baselineMismatch'] == review['totals']['unavailable'] == review['totals']['candidateFailed'] == 0

    guard = output / 'guarded-alias.gwt'
    guard.write_text('RECORD Box\n  value: optional<integer>\nREQUEST inspect\n  GIVEN items is list<Box>\n  GIVEN replacement is Box\n  WHEN inspect items with replacement\n  OUTPUT items is list<Box>\nWHEN inspect <items> with <replacement>\n  GIVEN items is list<Box>\n  AND replacement is Box\n  FOR selected in items WHERE selected.value is present\n    FIND alias in items WHERE true\n      set alias to replacement\n    ELSE\n      PASS\n')
    input_path = write('guard-input.json', {'items': [{'value': 1}], 'replacement': {}})
    old = run(previous, 'capture', guard, '--request', 'inspect', '--input', input_path)
    assert old['record']['observed']['ok'] and old['record']['observed']['result'] == {'items': [{'value': None}]}
    old_path = write('previous-guard-case.json', old)
    original_case = old_path.read_bytes()
    migration = run(native, 'migrate', old_path, '--previous-engine', previous)
    write('guard-migration.json', migration)
    assert migration['status'] == 'observation_changed'
    observed = migration['candidate']['record']['observed']
    assert not observed['ok'] and observed['diagnostic']['code'] == 'presence_mutation'
    assert observed['state']['items'] == [{'value': 1}]
    assert not any(event['operation'] == 'set' for event in observed['events'])
    candidate_case = write('candidate-guard-case.json', migration['candidate'])
    replay = run(native, 'replay', candidate_case)
    assert replay['verified'] and replay['actual'] == observed
    write('guard-replay.json', replay)
    assert old_path.read_bytes() == original_case
    result = {'native': str(native), 'nativeSha256': hashlib.sha256(native.read_bytes()).hexdigest(),
              'previousEngine': str(previous), 'previousSha256': hashlib.sha256(previous.read_bytes()).hexdigest(),
              'policyCases': len(cases), 'reviewTotals': review['totals'], 'engineChange': migration['status'],
              'previousCaseUnchanged': True, 'candidateGuardReplayVerified': True, 'reviewApproved': False}
    write('qualification.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
