"""Qualify an explicit allocation operating budget and retained-case compatibility."""
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

    def save(name, value):
        path = output / name
        path.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')
        return path

    def run(engine, *arguments, expected=0):
        command = [str(engine), *map(str, arguments)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        commands.append({'command': command, 'exitCode': result.returncode, 'stderr': result.stderr})
        save('commands.json', commands)
        assert result.returncode == expected, (command, result.stdout, result.stderr)
        return json.loads(result.stdout)

    source = output / 'rules.gwt'
    source.write_text(Path('examples/native_weighted_allocation/rules.gwt').read_text())
    candidate = output / 'candidate.gwt'
    # A deliberate resource regression in a copied fixture: repeat an invariant
    # already established when preparing each share. No public rule is changed.
    needle = '    IF share.remainder_score > largest_remainder\n'
    assert source.read_text().count(needle) == 1
    candidate.write_text(source.read_text().replace(needle, '    REQUIRE share.remainder_score >= 0\n' * 10 + needle))
    limits = save('limits.json', json.loads(Path('examples/native_weighted_allocation/limits.json').read_text()))
    for path in [source, candidate]:
        assert run(native, 'inspect', path)['ok']
        run(native, 'format', path, '--check')
        report = run(native, 'validate', path, '--limits', limits)
        assert report['ok'] and len(report['results']) == 11
        save(f'{path.stem}-validation.json', report)
    inp = save('input.json', {'budget': {'total': '0.07', 'recipients': [
        {'label': str(i), 'weight': 1, 'eligible': True} for i in range(8)]}})
    options = ['--request', 'allocate budget', '--input', inp]
    baseline = run(native, 'run', source, *options)
    ordinary_candidate = run(native, 'run', candidate, *options)
    assert baseline['ok'] and ordinary_candidate['ok']
    assert baseline['result'] == ordinary_candidate['result']
    assert baseline['state'] == ordinary_candidate['state']
    # Independent expectation: equal shares, seven cents, eight recipients.
    shares = baseline['result']['allocation']['shares']
    assert [share['amount'] for share in shares] == ['0.01'] * 7 + ['0']
    profiles = {}
    for label, path, code in [('baseline', source, 0), ('candidate', candidate, 1)]:
        profile = run(native, 'profile', path, *options, '--limits', limits, expected=code)
        assert profile['ok'] == (code == 0)
        profiles[label] = profile
        save(f'{label}-profile.json', profile)
    assert profiles['candidate']['diagnostic']['code'] == 'evidence_limit'
    case = run(native, 'capture', source, *options, '--limits', limits)
    case_path = save('baseline-case.json', case)
    assert case['record']['observed']['ok'] and case['record']['limits'] == json.loads(limits.read_text())
    assert run(native, 'replay', case_path)['verified']
    failed = run(native, 'capture', candidate, *options, '--limits', limits)
    failed_path = save('failed-candidate-case.json', failed)
    assert not failed['record']['observed']['ok']
    assert run(native, 'replay', failed_path)['verified']
    corpus = save('corpus.json', run(native, 'corpus', case_path))
    review = run(native, 'review', corpus, '--candidate', candidate, '--html', output / 'review.html')
    save('review.json', review)
    assert review['totals']['outcomeChanged'] == 1
    assert review['totals']['unavailable'] == review['totals']['baselineMismatch'] == 0
    zero = json.loads(limits.read_text())
    zero['execution']['steps'] = 0
    zero_path = save('zero-steps.json', zero)
    refused = run(native, 'validate', source, '--limits', zero_path, '--html', output / 'validation.html', expected=1)
    assert not refused['ok'] and len(refused['results']) == 11
    assert all(row['diagnostic']['code'] == 'execution_limit' for row in refused['results'])
    save('zero-step-validation.json', refused)
    portfolio = Path('evaluations/native_editor/2026-10-16-profiling/workloads')
    for index in range(57):
        path = portfolio / f'candidate-{index}.json'
        before = path.read_bytes()
        proposal = run(native, 'migrate', path, '--previous-engine', previous)
        assert proposal['status'] == 'observation_preserved' and not proposal['approved']
        assert path.read_bytes() == before
        assert proposal['candidate']['record']['observed'] == json.loads(before)['record']['observed']
        save(f'migration-{index}.json', proposal)
        migrated = save(f'migrated-{index}.json', proposal['candidate'])
        assert run(native, 'replay', migrated)['verified']
    save('qualification.json', {'native': str(native), 'nativeSha256': hashlib.sha256(native.read_bytes()).hexdigest(),
        'previousEngine': str(previous), 'previousSha256': hashlib.sha256(previous.read_bytes()).hexdigest(),
        'defaultBudgetResultsAndStatePreserved': True, 'embeddedScenariosPassBoth': 11,
        'explicitBudgetCatchesRequestRegression': True, 'bothCapturesReplay': True,
        'zeroStepScenariosFail': 11, 'reviewTotals': review['totals'],
        'migrationsObservationPreserved': 57, 'originalsUnchanged': True, 'approved': False,
        'baselineEvidenceBytes': profiles['baseline']['evidence']['bytes'],
        'candidatePartialEvidenceBytes': profiles['candidate']['evidence']['bytes']})
    print(json.dumps({'ok': True, 'regressionCaught': True, 'migrationsPreserved': 57}))


if __name__ == '__main__':
    main()
