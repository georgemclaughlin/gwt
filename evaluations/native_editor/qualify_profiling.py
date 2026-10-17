"""Independently account for native profiles and migrate actual retained cases."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess

from qualify_append_evidence import COLLECTOR


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()


def usage():
    return dict(events=0, bytes=0, valueBytes=0, metadataBytes=0)


def account(observed):
    total = usage()
    operations = defaultdict(usage)
    locations = defaultdict(usage)
    for event in observed['events']:
        size = len(encoded(event))
        values = len(encoded(event['value']))
        span = event['span']
        location = tuple(span[key] for key in ('file', 'start', 'end', 'line', 'column'))
        for row in (total, operations[event['operation']], locations[location]):
            row['events'] += 1
            row['bytes'] += size
            row['valueBytes'] += values
            row['metadataBytes'] += size - values
    by_operation = [{'operation': name, 'usage': value} for name, value in
                    sorted(operations.items(), key=lambda item: (-item[1]['bytes'], item[0]))]
    by_location = [{'span': dict(zip(('file', 'start', 'end', 'line', 'column'), span)), 'usage': value}
                   for span, value in sorted(locations.items(), key=lambda item: (-item[1]['bytes'], item[0]))]
    return total, by_operation, by_location


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--previous-engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    native, previous, output = args.native.resolve(), args.previous_engine.resolve(), args.output.resolve()
    assert native.is_file() and previous.is_file()
    output.mkdir(parents=True, exist_ok=False)
    commands = []

    def save(name, value):
        path = output / name
        path.write_bytes(encoded(value) + b'\n')
        return path

    def run(engine, *arguments, expected=None):
        command = [str(engine), *map(str, arguments)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        commands.append({'command': command, 'exitCode': result.returncode, 'stderr': result.stderr})
        save('commands.json', commands)
        value = json.loads(result.stdout)
        if expected is None:
            expected = 0 if value['ok'] else 1
        assert result.returncode == expected, (command, result.stdout, result.stderr)
        return value

    collector = output / 'collector.gwt'
    collector.write_text(COLLECTOR)
    allocation = output / 'allocation.gwt'
    allocation.write_text(Path('examples/native_weighted_allocation/rules.gwt').read_text())
    profiles = []

    def verify(label, source, options):
        ordinary = run(native, 'run', source, *options)
        measured = run(native, 'profile', source, *options)
        assert measured['kind'] == 'gwt.native-profile' and measured['schemaVersion'] == 1
        for key in ('ok', 'diagnostic', 'steps', 'file', 'program', 'programIdentity', 'request'):
            assert measured[key] == ordinary[key], (label, key)
        total, operations, locations = account(ordinary)
        assert measured['evidence'] == total
        assert measured['byOperation'] == operations
        assert measured['byLocation'] == locations
        assert measured == run(native, 'profile', source, *options)
        save(f'{label}-profile.json', measured)
        profiles.append({'id': label, 'ok': ordinary['ok'], 'diagnostic': ordinary['diagnostic'],
                         'evidence': total, 'steps': ordinary['steps'],
                         'ordinaryObservationSha256': hashlib.sha256(encoded(ordinary)).hexdigest()})
        return measured

    for count in (8, 16, 32, 64, 128):
        inp = save(f'collector-{count}-input.json', {'labels': [f'{i:03d}-' + 'x' * 196 for i in range(count)]})
        report = verify(f'collector-{count}', collector, ['--request', 'collect labels', '--input', inp])
        assert report['ok']
    for count in (8, 16, 32, 64):
        inp = save(f'allocation-{count}-input.json', {'budget': {'total': f'0.{count - 1:02d}',
            'recipients': [{'label': str(i), 'weight': 1, 'eligible': True} for i in range(count)]}})
        report = verify(f'allocation-{count}', allocation, ['--request', 'allocate budget', '--input', inp])
        assert report['ok'] == (count <= 16)
        if not report['ok']:
            assert report['diagnostic']['code'] == 'evidence_limit'
            assert report['evidence']['bytes'] <= report['limits']['execution']['evidenceBytes']
    inp = save('unicode-input.json', {'labels': ['café 😀', 'quoted "line"\nnext', '</script>']})
    assert verify('unicode', collector, ['--request', 'collect labels', '--input', inp])['ok']
    inp = save('invalid-input.json', {'labels': [False]})
    report = verify('invalid', collector, ['--request', 'collect labels', '--input', inp])
    assert not report['ok'] and report['evidence'] == usage() and report['steps'] == 0
    inspection = run(native, 'inspect', allocation)
    for index, scenario in enumerate(inspection['scenarios']):
        report = verify(f'scenario-{index}', allocation, ['--scenario', scenario['name']])
        assert report['ok'] and report['scenario'] == scenario['name']

    portfolio = Path('evaluations/native_editor/2026-10-16-evidence-growth/qualification')
    cases = [portfolio / f'allocation-new-{i}.json' for i in range(52)]
    cases += [portfolio / f'new-{i}.json' for i in (8, 16, 32, 64, 128)]
    statuses = Counter()
    for index, path in enumerate(cases):
        original = path.read_bytes()
        assert run(previous, 'replay', path, expected=0)['verified']
        proposal = run(native, 'migrate', path, '--previous-engine', previous, expected=0)
        assert proposal['status'] == 'observation_preserved' and not proposal['approved']
        assert not any(proposal['changes'][key] for key in ('outcome', 'state', 'source', 'evidence'))
        assert proposal['candidate']['record']['observed'] == json.loads(original)['record']['observed']
        assert path.read_bytes() == original
        statuses[proposal['status']] += 1
        save(f'migration-{index}.json', proposal)
        candidate = save(f'candidate-{index}.json', proposal['candidate'])
        assert run(native, 'replay', candidate, expected=0)['verified']

    save('qualification.json', {'profiles': profiles, 'exactAccountingVerified': True,
        'repeatedProfilesIdentical': True, 'migrationStatuses': dict(statuses),
        'allOriginalsUnchanged': True, 'allCandidatesReplay': True, 'approved': False,
        'native': str(native), 'nativeSha256': hashlib.sha256(native.read_bytes()).hexdigest(),
        'previousEngine': str(previous), 'previousSha256': hashlib.sha256(previous.read_bytes()).hexdigest()})
    print(json.dumps({'ok': True, 'profiles': len(profiles), 'migrationStatuses': dict(statuses)}))


if __name__ == '__main__':
    main()
