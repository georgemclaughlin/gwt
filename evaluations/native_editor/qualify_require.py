"""Qualify sequential REQUIRE proofs, policy revisions, and an explicit engine change."""
import argparse
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

    original = Path('examples/native_require/rules.gwt').read_text()
    source, candidate = output / 'rules.gwt', output / 'candidate.gwt'
    source.write_text(original)
    candidate.write_text(original.replace('REQUIRE facts.method.verified', 'REQUIRE true'))
    validation = run(native, 'validate', source, '--html', output / 'validation.html')
    assert validation['ok']
    write('validation.json', validation)
    methods = [None, {'kind': 'cash', 'desk': 'North'}] + [
        {'kind': 'bank', 'account': account, 'verified': verified}
        for account in ['', 'A'] for verified in [False, True]]
    cases, expectations = [], []
    for amount in [-1, 0, 1, 100]:
        for method in methods:
            index = len(cases)
            accepted = amount > 0 and method is not None and method['kind'] == 'bank' and method['account'] == 'A' and method['verified']
            input_path = write(f'input-{index}.json', {'facts': {'amount': amount, 'method': method}})
            case = run(native, 'capture', source, '--request', 'prepare transfer', '--input', input_path)
            observed = case['record']['observed']
            assert observed['ok'] == accepted
            if accepted:
                assert observed['result'] == {'transfer': {'account': 'A', 'amount': amount}}
            else:
                assert observed['diagnostic']['code'] == 'assertion_failed'
                assert observed['state']['transfer'] == {'account': '', 'amount': 0}
            path = write(f'case-{index}.json', case)
            replay = run(native, 'replay', path)
            assert replay['verified'] and replay['actual'] == observed
            write(f'replay-{index}.json', replay)
            cases.append(path)
            expectations.append({'case': index, 'input': json.loads(input_path.read_text()), 'accepted': accepted})
    write('independent-expectations.json', expectations)
    corpus = write('corpus.json', run(native, 'corpus', *cases))
    review = run(native, 'review', corpus, '--candidate', candidate, '--html', output / 'review.html')
    write('review.json', review)
    assert review['totals']['compared'] == 24 and review['totals']['outcomeChanged'] == 2, review['totals']
    assert review['totals']['baselineMismatch'] == review['totals']['unavailable'] == 0

    # Old code could assert presence and then clear it through a wider alias.
    # Retain that observation and make the changed runtime semantics reviewable.
    guard = output / 'guarded-alias.gwt'
    guard.write_text('RECORD Box\n  value: optional<integer>\nREQUEST replace\n  GIVEN box is Box\n  GIVEN replacement is Box\n  WHEN replace box through box with replacement\n  OUTPUT box is Box\nWHEN replace <box> through <alias> with <replacement>\n  GIVEN box is Box\n  AND alias is Box\n  AND replacement is Box\n  REQUIRE box.value is present\n  set alias to replacement\n')
    input_path = write('guard-input.json', {'box': {'value': 1}, 'replacement': {}})
    old = run(previous, 'capture', guard, '--request', 'replace', '--input', input_path)
    assert old['record']['observed']['ok'] and old['record']['observed']['result'] == {'box': {'value': None}}
    old_path = write('previous-guard-case.json', old)
    original_case = old_path.read_bytes()
    migration = run(native, 'migrate', old_path, '--previous-engine', previous)
    write('guard-migration.json', migration)
    assert migration['status'] == 'observation_changed', migration
    observed = migration['candidate']['record']['observed']
    assert not observed['ok'] and observed['diagnostic']['code'] == 'presence_mutation'
    assert observed['state']['box'] == {'value': 1}
    assert not any(event['operation'] == 'set' for event in observed['events'])
    candidate_case = write('candidate-guard-case.json', migration['candidate'])
    replay = run(native, 'replay', candidate_case)
    assert replay['verified'] and replay['actual'] == observed
    write('guard-replay.json', replay)
    assert old_path.read_bytes() == original_case
    result = {'native': str(native), 'nativeSha256': hashlib.sha256(native.read_bytes()).hexdigest(),
              'previousEngine': str(previous), 'previousSha256': hashlib.sha256(previous.read_bytes()).hexdigest(),
              'policyCases': len(cases), 'policyAccepted': sum(row['accepted'] for row in expectations),
              'reviewTotals': review['totals'], 'engineChange': migration['status'], 'previousCaseUnchanged': True,
              'candidateGuardReplayVerified': True, 'reviewApproved': False}
    write('qualification.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
