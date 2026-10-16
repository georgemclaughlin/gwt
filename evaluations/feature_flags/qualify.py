"""Independent feature-flag policy and typed-reason adaptation qualification."""
import argparse
from copy import deepcopy
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import tempfile

from gwtlang.runtime import GwtError, Runtime, parse_program


SOURCE = Path('examples/pressure_tests/feature_flag_rollout.gwt')
REQUEST = 'evaluate flag'


def override(enabled, reason='match', account='acct', flag='dashboard'):
    return dict(account_id=account, flag_key=flag, enabled=enabled, reason=reason)


def rule(segment, percent, enabled=True):
    return dict(segment=segment, percent=percent, enabled=enabled)


def probes():
    overrides = [[], [override(True, account='other')], [override(True, flag='other')],
                 [override(False)], [override(True)],
                 [override(False, 'first'), override(True, 'second')],
                 [override(True, 'first'), override(False, 'second')]]
    rules = [[], [rule('all', 0)], [rule('all', 100)], [rule('beta', 50)],
             [rule('all', 100, False), rule('beta', 50)],
             [rule('all', 0), rule('all', 100, False)],
             [rule('internal', 100), rule('all', 100, False), rule('beta', 50)]]
    for index, (account, kill, segment, bucket, exceptions, rollout) in enumerate(itertools.product(
            (False, True), (False, True), ('internal', 'beta', 'paid', 'free'),
            (-1, 0, 1, 49, 50, 51, 100, 101), overrides, rules)):
        yield f'flag-{index:04d}', {'request': dict(account_id='acct', flag_key='dashboard',
            segment=segment, bucket=bucket, account_enabled=account, kill_switch_active=kill,
            overrides=deepcopy(exceptions), rollout_rules=deepcopy(rollout))}


def expected(data):
    request = data['request']
    matching = [o for o in request['overrides'] if
                (o['account_id'], o['flag_key']) == (request['account_id'], request['flag_key'])]
    selected = matching[0] if matching else None
    applicable = [r for r in request['rollout_rules'] if r['segment'] in ('all', request['segment'])]
    enabled = any(r['enabled'] and request['bucket'] <= r['percent'] for r in applicable)
    disabled = any(not r['enabled'] for r in applicable)
    # Decision table: enabled matching rules outrank disabled fallback rules,
    # even if a disabled rule appears first. Invalid buckets precede all gates.
    table = [
        (request['bucket'] < 0 or request['bucket'] > 100, 'invalid_bucket', 'needs_review', False, False, False, False, []),
        (not request['account_enabled'], 'account_disabled', 'disabled', False, False, False, False, []),
        (request['kill_switch_active'], 'kill_switch', 'disabled', False, False, False, True, []),
        (selected is not None, 'override_enabled' if selected and selected['enabled'] else 'override_disabled',
         'enabled' if selected and selected['enabled'] else 'disabled', bool(selected and selected['enabled']), True, False, False,
         [selected['reason']] if selected else []),
        (enabled, 'rollout_rule_enabled', 'enabled', True, False, True, False, []),
        (disabled, 'rollout_rule_disabled', 'disabled', False, False, True, False, []),
        (True, 'no_matching_rule', 'disabled', False, False, False, False, []),
    ]
    _, reason, status, enabled, matched_override, matched_rule, blocked, notes = next(row for row in table if row[0])
    return dict(enabled=enabled, matched_override=matched_override, matched_rule=matched_rule,
                blocked_by_kill_switch=blocked, reasons=notes + [reason], status=status, reason=reason)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--before', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    native = args.native.resolve()
    before, after = args.before.read_text(), SOURCE.read_text()
    old, new = [Runtime(parse_program(source)) for source in (before, after)]
    observations = []
    selected = {}
    with tempfile.TemporaryDirectory(prefix='gwt-feature-flags-') as temp:
        input_path = Path(temp) / 'input.json'
        for name, value in probes():
            want = expected(value)
            for runtime in (old, new):
                actual = runtime.run_json(deepcopy(value), REQUEST).scenarios[0].returned_state['decision']
                # This output contains no numbers: preserve exact JSON scalar types.
                assert json.dumps(actual, sort_keys=True) == json.dumps(want, sort_keys=True), (name, actual, want)
            input_path.write_text(json.dumps(value))
            run = subprocess.run([str(native), 'run', str(SOURCE), '--request', REQUEST, '--input', str(input_path)],
                                 text=True, capture_output=True, timeout=15)
            payload = json.loads(run.stdout)
            assert run.returncode == 0 and payload['ok'] and payload['result'] == {'decision': want}, (name, payload)
            record = dict(id=name, input=value, expected=want, allThreeExecutionsMatch=True)
            observations.append(record)
            selected.setdefault(want['reason'], record)
    assert len(observations) == 6272
    (output/'observations.json').write_text(json.dumps(observations, indent=2)+'\n')
    (output/'review-selection.json').write_text(json.dumps(list(selected.values()), indent=2)+'\n')

    # The helper boundary is intentionally narrower. Observe partial writes,
    # not just the exception, for a previously unchecked arbitrary reason.
    appended = '''
REQUEST invalid reason
  GIVEN decision is FlagDecision
  WHEN enable flag with "unrecognized" into decision
  OUTPUT decision is FlagDecision
'''
    initial = dict(enabled=False, matched_override=False, matched_rule=False,
                   blocked_by_kill_switch=False, reasons=[], status='new', reason='new')
    compatibility = []
    for label, source in [('before', before), ('after', after)]:
        runtime = Runtime(parse_program(source + appended))
        try:
            runtime.run_json({'decision': deepcopy(initial)}, 'invalid reason')
        except GwtError as error:
            compatibility.append(dict(version=label, error=str(error), state=runtime.state))
        else:
            raise AssertionError('Unknown reason was accepted')
    assert compatibility[0]['state']['decision']['enabled'] is True
    assert compatibility[0]['state']['decision']['status'] == 'enabled'
    assert compatibility[1]['state']['decision'] == initial
    (output/'helper-boundary.json').write_text(json.dumps({'appendedSource':appended,'input':{'decision':initial},'observations':compatibility},indent=2)+'\n')
    report = dict(inputs=len(observations), executions=len(observations)*3,
                  outputReasons=sorted(selected), nativeExecutable=str(native),
                  nativeSha256=hashlib.sha256(native.read_bytes()).hexdigest(),
                  beforeSha256=hashlib.sha256(before.encode()).hexdigest(),
                  afterSha256=hashlib.sha256(after.encode()).hexdigest(), humanParticipants=0)
    (output/'qualification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
