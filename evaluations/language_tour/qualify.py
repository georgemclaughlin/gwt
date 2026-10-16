"""Check a tour refactor against integer-domain expectations and its frozen predecessor.

This is a local semantic qualification, not a human readability experiment.
The supplied native executable is recorded and need not come from the workspace.
"""
import argparse
from copy import deepcopy
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from gwtlang.runtime import Runtime, parse_program

NUMERIC = ('line_count', 'submitted_total', 'approved_total', 'violation_amount')


def facts(limit, lines):
    return {'report': {'employee': 'Ada', 'policy_limit': limit, 'lines': [
        {'description': f'line {index + 1}', 'amount': amount, 'category': 'other',
         'reimbursable': reimbursable}
        for index, (amount, reimbursable) in enumerate(lines)]}}


def expected(input):
    """Independent host arithmetic; no GWT parse, execution, or observed outputs."""
    report = input['report']
    lines, limit = report['lines'], report['policy_limit']
    eligible = [line for line in lines if line['reimbursable'] and line['amount'] <= limit]
    over = [line for line in lines if line['amount'] > limit]
    return {'line_count': len(lines), 'submitted_total': sum(line['amount'] for line in lines),
            'approved_total': sum(line['amount'] for line in eligible),
            'approved_descriptions': [line['description'] for line in eligible],
            'has_violation': bool(over),
            'violation_description': over[0]['description'] if over else '',
            'violation_amount': over[0]['amount'] if over else 0,
            'status': 'needs_review' if over else 'approved',
            'reason': 'line_over_policy_limit' if over else 'within_policy'}


def probes():
    result = []
    for limit in [0, 1, 100]:
        result.append((f'empty-{limit}', facts(limit, [])))
        for first, second, first_flag, second_flag in itertools.product(
                [-1, 0, 1, 99, 100, 101], [-1, 0, 1, 99, 100, 101], [False, True], [False, True]):
            result.append((f'{limit}-{first}-{second}-{int(first_flag)}-{int(second_flag)}',
                           facts(limit, [(first, first_flag), (second, second_flag)])))
    result.append(('original-four-lines', facts(100, [(42, True), (18, True), (225, True), (12, False)])))
    assert len(result) == 436
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--after', type=Path, default=ROOT / 'examples/language_tour/rules.gwt')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    native, before, after = args.native.resolve(), args.before.resolve(), args.after.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    old_text, new_text = before.read_text(), after.read_text()
    old = Runtime(parse_program(old_text, filename=str(before)))
    new = Runtime(parse_program(new_text, filename=str(after)))
    observations = []
    mutant_witnesses = {'inclusive-boundary': [], 'ignore-nonreimbursable': []}
    with tempfile.TemporaryDirectory(prefix='gwt-tour-qualification-') as directory:
        work = Path(directory)
        input_path = work / 'input.json'
        mutations = {
            'inclusive-boundary': new_text.replace('policy_violation.amount > report.policy_limit',
                                                  'policy_violation.amount >= report.policy_limit'),
            'ignore-nonreimbursable': new_text.replace('WHERE policy_violation.amount > report.policy_limit',
                'WHERE policy_violation.reimbursable == true and policy_violation.amount > report.policy_limit'),
        }
        paths = {}
        for name, source in mutations.items():
            assert source != new_text
            paths[name] = work / f'{name}.gwt'
            paths[name].write_text(source)

        def run(path):
            result = subprocess.run([str(native), 'run', str(path), '--request',
                                     'review expense report', '--input', str(input_path)],
                                    capture_output=True, text=True, timeout=10)
            assert result.returncode == 0, (path, result.stderr, result.stdout[:500])
            payload = json.loads(result.stdout)
            assert payload['ok']
            return payload['result']['decision']

        for name, input in probes():
            oracle = expected(input)
            old_result = old.run_json(deepcopy(input), 'review expense report').scenarios[0].returned_state['decision']
            new_result = new.run_json(deepcopy(input), 'review expense report').scenarios[0].returned_state['decision']
            assert old_result == oracle, ('before', name, old_result, oracle)
            assert new_result == oracle, ('after', name, new_result, oracle)
            input_path.write_text(json.dumps(input))
            native_expected = {key: str(value) if key in NUMERIC else value for key, value in oracle.items()}
            native_result = run(after)
            assert native_result == native_expected, ('native', name, native_result, native_expected)
            detected = []
            for mutation, path in paths.items():
                if run(path) != native_expected:
                    mutant_witnesses[mutation].append(name)
                    detected.append(mutation)
            observations.append({'id': name, 'input': input, 'expected': oracle,
                                 'pythonBeforeMatches': True, 'pythonAfterMatches': True,
                                 'nativeMatches': True, 'mutantsDetected': detected})
    assert all(mutant_witnesses.values())
    (args.output / 'observations.json').write_text(json.dumps(observations, indent=2) + '\n')
    report = {'ok': True, 'cases': len(observations), 'pythonBeforeMatches': len(observations),
              'pythonAfterMatches': len(observations), 'nativeMatches': len(observations),
              'mutantsDetected': {name: len(ids) for name, ids in mutant_witnesses.items()},
              'nativeExecutable': str(native), 'nativeSha256': hashlib.sha256(native.read_bytes()).hexdigest(),
              'beforeSha256': hashlib.sha256(before.read_bytes()).hexdigest(),
              'afterSha256': hashlib.sha256(after.read_bytes()).hexdigest(),
              'limitations': 'Integer-domain probes only; no human comprehension or performance claim.'}
    (args.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
