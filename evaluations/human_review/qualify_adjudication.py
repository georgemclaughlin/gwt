"""Synthetic CLI rehearsal for manual assessment; never participant evidence."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from .study import prepare, score, write_json


def synthetic_response(packet, key):
    rows = []
    for task, answer in zip(packet['tasks'], key['answers']):
        rows.append({'id': task['id'], 'sourceDigests': task['sourceDigests'], 'status': 'submitted',
                     'predictions': answer['predictions'], 'recommendation': answer['recommendation'],
                     'rationale': 'Synthetic rehearsal explanation: ' + answer['rationaleRubric'],
                     'confidence': 3, 'activeMs': 1000, 'wallMs': 1500,
                     **({'resumeCount': 0} if packet.get('responseSchemaVersion') == 2 else {})})
    return {'schemaVersion': packet.get('responseSchemaVersion', 1), 'packetId': packet['packetId'], 'assignmentId': packet['assignmentId'],
            'purpose': 'rehearsal', 'responseId': packet['assignmentId'] + '-synthetic', 'finished': True,
            'profile': {'role': 'developer', 'priorExposure': 'yes', 'gwtFamiliarity': 3, 'pythonFamiliarity': 3},
            'tasks': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.output
    root.mkdir(parents=True, exist_ok=False)
    sources = [Path(__file__).with_name(name) for name in ('adjudication.py', 'study.py', 'corpus.py', 'qualify_adjudication.py')]
    hashes = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources}
    keys, responses = [], []
    for group, label in [(0, 'complete'), (2, 'partial'), (1, 'missing')]:
        packet, key = prepare(group, 'adjudication-rehearsal-' + label)
        keys.append(key)
        write_json(root / f'{label}-key.json', key)
        if label == 'missing':
            continue
        response = synthetic_response(packet, key)
        if label == 'partial':
            response['finished'] = False
            response['tasks'][0].update(recommendation='unsure', rationale='Synthetic rehearsal: I cannot determine this.')
            response['tasks'][1]['status'] = 'skipped'
            response['tasks'][2]['status'] = 'draft'
            response['tasks'][3].update(status='unseen', activeMs=None, wallMs=None, rationale='', confidence=None,
                                        recommendation=None, predictions={'q1': None, 'q2': None})
        responses.append(response)
        write_json(root / f'{label}-response.json', response)
    common = ['--keys', *(str(root / f'{label}-key.json') for label in ('complete', 'partial', 'missing')),
              '--responses', *(str(root / f'{label}-response.json') for label in ('complete', 'partial')),
              '--assessors', 'synthetic-a', 'synthetic-b']
    commands = []

    def run(command, name, extra=()):
        invocation = [sys.executable, '-m', 'evaluations.human_review.adjudication', command,
                      *common, *extra, '--output', str(root / name)]
        result = subprocess.run(invocation, capture_output=True, text=True, timeout=30)
        commands.append({'command': invocation, 'exitCode': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr})
        write_json(root / f'command-{len(commands)}.json', commands[-1])
        if result.returncode:
            raise RuntimeError(result.stderr)
        return json.loads((root / name).read_text())

    for assessor in ('synthetic-a', 'synthetic-b'):
        sheet = run('prepare', f'{assessor}-blank.json', ['--assessor', assessor])
        faulty_index = 0
        for row in sheet['rows']:
            context = row['context']
            if context['status'] != 'submitted':
                row.update(assessment='unavailable', reason='Synthetic rehearsal: no submitted rationale.')
            elif context['recommendation'] == 'unsure':
                row.update(assessment='uncertain', evidenceQuote='I cannot determine this.',
                           reason='Synthetic uncertainty judgment.')
            elif context['revision'] == 'correct':
                row.update(assessment='supported_approval', evidenceQuote=context['rationale'],
                           reason='Synthetic supported-approval judgment.')
            else:
                faulty_index += 1
                row.update(assessment='missed_defect' if assessor == 'synthetic-b' and faulty_index == 2 else 'recognized_defect',
                           evidenceQuote=context['rationale'], reason='Deliberately synthetic judgment for testing reconciliation.')
        write_json(root / f'{assessor}-filled.json', sheet)
    first = ['--assessments', str(root / 'synthetic-a-filled.json')]
    both = [*first, str(root / 'synthetic-b-filled.json')]
    missing = run('reconcile', 'missing-assessor-report.json', first)
    pending = run('reconcile', 'disagreement-report.json', both)
    resolution = run('prepare-resolution', 'resolution-blank.json', [*both, '--resolver', 'synthetic-resolver'])
    assert len(resolution['rows']) == 1
    resolution['rows'][0].update(assessment='uncertain', evidenceQuote='',
                                 reason='Synthetic resolution retains uncertainty instead of assigning recognition credit.')
    write_json(root / 'resolution-filled.json', resolution)
    final = run('reconcile', 'final-report.json', [*both, '--resolution', str(root / 'resolution-filled.json')])
    assert final['summaries'] == score(keys, responses)['summaries']
    missing_summary = missing['rationaleReview']['summaries']['rehearsal']['overall']
    assert missing_summary['reviewStatusCounts'] == {'single_assessor': 12}
    assert missing_summary['assessorJudgedRecognizedDefects'] == 0
    assert pending['rationaleReview']['summaries']['rehearsal']['overall']['reviewStatusCounts'] == {'consensus': 11, 'needs_resolution': 1}
    summary = final['rationaleReview']['summaries']['rehearsal']['overall']
    assert summary['plannedTasks'] == 12 and summary['submittedTasks'] == 5
    assert summary['assessorJudgedRecognizedDefects'] == 1
    assert summary['finalAssessmentCounts']['unavailable'] == 7
    assert final['rationaleReview']['summaries']['participant']['overall']['plannedTasks'] == 0
    assert all(hashlib.sha256(Path(path).read_bytes()).hexdigest() == value for path, value in hashes.items())
    result = {'kind': 'human-rationale-adjudication-rehearsal', 'humanParticipants': 0, 'liveModelCalls': 0,
              'syntheticSessions': 3, 'syntheticResponses': 2, 'syntheticAssessors': 2,
              'commandsPassed': len(commands), 'summary': summary, 'sourceSha256': hashes,
              'browserValidation': 'not performed; browser runtime reported no available browser',
              'participantPageChanged': False}
    write_json(root / 'qualification.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
