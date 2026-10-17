"""Prepare the delivery walkthrough, checking explicit expectations and leaving review pending."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def prepare(native, output):
    native, output = Path(native).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)

    def invoke(*arguments, allowed=(0,)):
        process = subprocess.run([str(native), *map(str, arguments)], cwd=ROOT,
                                 capture_output=True, text=True, timeout=60)
        if process.returncode not in allowed:
            raise RuntimeError(process.stdout + process.stderr)
        return json.loads(process.stdout)

    def save(name, value):
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

    baseline = ROOT / 'examples/native_delivery/rules.gwt'
    candidate = HERE / 'candidate.gwt'
    expected = json.loads((HERE / 'cases.json').read_text())
    save('version.json', invoke('version', '--json'))
    for label, source in [('baseline', baseline), ('candidate', candidate)]:
        save(f'{label}-validation.json', invoke('validate', source))
        (output / f'{label}.gwt').write_bytes(source.read_bytes())
    entries = []
    for probe in expected:
        input_path = output / f'{probe["id"]}.input.json'
        save(input_path.name, probe['input'])
        case = invoke('capture', baseline, '--request', 'quote delivery', '--input', input_path)
        observed = case['record']['observed']
        if 'failure' in probe:
            assert not observed['ok'] and observed['diagnostic']['code'] == probe['failure']
        else:
            assert observed['ok'] and observed['result'] == probe['baseline'], probe['id']
        save(f'{probe["id"]}.case.json', case)
        entries.append({'id': probe['id'], 'label': probe['label'], 'case': case})
    save('corpus.json', {'kind': 'gwt.native-corpus', 'schemaVersion': 1, 'cases': entries})
    report = invoke('review', output / 'corpus.json', '--candidate', candidate,
                    '--html', output / 'review.html',
                    '--decisions-template', output / 'pending-decisions.json')
    save('review.json', report)
    assert report['complete'] and report['totals']['total'] == len(expected)
    changed = []
    for row, probe in zip(report['cases'], expected, strict=True):
        assert row['id'] == probe['id']
        observed = row['comparison']['candidate']
        if 'failure' in probe:
            assert not observed['ok'] and observed['diagnostic']['code'] == probe['failure']
        else:
            assert observed['ok'] and observed['result'] == probe['candidate'], probe['id']
        if row['comparison']['changes']['outcome']:
            changed.append(probe['id'])
    assert changed == ['new-band', 'new-limit'], changed
    decisions = json.loads((output / 'pending-decisions.json').read_text())
    assert all(row['status'] == 'pending' for row in decisions['decisions'])
    assessment = invoke('assess-review', output / 'corpus.json', '--candidate', candidate,
                        '--decisions', output / 'pending-decisions.json', allowed=(1,))
    assert assessment['pending'] == len(expected) and assessment['accepted'] == 0
    assert assessment['allAccepted'] is False
    save('pending-assessment.json', assessment)
    save('expectations.json', expected)
    summary = {'kind': 'native-delivery-walkthrough', 'cases': len(expected),
               'changedOutcomes': changed, 'expectedFailures': ['invalid-weight'],
               'reviewDecisions': 'all pending', 'humanParticipants': 0,
               'nativeSha256': hashlib.sha256(native.read_bytes()).hexdigest(),
               'sourceSha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in (baseline, candidate, HERE / 'cases.json', Path(__file__))},
               'reviewTotals': report['totals']}
    save('summary.json', summary)
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='new output directory')
    parser.add_argument('--native', type=Path, default=ROOT / 'target/debug/gwt')
    args = parser.parse_args()
    print(json.dumps(prepare(args.native, args.output), indent=2))
