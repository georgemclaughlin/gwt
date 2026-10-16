"""Verify execution preservation while compiler navigation metadata changes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--previous-engine', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    native, previous, baseline, output = (getattr(args, name).resolve() for name in ['native', 'previous_engine', 'baseline', 'output'])
    output.mkdir(parents=True, exist_ok=False)
    commands = []

    def run(executable, *arguments):
        command = [str(executable), *map(str, arguments)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=30)
        commands.append({'command': command, 'exitCode': result.returncode})
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)

    cases = []
    for name in ['missing', 'confirmed-email', 'unconfirmed-email', 'sms-consent', 'sms-no-consent', 'pickup-allowed', 'pickup-disabled', 'sms-empty-number', 'guarded-alias-case']:
        case = output / (name + '.json')
        case.write_bytes((baseline / case.name).read_bytes())
        cases.append(case)
    validation = json.loads((baseline / 'validation.json').read_text())
    assert validation['ok'] and len(validation['results']) == 7
    for index, row in enumerate(validation['results']):
        case = run(previous, 'capture', baseline / 'rules.gwt', '--scenario', row['name'])
        assert case['record']['observed']['ok']
        path = output / f'scenario-{index}.json'
        path.write_text(json.dumps(case, indent=2) + '\n')
        cases.append(path)
    checks = []
    for case in cases:
        before = case.read_bytes()
        migration = run(native, 'migrate', case, '--previous-engine', previous)
        assert migration['status'] == 'observation_preserved', migration['observationDifferences']
        assert migration['baselineVerification'] == 'trusted_previous_engine_replay'
        assert migration['observationDifferences'] == [] and not migration['observationDifferencesTruncated']
        assert not any(migration['changes'].values())
        assert migration['original']['record']['observed'] == migration['candidate']['record']['observed']
        assert migration['original']['record']['engine'] != migration['candidate']['record']['engine']
        assert case.read_bytes() == before
        path = output / (case.stem + '-migration.json')
        path.write_text(json.dumps(migration, indent=2) + '\n')
        checks.append({'case': case.name, 'status': migration['status'], 'fullObservationEqual': True, 'originalUnchanged': True})
    report = {'ok': True, 'native': str(native), 'previousEngine': str(previous),
              'nativeSha256': hashlib.sha256(native.read_bytes()).hexdigest(),
              'previousEngineSha256': hashlib.sha256(previous.read_bytes()).hexdigest(),
              'requestCases': 9, 'scenarioCases': 7, 'checks': checks, 'commands': commands}
    (output / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'ok': True, 'fullObservationsPreserved': len(checks), 'output': str(output)}))


if __name__ == '__main__':
    main()
