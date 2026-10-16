"""Qualify typed local construction through engine migration and allocation review."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from weighted_allocation_oracle import expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--previous-engine', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    native, previous, output = args.native.resolve(), args.previous_engine.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    original = Path('evaluations/native_editor/2026-10-16-weighted-allocation/policy')
    source = output / 'rules.gwt'
    source.write_text(Path('examples/native_weighted_allocation/rules.gwt').read_text())
    commands = []

    def save(name, data):
        path = output / name
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n')
        return path

    def run(engine, *arguments, exit_code=0):
        command = [str(engine), *map(str, arguments)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        commands.append({'command': command, 'exitCode': result.returncode, 'stderr': result.stderr})
        save('commands.json', commands)
        assert result.returncode == exit_code, result.stdout + result.stderr
        return json.loads(result.stdout)

    save('validation.json', run(native, 'validate', source))
    save('inspection.json', run(native, 'inspect', source))
    migrated, original_hashes = [], {}
    for i in range(52):
        old_case = original / f'baseline-case-{i}.json'
        original_hashes[old_case.name] = hashlib.sha256(old_case.read_bytes()).hexdigest()
        migration = run(native, 'migrate', old_case, '--previous-engine', previous)
        assert migration['status'] == 'observation_preserved' and not migration['approved']
        save(f'migration-{i}.json', migration)
        path = save(f'migrated-{i}.json', migration['candidate'])
        assert run(native, 'replay', path)['verified']
        migrated.append(path)
        inp = original / f'input-{i}.json'
        acceptance = expected(json.loads(inp.read_text())['budget'])
        case = run(native, 'capture', source, '--request', 'allocate budget', '--input', inp)
        observed = case['record']['observed']
        if 'failure' in acceptance:
            assert not observed['ok'] and observed['diagnostic']['code'] == acceptance['failure']
            assert observed['state']['allocation'] == {'shares': [], 'total': '0'}
        else:
            assert observed['ok'] and observed['result'] == acceptance
        assert 'draft' not in observed['state']
        prior_state = dict(migration['candidate']['record']['observed']['state'])
        assert 'draft' in prior_state
        prior_state.pop('draft')
        assert observed['state'] == prior_state
        path = save(f'constructed-{i}.json', case)
        assert run(native, 'replay', path)['verified']
    corpus = save('migrated-corpus.json', run(native, 'corpus', *migrated))
    review = run(native, 'review', corpus, '--candidate', source, '--html', output / 'review.html')
    save('review.json', review)
    totals = review['totals']
    assert totals['compared'] == totals['stateChanged'] == 52, totals
    assert totals['outcomeChanged'] == totals['baselineMismatch'] == totals['unavailable'] == 0, totals
    assert totals['candidateFailed'] == 15, totals
    assert original_hashes == {name: hashlib.sha256((original / name).read_bytes()).hexdigest() for name in original_hashes}

    # A trailing colon in an old returning behavior call now denotes construction.
    legacy = output / 'legacy.gwt'
    legacy.write_text('WHEN produce:\n  THEN returns integer\n  RETURN 7\nREQUEST build\n  WHEN LET answer be produce:\n  OUTPUT answer is integer\n')
    empty = save('empty.json', {})
    old = save('legacy-case.json', run(previous, 'capture', legacy, '--request', 'build', '--input', empty))
    assert run(previous, 'replay', old)['verified']
    before = old.read_bytes()
    refused = run(native, 'migrate', old, '--previous-engine', previous, exit_code=1)
    assert refused['status'] == 'candidate_unavailable' and refused['candidateDiagnostic']['code'] == 'unknown_type'
    assert not refused['approved'] and old.read_bytes() == before
    save('colon-migration.json', refused)
    renamed = output / 'renamed.gwt'
    renamed.write_text(legacy.read_text().replace('produce:', 'produce'))
    old_renamed = save('renamed-case.json', run(previous, 'capture', renamed, '--request', 'build', '--input', empty))
    renamed_bytes = old_renamed.read_bytes()
    migration = run(native, 'migrate', old_renamed, '--previous-engine', previous)
    assert migration['status'] == 'observation_preserved' and not migration['approved']
    assert old_renamed.read_bytes() == renamed_bytes
    candidate = save('renamed-candidate.json', migration['candidate'])
    assert run(native, 'replay', candidate)['verified']
    save('renamed-migration.json', migration)
    save('qualification.json', {'cases': 52, 'engineMigrations': 'all observation_preserved',
                               'reviewTotals': totals, 'baselineHashes': original_hashes,
                               'allMigratedAndConstructedReplaysVerified': True, 'reviewApproved': False,
                               'colonMigration': refused['status'], 'renamedMigration': migration['status'],
                               'nativeSha256': hashlib.sha256(native.read_bytes()).hexdigest()})
    print(json.dumps({'ok': True, 'cases': 52, 'outcomeChanges': 0, 'stateChanges': 52}))


if __name__ == '__main__':
    main()
