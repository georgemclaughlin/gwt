"""Audit retained CLI experiment records without model calls or candidate execution."""
import argparse
import hashlib
import json
from pathlib import Path

from .codex_provider import cli_request, normalize_events
from .experiment import prompt_for, write_json
from .provider import decode_response
from .scorer import strict_json
from .study import partition


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root):
    root = Path(root)
    load = lambda path: strict_json(path.read_bytes())
    state, seal, report = [load(root / name) for name in ('run.json', 'seal.json', 'report.json')]
    if state['status'] != 'complete' or state['phase'] != 'complete':
        raise ValueError('experiment is not complete')
    assert state['provider']['provider'] == 'codex-cli'
    assert sha(root / 'responses.jsonl') == seal['responsesSha256'] == state['sealedResponsesSha256']
    assert report['experiment']['responsesSha256'] == seal['responsesSha256']
    identities = state['identities']
    for name, key in [('tasks.jsonl', 'taskSha256'), ('corpus.json', 'corpusSha256'),
                      ('qualification.json', 'qualificationSha256')]:
        assert sha(root / ('frozen-' + name)) == identities[key]
    tasks = [strict_json(line) for line in (root / 'frozen-tasks.jsonl').read_text().splitlines()]
    responses = [strict_json(line) for line in (root / 'responses.jsonl').read_text().splitlines()]
    assert len(responses) == seal['attempts'] == seal['providerCalls'] == state['completedCalls']
    assert len(tasks) == state['scheduledTrials'] == len(report['cases'])
    by_id = {task['caseId']: task for task in tasks}
    previous, feedback = {}, {}
    settings = state['settings']
    for response, call in zip(responses, state['calls'], strict=True):
        case_id, attempt = response['caseId'], response['attempt']
        assert (case_id, attempt) == (call['caseId'], call['attempt'])
        folder = root / 'calls' / f'{case_id}-{attempt}'
        request, transport, public = [load(folder / name) for name in
                                       ('request.json', 'transport.json', 'public-feedback.json')]
        expected_prompt = prompt_for(by_id[case_id], previous.get(case_id), feedback.get(case_id))
        assert request == cli_request(expected_prompt, model=settings['model'],
                                     reasoning_effort=settings['reasoningEffort'], maximum_output_tokens=None)
        assert transport['transportError'] is None and transport['exitCode'] == 0
        normalized = normalize_events(transport['stdout'], transport['finalMessage'])
        assert normalized == strict_json(transport['rawBody'])
        if not response.get('generationError'):
            assert {key: response[key] for key in ('action', 'source', 'clarifications')} == decode_response(normalized)
        assert normalized['usage'] == call['usage']
        assert call['returnedModel'] is None
        previous[case_id], feedback[case_id] = response, public['feedback']
    specs = {spec['id']: spec for spec in load(root / 'frozen-corpus.json')}
    response_map = {(row['caseId'], row['attempt']): row for row in responses}
    for case in report['cases']:
        for attempt in case['attempts']:
            response = response_map[(case['caseId'], attempt['attempt'])]
            assert hashlib.sha256(response['source'].encode()).hexdigest() == attempt['sourceSha256']
            execution_path = root / 'executions' / f'withheld-{case["caseId"]}-{attempt["attempt"]}.json'
            if response.get('generationError') or not response['source'].strip() or response['action'] != 'code':
                assert not attempt['success']
                continue
            execution = load(execution_path)
            probes = specs[case['pairId']]['probes']
            observations = execution['observations']
            if execution['error']:
                observations = [{'error': execution['error']} for _ in probes]
            assert partition(probes, observations) == attempt['scores']
            expected_success = not execution['error'] and attempt['scores']['all']['passed'] == len(probes)
            assert attempt['success'] == expected_success
    changed_sources = [path for path, digest in state['sourceSha256'].items()
                       if not Path(path).is_file() or sha(Path(path)) != digest]
    return {'kind': 'codex-experiment-artifact-audit', 'schemaVersion': 1,
            'recordedCalls': len(responses), 'scheduledTrials': len(tasks),
            'complete': True, 'publicPromptsReconstructed': True,
            'acceptedToolEvents': 0, 'sealedResponsesVerified': True,
            'scoresMatchRetainedObservations': True, 'sourceFilesDifferNow': changed_sources,
            'metrics': report['metrics'], 'humanParticipants': 0,
            'auditSourceSha256': sha(Path(__file__)),
            'scope': 'Artifact consistency; not a model rerun, independent policy oracle, or human study'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify(args.run)
    if args.output:
        if args.output.exists():
            parser.error('audit output already exists')
        write_json(args.output, result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
