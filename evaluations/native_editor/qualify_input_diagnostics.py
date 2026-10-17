"""Compare actual engines on nested host input; retain message-only migrations."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess

SOURCE = '''RECORD Line
  amount: decimal
  count: integer
  quality: "new" | "used"
RECORD Contact is one of
  email:
    address: text
  phone:
    number: text
RECORD Facts
  lines: list<optional<Line>>
  contact: optional<Contact>
REQUEST inspect
  GIVEN facts is Facts
  WHEN print "accepted"
  OUTPUT facts is Facts
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--previous-engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    native, previous, output = args.native.resolve(), args.previous_engine.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    source = output / 'rules.gwt'
    source.write_text(SOURCE)
    commands, checks = [], []

    def run(engine, *arguments):
        command = [str(engine), *map(str, arguments)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        commands.append({'command': command, 'exitCode': result.returncode, 'stderr': result.stderr})
        (output / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)

    def save(name, data):
        path = output / name
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
        return path

    def facts(line=None, contact=None):
        return {'facts': {'lines': [None, line if line is not None else {'amount': '0.1', 'count': 3, 'quality': 'new'}], 'contact': contact}}

    probes = [
        ('exact-decimal', facts(), None),
        ('integer-decimal', facts({'amount': 2, 'count': 3, 'quality': 'used'}), None),
        ('valid-kind', facts(contact={'kind': 'email', 'address': 'a'}), None),
        ('boolean-count', facts({'amount': '0.1', 'count': True, 'quality': 'new'}), 'input_type'),
        ('fractional-number', facts({'amount': 0.1, 'count': 3, 'quality': 'new'}), 'input_type'),
        ('missing-amount', facts({'count': 3, 'quality': 'new'}), 'missing_input'),
        ('missing-count', facts({'amount': '0.1', 'quality': 'new'}), 'missing_input'),
        ('unknown-field', facts({'amount': '0.1', 'count': 3, 'quality': 'new', 'extra': 1}), 'unknown_input'),
        ('unknown-quality', facts({'amount': '0.1', 'count': 3, 'quality': 'broken'}), 'input_type'),
        ('wrong-list', {'facts': {'lines': {}, 'contact': None}}, 'input_type'),
        ('missing-kind', facts(contact={}), 'one_of_kind'),
        ('wrong-kind-type', facts(contact={'kind': False}), 'one_of_kind'),
        ('unknown-kind', facts(contact={'kind': 'pager'}), 'one_of_kind'),
        ('missing-facts', {}, 'missing_input'),
        ('invalid-decimal', facts({'amount': '1e2', 'count': 3, 'quality': 'new'}), 'invalid_number'),
    ]
    for name, input_value, expected_code in probes:
        input_path = save(f'{name}-input.json', input_value)
        original = run(previous, 'capture', source, '--request', 'inspect', '--input', input_path)
        prior_path = save(f'{name}-original.json', original)
        prior_bytes = prior_path.read_bytes()
        current = run(native, 'capture', source, '--request', 'inspect', '--input', input_path)
        current_path = save(f'{name}-current.json', current)
        before, after = original['record']['observed'], current['record']['observed']
        for observed in [before, after]:
            assert observed['ok'] == (expected_code is None)
            if expected_code:
                assert observed['diagnostic']['code'] == expected_code
                assert observed['events'] == [] and observed['state'] == {} and observed['output'] == []
            else:
                assert observed['output'] == ['accepted']
                expected = copy.deepcopy(input_value)
                # The integer decimal probe deliberately normalizes to text.
                if name == 'integer-decimal':
                    expected['facts']['lines'][1]['amount'] = '2'
                assert observed['result'] == expected
        changed = before != after
        comparable_before, comparable_after = copy.deepcopy(before), copy.deepcopy(after)
        if expected_code:
            comparable_before['diagnostic'].pop('message')
            comparable_after['diagnostic'].pop('message')
        assert comparable_before == comparable_after, 'Change beyond diagnostic wording'
        migration = run(native, 'migrate', prior_path, '--previous-engine', previous)
        assert migration['status'] == ('observation_changed' if changed else 'observation_preserved')
        assert migration['approved'] is False
        assert migration['candidate']['record']['observed'] == after
        save(f'{name}-migration.json', migration)
        assert prior_path.read_bytes() == prior_bytes
        assert run(native, 'replay', current_path)['verified']
        migrated_path = save(f'{name}-candidate.json', migration['candidate'])
        assert run(native, 'replay', migrated_path)['verified']
        checks.append({'id': name, 'expectedError': expected_code, 'messageChanged': changed,
                       'allOtherObservationFieldsEqual': True, 'migrationStatus': migration['status'],
                       'originalSha256': hashlib.sha256(prior_bytes).hexdigest(),
                       'originalUnchanged': True, 'candidateReplayVerified': True, 'approved': False})
    save('qualification.json', {'previousExecutable': str(previous), 'nativeExecutable': str(native),
                               'checks': checks, 'cases': len(checks),
                               'messageChanges': sum(row['messageChanged'] for row in checks)})
    print(json.dumps({'ok': True, 'cases': len(checks), 'messageChanges': sum(row['messageChanged'] for row in checks)}))


if __name__ == '__main__':
    main()
