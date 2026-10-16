"""Frozen model experiment: public repairs first, withheld scoring only after sealing."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil

from .isolated import ContainerEvaluator
from .provider import ResponsesProvider, decode_response, request_body
from .scorer import load_tasks, score_records, strict_json, validate_tasks


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def write_json(path, value):
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def public_task(task):
    # Explicit projection prevents future private task metadata reaching the provider.
    context = task['context']
    return {**{key: deepcopy(task[key]) for key in ('caseId', 'language', 'kind', 'task')},
            'context': {key: deepcopy(context[key]) for key in
                        ('source', 'guide', 'request', 'publicProbes', 'outcomeContract', 'executionEngine')}}


def prompt_for(task, previous=None, feedback=None):
    prompt = ('Complete this maintenance task using only the supplied source, language guide, '
              'intent, and public examples. Return complete replacement source with action code '
              'and an empty clarifications array. Preserve the request entry (GWT) or decide(state) '
              '(Python) and its output contract. No tools or external context are available.\n\n'
              'TASK\n' + json.dumps(public_task(task), ensure_ascii=False, sort_keys=True))
    if previous is not None:
        visible = {key: previous[key] for key in ('action', 'source', 'clarifications')}
        prompt += ('\n\nPREVIOUS RESPONSE\n' + json.dumps(visible, ensure_ascii=False, sort_keys=True)
                   + '\n\nPUBLIC FEEDBACK\n' + json.dumps(feedback, ensure_ascii=False, sort_keys=True)
                   + '\nReturn a complete repaired response. Withheld cases are unavailable.')
    return prompt


def run_loop(tasks, specs, provider, evaluate, output, *, settings, metadata):
    """Provider receives request JSON only; evaluator receives inputs without expected values.

    Output must already exist and be reserved for this run. Infrastructure failures
    stop the experiment without retries. Completed but unusable model responses
    consume an attempt and may receive public response-format feedback.
    """
    validate_tasks(tasks, specs)
    maximum_attempts = settings['maximumAttempts']
    if type(maximum_attempts) is not int or maximum_attempts < 1:
        raise ValueError('positive maximum attempts required')
    output = Path(output)
    (output / 'calls').mkdir()
    (output / 'executions').mkdir()
    responses, calls = [], []
    state = {**metadata, 'settings': settings, 'phase': 'public', 'status': 'running',
             'startedAt': datetime.now(timezone.utc).isoformat(), 'scheduledTrials': len(tasks)}

    def checkpoint():
        text = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in responses)
        temporary = output / 'responses.jsonl.tmp'
        temporary.write_text(text)
        temporary.replace(output / 'responses.jsonl')
        write_json(output / 'run.json', {**state, 'recordedAttempts': len(responses),
                                        'completedCalls': len(calls), 'calls': calls})

    def execute(source, language, request, inputs, case_id, attempt):
        result = evaluate(source, language, request, inputs)
        write_json(output / 'executions' / f'{state["phase"]}-{case_id}-{attempt}.json', result)
        if result.get('error') == 'infrastructure_error':
            raise RuntimeError('candidate execution infrastructure failed')
        return result

    checkpoint()
    try:
        pending = {task['caseId']: (None, []) for task in tasks}
        # Rounds preserve the frozen alternating pair order before every repair round.
        for attempt in range(1, maximum_attempts + 1):
            for task in tasks:
                case_id = task['caseId']
                if case_id not in pending:
                    continue
                previous, feedback = pending[case_id]
                prompt = prompt_for(task, previous, feedback)
                body = request_body(prompt, model=settings['model'], reasoning_effort=settings['reasoningEffort'],
                                    maximum_output_tokens=settings['maximumOutputTokens'])
                call_dir = output / 'calls' / f'{case_id}-{attempt}'
                call_dir.mkdir()
                write_json(call_dir / 'request.json', body)
                state['pendingCall'] = {'caseId': case_id, 'attempt': attempt,
                                        'requestSha256': digest((call_dir / 'request.json').read_bytes())}
                checkpoint()  # Persist intent before a possibly billable request.
                reply = provider(deepcopy(body))
                write_json(call_dir / 'transport.json', reply)
                if reply['httpStatus'] != 200:
                    raise RuntimeError(f'provider HTTP status {reply["httpStatus"]}; no automatic retry')
                try:
                    raw = strict_json(reply['rawBody'])
                except (ValueError, TypeError):
                    raise RuntimeError('provider returned invalid transport JSON') from None
                generation_error = None
                try:
                    response = decode_response(raw)
                except ValueError as error:
                    generation_error = str(error)
                    response = {'action': 'code', 'source': '', 'clarifications': []}
                response = {'caseId': case_id, 'attempt': attempt, **response}
                if generation_error:
                    response['generationError'] = generation_error
                responses.append(response)
                calls.append({'caseId': case_id, 'attempt': attempt, 'requestId': reply.get('requestId'),
                              'responseId': raw.get('id') if isinstance(raw, dict) else None,
                              'returnedModel': raw.get('model') if isinstance(raw, dict) else None,
                              'usage': raw.get('usage') if isinstance(raw, dict) else None,
                              'durationSeconds': reply.get('durationSeconds'),
                              'promptUtf8Bytes': len(prompt.encode()), 'generationError': generation_error})
                state.pop('pendingCall')
                checkpoint()  # Preserve the response before executing candidate code.
                # Pair validation requires both arms; only this case has responses here.
                pair = [row for row in tasks if row['pairId'] == task['pairId'] and row['trial'] == task['trial']]
                report = score_records(pair, specs, [row for row in responses if row['caseId'] == case_id],
                                       execute, public_only=True, maximum_attempts=maximum_attempts)
                detail = next(row for row in report['cases'] if row['caseId'] == case_id)
                feedback = detail['attempts'][-1]['feedback']
                if generation_error:
                    feedback = [{'gate': 'response', 'message': generation_error}]
                write_json(call_dir / 'public-feedback.json', {'caseId': case_id, 'attempt': attempt,
                           'success': detail['finalSuccess'], 'nextAttempt': detail['nextAttempt'], 'feedback': feedback})
                if detail['nextAttempt'] is None:
                    del pending[case_id]
                else:
                    pending[case_id] = (response, feedback)
            if not pending:
                break
        # No provider calls occur after this seal. Full results cannot drive repairs.
        state['phase'] = 'withheld'
        state['sealedResponsesSha256'] = digest((output / 'responses.jsonl').read_bytes())
        write_json(output / 'seal.json', {'responsesSha256': state['sealedResponsesSha256'],
                   'attempts': len(responses), 'providerCalls': len(calls)})
        checkpoint()
        report = score_records(tasks, specs, responses, execute, maximum_attempts=maximum_attempts)
        if digest((output / 'responses.jsonl').read_bytes()) != state['sealedResponsesSha256']:
            raise RuntimeError('sealed responses changed during scoring')
        report['experiment'] = {**metadata, 'settings': settings, 'responsesSha256': state['sealedResponsesSha256']}
        write_json(output / 'report.json', report)
        state.update(status='complete', phase='complete', finishedAt=datetime.now(timezone.utc).isoformat())
        checkpoint()
        return report
    except BaseException as error:
        state.update(status='interrupted', errorType=type(error).__name__)
        checkpoint()
        raise


def run_experiment(qualification, native, image, output, provider, settings):
    tasks, specs, identities = load_tasks(qualification)
    source_paths = [Path(__file__).with_name(name) for name in
                    ('experiment.py', 'provider.py', 'scorer.py', 'isolated.py', 'worker.py', 'study.py')]
    hashes = {str(path): digest(path.read_bytes()) for path in source_paths}
    evaluator = ContainerEvaluator(native, image, timeout=settings['executionTimeoutSeconds'])
    try:
        if evaluator.metadata['nativeSha256'] != identities['qualifiedNativeSha256'] or evaluator.metadata['workerSha256'] != identities['qualifiedWorkerSha256']:
            raise ValueError('native executable or worker differs from qualification')
        output = Path(output)
        output.mkdir(parents=True, exist_ok=False)
        for name, identity in [('tasks.jsonl', 'taskSha256'), ('corpus.json', 'corpusSha256'),
                               ('qualification.json', 'qualificationSha256')]:
            frozen = output / ('frozen-' + name)
            shutil.copyfile(Path(qualification) / name, frozen)
            if digest(frozen.read_bytes()) != identities[identity]:
                raise ValueError('qualification changed while freezing experiment inputs')
        metadata = {'kind': 'native-maintenance-experiment', 'schemaVersion': 1,
                    'identities': identities, 'sourceSha256': hashes, 'provider': provider.metadata,
                    'executionEnvironment': evaluator.metadata}
        def guarded_provider(body):
            if any(digest(Path(path).read_bytes()) != sha for path, sha in hashes.items()):
                raise RuntimeError('experiment source changed')
            return provider(body)
        report = run_loop(tasks, specs, guarded_provider, evaluator.evaluate, output, settings=settings, metadata=metadata)
        if any(digest(Path(path).read_bytes()) != sha for path, sha in hashes.items()):
            state = strict_json((output / 'run.json').read_bytes())
            state.update(status='invalidated', errorType='source_changed')
            write_json(output / 'run.json', state)
            raise RuntimeError('experiment source changed; report is invalidated')
        return report
    finally:
        evaluator.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualification', type=Path, required=True)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--reasoning-effort', required=True)
    parser.add_argument('--maximum-attempts', type=int, default=3)
    parser.add_argument('--maximum-output-tokens', type=int, default=16000)
    parser.add_argument('--provider-socket-timeout', type=float, default=300)
    parser.add_argument('--execution-timeout', type=float, default=120)
    args = parser.parse_args()
    if args.maximum_attempts < 1 or args.maximum_output_tokens < 1 or any(
            not math.isfinite(value) or value <= 0 for value in (args.provider_socket_timeout, args.execution_timeout)):
        parser.error('attempt/token bounds and finite timeouts must be positive')
    settings = {'model': args.model, 'reasoningEffort': args.reasoning_effort,
                'maximumAttempts': args.maximum_attempts, 'maximumOutputTokens': args.maximum_output_tokens,
                'providerSocketTimeoutSeconds': args.provider_socket_timeout,
                'executionTimeoutSeconds': args.execution_timeout}
    provider = ResponsesProvider(socket_timeout=args.provider_socket_timeout)
    report = run_experiment(args.qualification, args.native, args.image, args.output, provider, settings)
    print(json.dumps(report['metrics']))


if __name__ == '__main__':
    main()
