"""Qualify an installed native engine's kind-condition policy and revision review."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    native, output = args.native.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    commands = []

    def run(*arguments):
        command = [str(native), *map(str, arguments)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        commands.append({'command': command, 'exitCode': result.returncode})
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout)

    def write(name, value):
        (output / name).write_text(json.dumps(value, indent=2) + '\n')
        return output / name

    original = Path('examples/native_kind_conditions/rules.gwt').read_text()
    source, candidate = output / 'rules.gwt', output / 'candidate.gwt'
    source.write_text(original)
    candidate.write_text(original.replace('and facts.contact.opted_in', 'and not facts.contact.opted_in'))
    write('validation.json', run('validate', source, '--html', output / 'validation.html'))
    cases = []
    for name, allow, contact, expected in [
        ('missing', True, None, ('review', 'none', '')),
        ('confirmed-email', True, {'kind': 'email', 'address': 'orders@example.test', 'confirmed': True}, ('ready', 'email', 'orders@example.test')),
        ('unconfirmed-email', True, {'kind': 'email', 'address': 'orders@example.test', 'confirmed': False}, ('review', 'email', '')),
        ('sms-consent', True, {'kind': 'sms', 'number': '555', 'opted_in': True}, ('ready', 'sms', '555')),
        ('sms-no-consent', True, {'kind': 'sms', 'number': '555', 'opted_in': False}, ('blocked', 'sms', '')),
        ('pickup-allowed', True, {'kind': 'pickup', 'location': 'West counter'}, ('ready', 'pickup', 'West counter')),
        ('pickup-disabled', False, {'kind': 'pickup', 'location': 'West counter'}, ('blocked', 'pickup', '')),
        ('sms-empty-number', True, {'kind': 'sms', 'number': '', 'opted_in': True}, ('ready', 'sms', '')),
    ]:
        input_path = write(name + '-input.json', {'facts': {'allow_pickup': allow, 'contact': contact}})
        case = run('capture', source, '--request', 'review contact', '--input', input_path)
        observed = case['record']['observed']
        assert observed['ok'] and observed['result'] == {'decision': dict(zip(['status', 'channel', 'destination'], expected))}
        path = write(name + '.json', case)
        replay = run('replay', path)
        assert replay['verified']
        write(name + '-replay.json', replay)
        cases.append(path)
    corpus = write('corpus.json', run('corpus', *cases))
    review = run('review', corpus, '--candidate', candidate, '--html', output / 'kind-review.html')
    write('kind-review.json', review)
    totals = review['totals']
    assert totals['compared'] == 8 and totals['outcomeChanged'] == 3, totals
    assert totals['baselineMismatch'] == totals['unavailable'] == totals['candidateFailed'] == 0

    guard = output / 'guarded-alias.gwt'
    guard.write_text('RECORD Contact is one of\n  email:\n    address: text\n  phone:\n    number: text\nREQUEST replace\n  GIVEN contact is Contact\n  GIVEN replacement is Contact\n  WHEN replace contact through contact with replacement\n  OUTPUT contact is Contact\nWHEN replace <contact> through <alias> with <replacement>\n  GIVEN contact is Contact\n  AND alias is Contact\n  AND replacement is Contact\n  IF contact.kind == "email"\n    set alias to replacement\n')
    input_path = write('guarded-alias-input.json', {'contact': {'kind': 'email', 'address': 'before'}, 'replacement': {'kind': 'phone', 'number': 'after'}})
    failed = run('capture', guard, '--request', 'replace', '--input', input_path)
    observed = failed['record']['observed']
    assert not observed['ok'] and observed['diagnostic']['code'] == 'kind_mutation'
    assert observed['state']['contact'] == {'kind': 'email', 'address': 'before'}
    assert not any(event['operation'] == 'set' for event in observed['events'])
    path = write('guarded-alias-case.json', failed)
    replay = run('replay', path)
    assert replay['verified']
    write('guarded-alias-replay.json', replay)
    write('qualification.json', {'native': str(native), 'nativeSha256': hashlib.sha256(native.read_bytes()).hexdigest(),
                                'verifiedPolicyReplays': 8, 'guardFailureVerified': True, 'reviewTotals': totals, 'commands': commands})
    print(json.dumps({'ok': True, 'output': str(output), 'totals': totals}))


if __name__ == '__main__':
    main()
