from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from subprocess import CompletedProcess

from evaluations.native_maintenance.corpus import DOMAINS, task
from evaluations.native_maintenance.scorer import load_tasks, score_records, strict_json, validate_tasks
from evaluations.native_maintenance.study import prepare
from evaluations.native_maintenance.isolated import _remove_owned


class NativeMaintenanceScorerTests(unittest.TestCase):
    def setUp(self):
        self.tasks = prepare(1)
        self.specs = [task(domain) for domain in DOMAINS]

    def test_missing_trials_and_failed_attempts_remain_in_denominators(self):
        calls = []
        chosen = self.tasks[0]
        spec = next(spec for spec in self.specs if spec['id'] == chosen['pairId'])
        responses = [{'caseId': chosen['caseId'], 'attempt': i, 'action': 'code', 'source': source}
                     for i, source in [(1, 'bad'), (2, 'correct')]]

        def evaluate(source, language, request, inputs, case_id, attempt):
            calls.append((inputs, case_id, attempt))
            return {'error': 'timeout', 'observations': None} if source == 'bad' else {
                'error': None, 'observations': [probe['expected'] for probe in spec['probes']]}

        result = score_records(self.tasks, self.specs, responses, evaluate)
        metrics = result['metrics'][chosen['language']]
        self.assertEqual(metrics, {'trials': 5, 'missing': 4, 'firstPassSucceeded': 0,
                                  'finalSucceeded': 1, 'repairedTrials': 1, 'recoveredTrials': 1})
        self.assertEqual(len(calls), 2)
        self.assertEqual(result['cases'][0]['attempts'][0]['error'], 'timeout')
        self.assertEqual(result['cases'][0]['attempts'][0]['scores']['all']['passed'], 0)
        self.assertTrue(result['cases'][0]['finalSuccess'])
        self.assertTrue(result['cases'][1]['missing'])
        self.assertTrue(all(row['nextAttempt'] is None for row in result['cases']), 'withheld scoring must not schedule repairs')

    def test_invalid_response_sequences_are_rejected_before_execution(self):
        record = {'caseId': self.tasks[0]['caseId'], 'attempt': 1, 'action': 'code', 'source': 'pass'}
        variants = [[record, record], [{**record, 'attempt': 2}], [{**record, 'attempt': True}],
                    [{**record, 'attempt': 4}], [{**record, 'caseId': 'unknown'}], [{**record, 'action': 'accept'}]]
        for responses in variants:
            with self.subTest(responses=responses), self.assertRaises(ValueError):
                score_records(self.tasks, self.specs, responses, lambda *args: self.fail('executed malformed response'))

    def test_public_feedback_runs_only_public_inputs_and_keeps_withheld_scores_empty(self):
        chosen = next(row for row in self.tasks if row['pairId'] == 'allocation' and row['language'] == 'gwt')
        spec = next(spec for spec in self.specs if spec['id'] == 'allocation')
        public = [probe for probe in spec['probes'] if probe['public']]
        calls = []

        def evaluate(source, language, request, inputs, *rest):
            calls.append(inputs)
            self.assertEqual(inputs, [probe['input'] for probe in public])
            return {'error': None, 'observations': [probe['expected'] for probe in public]}

        responses = [{'caseId': chosen['caseId'], 'attempt': 1, 'action': 'code', 'source': 'candidate'}]
        report = score_records(self.tasks, self.specs, responses, evaluate, public_only=True)
        row = next(row for row in report['cases'] if row['caseId'] == chosen['caseId'])
        self.assertEqual(len(calls), 1)
        self.assertIsNone(row['firstPassSuccess'])
        self.assertIsNone(row['nextAttempt'])
        self.assertEqual(row['attempts'][0]['feedback'], [])
        self.assertEqual(row['attempts'][0]['scores']['withheld'], {'passed': 0, 'total': 0})
        self.assertEqual(report['kind'], 'native-maintenance-public-feedback')

    def test_execution_errors_clarifications_and_incomplete_observations_cannot_pass(self):
        chosen = self.tasks[0]
        for result in [{'error': 'stdout_limit', 'observations': None},
                       {'error': None, 'observations': []},
                       {'error': None, 'observations': [{'error': 'policy_rejected'}]}]:
            responses = [{'caseId': chosen['caseId'], 'attempt': 1, 'action': 'code', 'source': 'bad'}]
            report = score_records(self.tasks, self.specs, responses, lambda *args: result)
            self.assertFalse(report['cases'][0]['finalSuccess'])
        report = score_records(self.tasks, self.specs, [{'caseId': chosen['caseId'], 'attempt': 1, 'action': 'clarify'}],
                               lambda *args: self.fail('must not execute a clarification'))
        self.assertEqual(report['cases'][0]['attempts'][0]['error'], 'missing_code')

    def test_public_repair_uses_latest_attempt_and_respects_the_declared_attempt_cap(self):
        chosen = self.tasks[0]
        responses = [{'caseId': chosen['caseId'], 'attempt': attempt, 'action': 'code', 'source': str(attempt)} for attempt in (1, 2)]
        calls = []

        def evaluate(source, *args):
            calls.append(source)
            return {'error': 'process_error', 'observations': None, 'stderr': 'SyntaxError: ' + 'x' * 3000}

        report = score_records(self.tasks, self.specs, responses, evaluate, public_only=True)
        row = report['cases'][0]
        self.assertEqual(calls, ['2'])
        self.assertEqual(row['nextAttempt'], 3)
        feedback = row['attempts'][0]['feedback'][0]
        self.assertEqual(feedback['gate'], 'execution')
        self.assertEqual(feedback['message'], 'process_error')
        self.assertTrue(feedback['details'].startswith('SyntaxError:'))
        self.assertEqual(len(feedback['details']), 2000)
        capped = score_records(self.tasks, self.specs, responses, evaluate, public_only=True, maximum_attempts=2)
        self.assertIsNone(capped['cases'][0]['nextAttempt'])

    def test_json_and_corpus_validation_preserve_types_pairing_and_public_boundaries(self):
        for raw in ['{"a":1,"a":2}', '{"x":NaN}', '[Infinity]']:
            with self.assertRaises(ValueError):
                strict_json(raw)
        with self.assertRaises(ValueError):
            validate_tasks(self.tasks[1:], self.specs)
        modified = deepcopy(self.tasks)
        modified[0]['context']['publicProbes'][0]['expected'] = {'result': 'different'}
        with self.assertRaises(ValueError):
            validate_tasks(modified, self.specs)
        specs = deepcopy(self.specs)
        specs[0]['probes'][0]['expected'] = {'rejected': 1}
        with self.assertRaises(ValueError):
            validate_tasks(self.tasks, specs)

    def test_qualified_task_and_corpus_digests_detect_changed_material(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tasks = '\n'.join(json.dumps(row) for row in self.tasks).encode()
            corpus = json.dumps(self.specs).encode()
            (root / 'tasks.jsonl').write_bytes(tasks)
            (root / 'corpus.json').write_bytes(corpus)
            (root / 'qualification.json').write_text(json.dumps({'taskFileSha256': hashlib.sha256(tasks).hexdigest(),
                'corpusSha256': hashlib.sha256(corpus).hexdigest(), 'nativeSha256': 'engine',
                'sourceSha256': {'evaluations/native_maintenance/worker.py': 'worker'}}))
            self.assertEqual(len(load_tasks(root)[0]), 10)
            (root / 'corpus.json').write_bytes(corpus + b' ')
            with self.assertRaises(ValueError):
                load_tasks(root)

    def test_container_removal_race_requires_verified_absence_not_an_arbitrary_error(self):
        progress = CompletedProcess([], 1, '', 'removal of container owned is already in progress')
        present = CompletedProcess([], 0, '[{}]', '')
        absent = CompletedProcess([], 1, '[]', 'error: no such object: owned')
        with patch('evaluations.native_maintenance.isolated.subprocess.run', side_effect=[progress, present, absent]) as run:
            _remove_owned('owned')
            self.assertEqual(run.call_count, 3)
            self.assertTrue(all(call.args[0][-1] == 'owned' for call in run.call_args_list))
        broken = CompletedProcess([], 1, '', 'cannot connect to Docker daemon')
        with patch('evaluations.native_maintenance.isolated.subprocess.run', side_effect=[progress, broken]), self.assertRaises(RuntimeError):
            _remove_owned('owned')
