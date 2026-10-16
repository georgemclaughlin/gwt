"""Exercise the complete experiment with synthetic provider replies and real containers."""
import argparse
import hashlib
import json
from pathlib import Path

from .corpus import source_path
from .experiment import run_experiment, write_json


class FixtureProvider:
    metadata = {'provider': 'synthetic-fixture-responses', 'synthetic': True, 'liveModelCalls': 0}

    def __call__(self, body):
        assert body['tools'] == [] and body['tool_choice'] == 'none'
        task = json.JSONDecoder().raw_decode(body['input'].split('TASK\n', 1)[1])[0]
        domain = task['caseId'].split('-')[2]
        revision = 'faulty' if domain == 'allocation' else 'correct'
        if domain == 'refund' and 'PREVIOUS RESPONSE' not in body['input']:
            revision = 'baseline'
        source = source_path(domain, revision, task['language']).read_text()
        result = {'id': 'synthetic-' + task['caseId'], 'model': 'synthetic-fixture', 'status': 'completed',
                  'usage': None, 'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                    'content': [{'type': 'output_text', 'text': json.dumps(
                        {'action': 'code', 'source': source, 'clarifications': []})}]}]}
        return {'httpStatus': 200, 'requestId': None, 'durationSeconds': None, 'rawBody': json.dumps(result)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualification', type=Path, required=True)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    settings = {'model': 'synthetic-fixture', 'reasoningEffort': 'medium', 'maximumAttempts': 3,
                'maximumOutputTokens': 16000, 'providerSocketTimeoutSeconds': 300, 'executionTimeoutSeconds': 120}
    report = run_experiment(args.qualification, args.native, args.image, args.output, FixtureProvider(), settings)
    for scores in report['metrics'].values():
        assert scores == {'trials': 15, 'missing': 0, 'firstPassSucceeded': 9,
                          'finalSucceeded': 12, 'repairedTrials': 3, 'recoveredTrials': 3}, scores
    state = json.loads((args.output / 'run.json').read_text())
    assert state['completedCalls'] == 36
    assert state['status'] == 'complete'
    assert all(row['usage'] is None for row in state['calls'])
    for row in report['cases']:
        if row['pairId'] == 'allocation':
            assert len(row['attempts']) == 1
            scores = row['attempts'][0]['scores']
            assert scores['public'] == {'passed': 2, 'total': 2}
            assert scores['withheld']['total'] - scores['withheld']['passed'] == 380
    result = {'liveModelCalls': 0, 'humanParticipants': 0, 'syntheticProviderResponses': 36,
              'metrics': report['metrics'], 'qualifierSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    write_json(args.output / 'qualification.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
