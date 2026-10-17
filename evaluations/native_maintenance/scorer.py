"""Score frozen maintenance tasks with isolated native-GWT/Python executions."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil

from .isolated import ContainerEvaluator
from .study import exact, partition


def strict_json(text):
    def object_pairs(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError(f'duplicate JSON field: {key}')
            value[key] = item
        return value

    def constant(value):
        raise ValueError(f'nonfinite JSON: {value}')
    return json.loads(text, object_pairs_hook=object_pairs, parse_constant=constant)


def read_file(path, maximum=32 * 1024 * 1024):
    with Path(path).open('rb') as stream:
        raw = stream.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError(f'{path}: input file exceeds {maximum} bytes')
    return raw


def load_tasks(directory):
    directory = Path(directory)
    task_bytes = read_file(directory / 'tasks.jsonl')
    corpus_bytes = read_file(directory / 'corpus.json')
    qualification = strict_json(read_file(directory / 'qualification.json'))
    if hashlib.sha256(task_bytes).hexdigest() != qualification['taskFileSha256']:
        raise ValueError('task file no longer matches its qualification')
    if hashlib.sha256(corpus_bytes).hexdigest() != qualification.get('corpusSha256'):
        raise ValueError('corpus is changed or lacks a qualified digest; rerun trusted fixture qualification')
    tasks = [strict_json(line) for line in task_bytes.splitlines() if line.strip()]
    specs = strict_json(corpus_bytes)
    validate_tasks(tasks, specs)
    worker = [digest for path, digest in qualification.get('sourceSha256', {}).items()
              if path.endswith('evaluations/native_maintenance/worker.py')]
    if len(worker) != 1:
        raise ValueError('qualification must identify its execution worker')
    return tasks, specs, {'taskSha256': hashlib.sha256(task_bytes).hexdigest(),
        'corpusSha256': hashlib.sha256(corpus_bytes).hexdigest(),
        'qualificationSha256': hashlib.sha256(read_file(directory / 'qualification.json')).hexdigest(),
        'qualifiedNativeSha256': qualification['nativeSha256'], 'qualifiedWorkerSha256': worker[0]}


def validate_tasks(tasks, specs):
    if not isinstance(tasks, list) or not tasks or not isinstance(specs, list) or not specs:
        raise ValueError('nonempty frozen tasks and corpus required')
    by_domain = {}
    for spec in specs:
        if spec['id'] in by_domain or not spec['probes']:
            raise ValueError('duplicate domain or empty probes')
        by_domain[spec['id']] = spec
        for probe in spec['probes']:
            if probe['kind'] not in ('changed', 'preserved') or type(probe['public']) is not bool:
                raise ValueError('invalid probe partition')
            if (probe['kind'] == 'preserved') != exact(probe['expected'], probe['baseline']):
                raise ValueError('incorrect changed/preserved classification')
            expected = probe['expected']
            if not isinstance(expected, dict) or not (set(expected) == {'result'} or (set(expected) == {'rejected'} and expected['rejected'] is True)):
                raise ValueError('invalid expected outcome')
    ids, pairs = set(), set()
    for task in tasks:
        case_id = task['caseId']
        pair = (task['pairId'], task['trial'], task['language'])
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', case_id) or case_id in ids or pair in pairs:
            raise ValueError('duplicate or invalid task identity')
        ids.add(case_id)
        pairs.add(pair)
        if task['language'] not in ('gwt', 'python') or type(task['trial']) is not int or task['trial'] < 1:
            raise ValueError('invalid task language/trial')
        spec = by_domain[task['pairId']]
        public = [{'input': row['input'], 'expected': row['expected']} for row in spec['probes'] if row['public']]
        provided = task['context']['publicProbes']
        if task['context']['request'] != spec['request'] or len(provided) != len(public) or any(
                not any(exact(row, counterpart) for counterpart in provided) for row in public):
            raise ValueError('task public probes/request disagree with frozen corpus')
    for domain, trial, _ in pairs:
        if not all((domain, trial, language) in pairs for language in ('gwt', 'python')):
            raise ValueError('missing paired language task')


def grouped_responses(tasks, responses, maximum_attempts):
    if type(maximum_attempts) is not int or maximum_attempts < 1:
        raise ValueError('positive maximum attempts required')
    ids = {task['caseId'] for task in tasks}
    grouped = defaultdict(list)
    for response in responses:
        if not isinstance(response, dict) or response.get('caseId') not in ids:
            raise ValueError('unknown response case ID')
        attempt = response.get('attempt')
        if type(attempt) is not int or not 1 <= attempt <= maximum_attempts:
            raise ValueError('invalid attempt number')
        if response.get('action') not in ('code', 'clarify'):
            raise ValueError('invalid response action')
        grouped[response['caseId']].append(response)
    for rows in grouped.values():
        rows.sort(key=lambda row: row['attempt'])
        if [row['attempt'] for row in rows] != list(range(1, len(rows) + 1)):
            raise ValueError('attempts must be contiguous from one without duplicates')
    return grouped


def score_records(tasks, specs, responses, evaluate, *, public_only=False, maximum_attempts=3, checkpoint=None):
    validate_tasks(tasks, specs)
    grouped = grouped_responses(tasks, responses, maximum_attempts)
    domains = {spec['id']: spec for spec in specs}
    details = []
    for task in tasks:
        probes = [row for row in domains[task['pairId']]['probes'] if not public_only or row['public']]
        attempts = []
        rows = grouped[task['caseId']]
        selected = rows[-1:] if public_only else rows
        for response in selected:
            source = response.get('source')
            if response['action'] != 'code' or not isinstance(source, str) or not source.strip():
                result = {'error': 'missing_code', 'observations': None}
            else:
                # Pass only selected inputs; expected values never reach the evaluator.
                result = evaluate(source, task['language'], task['context']['request'],
                                  [row['input'] for row in probes], task['caseId'], response['attempt'])
            observed = result.get('observations')
            error = result.get('error')
            if error or not isinstance(observed, list) or len(observed) != len(probes):
                error = error or 'invalid_worker_response'
                observed = [{'error': error} for _ in probes]
            counts = partition(probes, observed)
            attempt = {'attempt': response['attempt'], 'success': not error and counts['all']['passed'] == counts['all']['total'],
                       'error': error, 'scores': counts, 'sourceSha256': hashlib.sha256(source.encode()).hexdigest() if isinstance(source, str) else None}
            if public_only:
                diagnostic = {'gate': 'execution', 'message': error}
                if error and result.get('stderr'):
                    diagnostic['details'] = result['stderr'][:2000]
                attempt['feedback'] = ([diagnostic] if error else [
                    {'gate': 'public-probe', 'input': probe['input'], 'expected': probe['expected'], 'actual': actual}
                    for probe, actual in zip(probes, observed) if not exact(actual, probe['expected'])])
            attempts.append(attempt)
        missing = not rows
        details.append({'caseId': task['caseId'], 'pairId': task['pairId'], 'trial': task['trial'], 'language': task['language'],
            'missing': missing, 'attempts': attempts, 'firstPassSuccess': None if public_only else bool(attempts and attempts[0]['success']),
            'finalSuccess': bool(attempts and attempts[-1]['success']),
            'nextAttempt': len(rows) + 1 if public_only and len(rows) < maximum_attempts and (not attempts or not attempts[-1]['success']) else None})
        if checkpoint:
            checkpoint(details)
    metrics = {}
    for language in ('gwt', 'python'):
        rows = [row for row in details if row['language'] == language]
        repaired = [row for row in rows if len(row['attempts']) > 1 and not row['attempts'][0]['success']]
        metrics[language] = {'trials': len(rows), 'missing': sum(row['missing'] for row in rows),
            'firstPassSucceeded': None if public_only else sum(row['firstPassSuccess'] for row in rows),
            'finalSucceeded': sum(row['finalSuccess'] for row in rows),
            'repairedTrials': None if public_only else len(repaired),
            'recoveredTrials': None if public_only else sum(row['finalSuccess'] for row in repaired)}
    return {'kind': 'native-maintenance-public-feedback' if public_only else 'native-maintenance-score',
            'schemaVersion': 1, 'publicOnly': public_only, 'maximumAttempts': maximum_attempts, 'metrics': metrics, 'cases': details}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualification', type=Path, required=True)
    parser.add_argument('--responses', type=Path, required=True)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--image', required=True, help='Existing local Python image; never pulled')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--public-only', action='store_true')
    parser.add_argument('--maximum-attempts', type=int, default=3)
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    source_paths = [Path(__file__), Path(__file__).with_name('isolated.py'), Path(__file__).with_name('study.py')]
    source_hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
    tasks, specs, identities = load_tasks(args.qualification)
    raw = read_file(args.responses)
    responses = [strict_json(line) for line in raw.splitlines() if line.strip()]
    grouped_responses(tasks, responses, args.maximum_attempts)
    args.output.mkdir(parents=True, exist_ok=False)
    evaluator = ContainerEvaluator(args.native, args.image, timeout=args.timeout)
    try:
        if evaluator.metadata['nativeSha256'] != identities['qualifiedNativeSha256']:
            raise ValueError('native executable differs from the qualified fixture engine')
        if evaluator.metadata['workerSha256'] != identities['qualifiedWorkerSha256']:
            raise ValueError('execution worker differs from its fixture qualification')
        identities['responsesSha256'] = hashlib.sha256(raw).hexdigest()
        (args.output / 'responses.jsonl').write_bytes(raw)
        for filename in ('tasks.jsonl', 'corpus.json', 'qualification.json'):
            shutil.copyfile(args.qualification / filename, args.output / ('frozen-' + filename))

        def evaluate(source, language, request, inputs, case_id, attempt):
            result = evaluator.evaluate(source, language, request, inputs)
            (args.output / f'{case_id}-attempt-{attempt}.json').write_text(json.dumps(result, ensure_ascii=False) + '\n')
            return result

        def checkpoint(details):
            (args.output / 'checkpoint.json').write_text(json.dumps({'status': 'running', 'cases': details}, indent=2) + '\n')

        report = score_records(tasks, specs, responses, evaluate, public_only=args.public_only,
                               maximum_attempts=args.maximum_attempts, checkpoint=checkpoint)
        report.update({'identities': identities, 'executionEnvironment': evaluator.metadata})
        if any(hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest for path, digest in source_hashes.items()):
            raise ValueError('scorer source changed during execution')
        report['scorerSourceSha256'] = source_hashes
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        (args.output / 'checkpoint.json').write_text(json.dumps({'status': 'complete', 'report': 'report.json'}) + '\n')
        print(json.dumps({'kind': report['kind'], 'metrics': report['metrics']}))
    finally:
        evaluator.close()


if __name__ == '__main__':
    main()
