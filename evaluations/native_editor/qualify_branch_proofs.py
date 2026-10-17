"""Qualify branch-exit proofs, equivalent source adaptation, and explicit engine changes."""
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
    native, previous, root = args.native.resolve(), args.previous_engine.resolve(), args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    commands = []
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in (native, previous)}
    def save(name, data):
        path = root / name
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n')
        return path
    def run(engine, *arguments, expected=0):
        command = [str(engine), *map(str, arguments)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        commands.append({'command': command, 'exitCode': result.returncode, 'stderr': result.stderr})
        save('commands.json', commands)
        assert result.returncode == expected, (command, result.stdout[:2000], result.stderr)
        return json.loads(result.stdout)
    source = Path('examples/native_branch_proofs/rules.gwt').read_text()
    current, nested, faulty = root / 'rules.gwt', root / 'nested.gwt', root / 'faulty.gwt'
    current.write_text(source)
    tail = '  REQUIRE facts.proof.reference != ""\n  RETURN facts.proof.reference\n'
    assert source.count(tail) == 1
    branch_end = '    REQUIRE facts.proof.kind == "receipt"\n'
    assert source.count(branch_end) == 2
    nested.write_text(source.replace(tail, '').replace(branch_end, branch_end + '    REQUIRE facts.proof.reference != ""\n    RETURN facts.proof.reference\n'))
    faulty.write_text(source.replace('REQUIRE facts.locker_checked', 'REQUIRE true'))
    for engine, path in [(previous, nested), (native, nested), (native, current)]:
        validation = run(engine, 'validate', path)
        assert validation['ok'] and len(validation['results']) == 7
        save(('old-' if engine == previous else 'new-') + path.stem + '-validation.json', validation)
    original_cases, cases = [], []
    for mode in ('counter', 'locker'):
        for staff in (False, True):
            for locker in (False, True):
                for proof in (None, {'kind': 'gift', 'message': 'G'}, {'kind': 'receipt', 'reference': ''}, {'kind': 'receipt', 'reference': 'R'}):
                    index = len(cases)
                    data = {'facts': {'mode': mode, 'staff_checked': staff, 'locker_checked': locker, 'proof': proof}}
                    input_path = save(f'input-{index}.json', data)
                    old = run(previous, 'capture', nested, '--request', 'authorize collection', '--input', input_path)
                    expected = (staff if mode == 'counter' else locker) and proof == {'kind': 'receipt', 'reference': 'R'}
                    assert old['record']['observed']['ok'] == expected
                    original = save(f'old-{index}.json', old)
                    before = original.read_bytes()
                    proposal = run(native, 'migrate', original, '--previous-engine', previous)
                    assert proposal['status'] == 'observation_preserved' and not proposal['approved']
                    save(f'policy-migration-{index}.json', proposal)
                    case = proposal['candidate']
                    candidate = save(f'migrated-policy-{index}.json', case)
                    assert run(native, 'replay', candidate)['verified']
                    assert original.read_bytes() == before
                    original_cases.append(original)
                    cases.append({'id': f'collection-{index}', 'label': f'{mode}, staff={staff}, locker={locker}, proof={proof}', 'case': case})
    corpus = save('policy-corpus.json', {'kind':'gwt.native-corpus', 'schemaVersion':1, 'cases':cases})
    adapted = run(native, 'review', corpus, '--candidate', current, '--html', root / 'adaptation.html')
    save('adaptation.json', adapted)
    assert adapted['totals']['compared'] == 32
    assert adapted['totals']['outcomeChanged'] == adapted['totals']['stateChanged'] == 0
    assert adapted['totals']['unavailable'] == adapted['totals']['baselineMismatch'] == 0
    faults = run(native, 'review', corpus, '--candidate', faulty, '--html', root / 'fault-review.html')
    save('fault-review.json', faults)
    assert faults['totals']['outcomeChanged'] == 2
    assert faults['totals']['unavailable'] == faults['totals']['baselineMismatch'] == 0

    alias = root / 'alias.gwt'
    body = '  IF flag\n    REQUIRE box.value is present\n  ELSE\n    REQUIRE box.value is present\n'
    source = 'RECORD Box\n  value: optional<integer>\nREQUEST choose\n  GIVEN box is Box\n  GIVEN replacement is Box\n  GIVEN flag is boolean\n  WHEN choose box through box with replacement if flag\n  OUTPUT box is Box\nWHEN choose <box> through <alias> with <replacement> if <flag>\n  GIVEN box is Box\n  AND alias is Box\n  AND replacement is Box\n  AND flag is boolean\n' + body + '  set alias to replacement\n'
    alias.write_text(source)
    redundant = root / 'redundant.gwt'
    redundant.write_text(source.replace('  set alias to replacement\n', '  REQUIRE box.value is present\n'))
    compatibility = []
    for flag in (False, True):
        data = save(f'alias-input-{flag}.json', {'box': {'value': 1}, 'replacement': {}, 'flag': flag})
        for path in (alias, redundant):
            old = run(previous, 'capture', path, '--request', 'choose', '--input', data)
            assert old['record']['observed']['ok']
            original = save(f'old-{path.stem}-{flag}.json', old)
            before = original.read_bytes()
            proposal = run(native, 'migrate', original, '--previous-engine', previous, expected=1 if path == redundant else 0)
            save(f'migration-{path.stem}-{flag}.json', proposal)
            assert not proposal['approved'] and original.read_bytes() == before
            if path == alias:
                assert proposal['status'] == 'observation_changed'
                observed = proposal['candidate']['record']['observed']
                assert not observed['ok'] and observed['diagnostic']['code'] == 'presence_mutation'
                assert observed['state']['box']['value'] == 1
                assert not any(event['operation'] == 'set' for event in observed['events'])
                candidate = save(f'candidate-alias-{flag}.json', proposal['candidate'])
                assert run(native, 'replay', candidate)['verified']
            else:
                assert proposal['status'] == 'candidate_unavailable'
            compatibility.append({'kind': path.stem, 'flag': flag, 'status': proposal['status']})

    portfolio = Path('evaluations/native_editor/2026-10-16-cli-limits/workflow')
    for index in range(57):
        original = portfolio / f'migrated-{index}.json'
        before = original.read_bytes()
        proposal = run(native, 'migrate', original, '--previous-engine', previous)
        assert proposal['status'] == 'observation_preserved' and not proposal['approved']
        assert original.read_bytes() == before
        save(f'portfolio-migration-{index}.json', proposal)
        candidate = save(f'portfolio-candidate-{index}.json', proposal['candidate'])
        assert run(native, 'replay', candidate)['verified']
    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha for path, sha in hashes.items())
    result = {'executableSha256': hashes, 'policyInputs': 32, 'preservedPolicyEngineTransitions': 32,
              'preservedRetainedPortfolioCases':57, 'adaptationTotals':adapted['totals'], 'faultTotals':faults['totals'],
              'compatibilityChanges':compatibility, 'originalCasesUnchanged':True, 'proposalsApproved':False,
              'humanParticipants':0, 'browserValidation':'pending; browser unavailable'}
    save('qualification.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
