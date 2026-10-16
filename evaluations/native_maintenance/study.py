"""Prepare paired maintenance tasks and qualify trusted references, not model performance."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from .corpus import DOMAINS, GUIDES, source_path, task


def exact(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(exact(actual[key], value) for key, value in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(exact(a, b) for a, b in zip(actual, expected))
    return actual == expected


def prepare(repeats=3):
    if type(repeats) is not int or repeats < 1:
        raise ValueError('repeats must be a positive integer')
    tasks = []
    for trial in range(1, repeats + 1):
        for index, domain in enumerate(DOMAINS):
            spec = task(domain)
            languages = ('gwt', 'python') if (trial + index) % 2 else ('python', 'gwt')
            for language in languages:
                source = source_path(domain, 'baseline', language).read_text()
                tasks.append({'schemaVersion': 1, 'caseId': f'native-maintenance-{domain}-{language}-{trial}',
                    'pairId': domain, 'trial': trial, 'language': language, 'kind': 'maintain',
                    'task': spec['task'], 'contextVariant': 'native-maintenance-guide',
                    'context': {'source': source, 'guide': GUIDES[language],
                        'request': spec['request'], 'publicProbes': spec['publicProbes'],
                        'outcomeContract': 'Public expected outcomes wrap successful return values in result; rejected:true denotes a policy rejection. Do not add this wrapper to the function/request return value.',
                        'executionEngine': 'native-gwt' if language == 'gwt' else 'python'},
                    'responseContract': {'action': 'code', 'source': 'complete replacement source', 'clarifications': []}})
    return tasks


def evaluate(path, language, spec, native):
    worker = Path(__file__).with_name('worker.py').resolve()
    process = subprocess.run([sys.executable, '-I', str(worker), language, str(path.resolve()), str(native)],
        input=json.dumps({'request': spec['request'], 'inputs': [probe['input'] for probe in spec['probes']]}),
        capture_output=True, text=True, timeout=120)
    if process.returncode:
        raise RuntimeError(process.stderr[-2000:])
    values = json.loads(process.stdout)
    if not isinstance(values, list) or len(values) != len(spec['probes']):
        raise ValueError('worker returned the wrong observation count')
    return values


def partition(probes, observations):
    if len(probes) != len(observations):
        raise ValueError('missing observations')
    result = {}
    for name, selected in [('all', lambda p: True), ('changed', lambda p: p['kind'] == 'changed'),
                           ('preserved', lambda p: p['kind'] == 'preserved'),
                           ('public', lambda p: p['public']), ('withheld', lambda p: not p['public'])]:
        flags = [exact(observed, probe['expected']) for probe, observed in zip(probes, observations) if selected(probe)]
        result[name] = {'passed': sum(flags), 'total': len(flags)}
    return result


def qualify(native, output):
    native = native.resolve(strict=True)
    output.mkdir(parents=True, exist_ok=False)
    digest = hashlib.sha256(native.read_bytes()).hexdigest()
    checks, observations, sources, commands = [], {}, {}, []
    code = [Path(__file__), Path(__file__).with_name('corpus.py'), Path(__file__).with_name('worker.py'),
            Path('evaluations/human_review/corpus.py'), Path('evaluations/native_editor/weighted_allocation_oracle.py')]
    sources.update({str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in code})
    specs = [task(domain) for domain in DOMAINS]
    for spec in specs:
        domain = spec['id']
        observations[domain] = {}
        for language in ('gwt', 'python'):
            observations[domain][language] = {}
            for revision in ('baseline', 'correct', 'faulty'):
                path = source_path(domain, revision, language)
                sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
                if language == 'gwt':
                    command = [str(native), 'validate', str(path.resolve()), '--allow-no-scenarios']
                    completed = subprocess.run(command, capture_output=True, text=True, timeout=10)
                    commands.append({'command': command, 'exitCode': completed.returncode})
                    assert completed.returncode == 0, completed.stdout + completed.stderr
                values = evaluate(path, language, spec, native)
                assert not any('error' in value for value in values), (domain, language, revision)
                if revision == 'baseline':
                    assert all(exact(value, probe['baseline']) for value, probe in zip(values, spec['probes'])), (domain, language)
                scored = partition(spec['probes'], values)
                if revision == 'correct':
                    assert scored['all']['passed'] == scored['all']['total'], (domain, language, scored)
                else:
                    assert scored['all']['passed'] < scored['all']['total'], (domain, language, revision)
                if revision == 'baseline':
                    assert scored['changed']['passed'] == 0
                    assert scored['preserved']['passed'] == scored['preserved']['total']
                if domain == 'allocation' and revision == 'faulty':
                    assert scored['public']['passed'] == scored['public']['total']
                    assert scored['withheld']['passed'] < scored['withheld']['total']
                observations[domain][language][revision] = values
                checks.append({'domain': domain, 'language': language, 'revision': revision, 'scores': scored})
                (output / 'checks.json').write_text(json.dumps(checks, indent=2) + '\n')
                print(domain, language, revision, scored['all'], flush=True)
        for revision in ('baseline', 'correct', 'faulty'):
            assert exact(observations[domain]['gwt'][revision], observations[domain]['python'][revision]), (domain, revision)
    for path, expected in sources.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected
    assert hashlib.sha256(native.read_bytes()).hexdigest() == digest
    prepared = prepare()
    (output / 'tasks.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in prepared))
    for name, value in [('corpus.json', specs), ('observations.json', observations), ('commands.json', commands)]:
        (output / name).write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')
    result = {'kind': 'native-maintenance-fixture-qualification', 'schemaVersion': 1,
              'native': str(native), 'nativeSha256': digest, 'domains': len(specs),
              'uniqueProbesPerRevision': sum(len(spec['probes']) for spec in specs),
              'fixtureExecutions': sum(check['scores']['all']['total'] for check in checks),
              'preparedTrials': len(prepared), 'repeatsPerLanguage': 3,
              'liveModelCalls': 0, 'humanParticipants': 0, 'checks': checks,
              'sourceSha256': sources,
              'corpusSha256': hashlib.sha256((output / 'corpus.json').read_bytes()).hexdigest(),
              'taskFileSha256': hashlib.sha256((output / 'tasks.jsonl').read_bytes()).hexdigest()}
    (output / 'qualification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('domains', 'uniqueProbesPerRevision', 'fixtureExecutions', 'preparedTrials', 'liveModelCalls', 'humanParticipants')}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    qualify(args.native, args.output)


if __name__ == '__main__':
    main()
