"""Qualify early-return facts, a nested-source refactor, and a guard migration."""
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

    original = Path('examples/native_early_returns/rules.gwt').read_text()
    source, candidate, nested = output / 'rules.gwt', output / 'candidate.gwt', output / 'nested-rules.gwt'
    source.write_text(original)
    candidate.write_text(original.replace('age_days > 30', 'age_days >= 30'))
    # Equivalent old-style rule, explicitly frozen rather than reconstructed from
    # execution observations. The old engine checks this nested control flow.
    start = original.index('  IF not facts.allow_exchanges')
    end = original.index('\nSCENARIO ', start)
    nested_body = '''  IF not facts.allow_exchanges
    RETURN "disabled"
  ELSE
    IF facts.proof is absent
      RETURN "missing_proof"
    ELSE
      IF facts.proof.kind != "receipt"
        RETURN "gift_route"
      ELSE
        IF not facts.proof.verified
          RETURN "unverified"
        ELSE
          IF facts.proof.age_days < 0
            RETURN "invalid_age"
          ELSE
            IF facts.proof.age_days > 30
              RETURN "outside_window"
            ELSE
              RETURN "eligible"
'''
    nested.write_text(original[:start] + nested_body + original[end:])
    validation = run(native, 'validate', source, '--html', output / 'validation.html')
    assert validation['ok']
    write('validation.json', validation)
    proofs = [None, {'kind': 'gift', 'reference': 'G'}] + [
        {'kind': 'receipt', 'age_days': age, 'verified': verified}
        for age in [-1, 0, 30, 31] for verified in [False, True]]
    cases, adapted, expectations = [], [], []
    for allowed in [False, True]:
        for proof in proofs:
            index = len(cases)
            expected = ('disabled' if not allowed else 'missing_proof' if proof is None else
                        'gift_route' if proof['kind'] == 'gift' else 'unverified' if not proof['verified'] else
                        'invalid_age' if proof['age_days'] < 0 else 'outside_window' if proof['age_days'] > 30 else 'eligible')
            input_path = write(f'input-{index}.json', {'facts': {'allow_exchanges': allowed, 'proof': proof}})
            case = run(native, 'capture', source, '--request', 'assess exchange', '--input', input_path)
            observed = case['record']['observed']
            assert observed['ok'] and observed['result'] == {'decision': expected}
            path = write(f'case-{index}.json', case)
            replay = run(native, 'replay', path)
            assert replay['verified'] and replay['actual'] == observed
            write(f'replay-{index}.json', replay)
            cases.append(path)
            expectations.append({'case': index, 'input': json.loads(input_path.read_text()), 'expected': {'decision': expected}})

            prior = run(previous, 'capture', nested, '--request', 'assess exchange', '--input', input_path)
            assert prior['record']['observed']['ok'] and prior['record']['observed']['result'] == {'decision': expected}
            assert prior['record']['observed']['state'] == observed['state']
            prior_path = write(f'nested-previous-{index}.json', prior)
            prior_bytes = prior_path.read_bytes()
            migration = run(native, 'migrate', prior_path, '--previous-engine', previous)
            assert migration['status'] == 'observation_preserved'
            assert prior_path.read_bytes() == prior_bytes
            write(f'nested-migration-{index}.json', migration)
            adapted.append(write(f'nested-candidate-{index}.json', migration['candidate']))
    assert len(cases) == 20
    write('independent-expectations.json', expectations)
    corpus = write('corpus.json', run(native, 'corpus', *cases))
    review = run(native, 'review', corpus, '--candidate', candidate, '--html', output / 'review.html')
    write('review.json', review)
    assert review['totals']['compared'] == 20 and review['totals']['outcomeChanged'] == 1, review['totals']
    assert review['totals']['baselineMismatch'] == review['totals']['unavailable'] == review['totals']['candidateFailed'] == 0
    adapted_corpus = write('nested-corpus.json', run(native, 'corpus', *adapted))
    refactor = run(native, 'review', adapted_corpus, '--candidate', source, '--html', output / 'refactor.html')
    write('refactor.json', refactor)
    totals = refactor['totals']
    assert totals['compared'] == 20 and totals['outcomeChanged'] == totals['stateChanged'] == 0, totals
    assert totals['baselineMismatch'] == totals['unavailable'] == totals['candidateFailed'] == 0

    guard = output / 'guarded-alias.gwt'
    guard.write_text('RECORD Box\n  value: optional<integer>\nREQUEST choose\n  GIVEN box is Box\n  GIVEN replacement is Box\n  WHEN LET answer be choose box through box with replacement\n  OUTPUT box is Box\n  OUTPUT answer is integer\nWHEN choose <box> through <alias> with <replacement>\n  GIVEN box is Box\n  AND alias is Box\n  AND replacement is Box\n  THEN returns integer\n  IF box.value is absent\n    RETURN -1\n  set alias to replacement\n  RETURN 0\n')
    input_path = write('guard-input.json', {'box': {'value': 1}, 'replacement': {}})
    old = run(previous, 'capture', guard, '--request', 'choose', '--input', input_path)
    assert old['record']['observed']['ok'] and old['record']['observed']['result'] == {'box': {'value': None}, 'answer': 0}
    old_path = write('previous-guard-case.json', old)
    original_case = old_path.read_bytes()
    migration = run(native, 'migrate', old_path, '--previous-engine', previous)
    write('guard-migration.json', migration)
    assert migration['status'] == 'observation_changed'
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
              'policyCases': len(cases), 'reviewTotals': review['totals'], 'refactorTotals': totals,
              'preservedNestedEngineTransitions': len(adapted), 'guardEngineChange': migration['status'],
              'previousCasesUnchanged': True, 'candidateGuardReplayVerified': True, 'reviewApproved': False}
    write('qualification.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
