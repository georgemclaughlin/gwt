"""Compare the exact-ratio native example with the retained Python policy."""
import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from gwtlang.runtime import Runtime, parse_program
from evaluations.underwriting.fixtures import probes

SOURCE = Path('examples/loan_underwriting/native_rules.gwt')
BEFORE = Path('examples/loan_underwriting/rules.gwt')
REQUEST = 'underwrite loan'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    native = args.native.resolve()
    runtime = Runtime(parse_program(BEFORE.read_text()))
    results, differences, selected = [], [], {}
    numeric = ('principal', 'risk_points', 'interest_rate')
    labels = ('status', 'reason')
    with tempfile.TemporaryDirectory(prefix='gwt-underwriting-') as temporary:
        input_path = Path(temporary)/'input.json'
        for row in probes():
            input_path.write_text(json.dumps(row['input']))
            run = subprocess.run([str(native), 'run', str(SOURCE), '--request', REQUEST, '--input', str(input_path)], text=True, capture_output=True, timeout=15)
            payload = json.loads(run.stdout)
            assert run.returncode == 0 and payload['ok'] and payload['result'] == row['expected'], (row['id'], payload)
            # Python `number` takes JSON numbers; native decimal takes exact strings.
            # Preserve the actual numeric-token input separately: this comparison
            # includes the old host representation, not just source arithmetic.
            def numeric_input(value):
                if isinstance(value, dict):
                    return {k: numeric_input(v) for k, v in value.items()}
                if isinstance(value, list):
                    return [numeric_input(v) for v in value]
                number = Fraction(value)
                return int(number) if number.denominator == 1 else float(number)
            python_input = numeric_input(row['input'])
            prior = runtime.run_json(deepcopy(python_input), REQUEST).scenarios[0].returned_state['decision']
            actual = json.loads(json.dumps(prior, default=str))
            expected = row['expected']['decision']
            changed = [k for k in labels if actual[k] != expected[k]]
            changed += [k for k in numeric if Fraction(str(actual[k])) != Fraction(expected[k])]
            result = dict(id=row['id'], input=row['input'], pythonInput=python_input, nativeExpected=row['expected'], nativeMatches=True,
                          pythonDecision=actual, changedPolicyFields=changed)
            results.append(result)
            if changed: differences.append(result)
            selected.setdefault(expected['reason'], result)
        # Capture actual native cases, including recurring ratios and any observed policy difference.
        selection = list(selected.values()) + [results[-4]] + differences[:3]
        seen = set()
        for row in selection:
            if row['id'] in seen: continue
            seen.add(row['id'])
            input_path.write_text(json.dumps(row['input']))
            case_path = args.output/f"{row['id']}.case.json"
            capture = subprocess.run([str(native), 'capture', str(SOURCE), '--request', REQUEST, '--input', str(input_path)],text=True,capture_output=True,check=True)
            case_path.write_text(capture.stdout)
            replay = subprocess.run([str(native), 'replay', str(case_path)],text=True,capture_output=True,check=True)
            assert json.loads(replay.stdout)['verified']
            (args.output/f"{row['id']}.replay.json").write_text(replay.stdout)
    (args.output/'before.gwt').write_text(BEFORE.read_text())
    for filename, data in [('observations.json',results),('policy-differences.json',differences)]:
        (args.output/filename).write_text(json.dumps(data,indent=2)+'\n')
    summary=dict(inputs=len(results),nativeExecutions=len(results),pythonExecutions=len(results),
                 changedPolicyCases=len(differences),ratioOutputContractChangedForEveryCase=True,
                 capturesReplayed=len(seen),nativeExecutable=str(native),nativeSha256=hashlib.sha256(native.read_bytes()).hexdigest(),
                 beforeSha256=hashlib.sha256(BEFORE.read_bytes()).hexdigest(),afterSha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                 humanParticipants=0)
    (args.output/'qualification.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__ == '__main__': main()
