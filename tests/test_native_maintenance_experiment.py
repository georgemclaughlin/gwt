from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from evaluations.native_maintenance.corpus import DOMAINS, task
from evaluations.native_maintenance.experiment import digest, prompt_for, run_experiment, run_loop
from evaluations.native_maintenance.provider import ResponsesProvider, decode_response, request_body
from evaluations.native_maintenance.study import prepare


SETTINGS = {'model': 'explicit-model', 'reasoningEffort': 'medium', 'maximumAttempts': 3,
            'maximumOutputTokens': 16000, 'providerSocketTimeoutSeconds': 300,
            'executionTimeoutSeconds': 120}


def completion(source, **changes):
    return {'id': 'synthetic-response', 'model': 'returned-model', 'status': 'completed',
            'usage': {'input_tokens': 11, 'output_tokens': 12, 'total_tokens': 23},
            'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                        'content': [{'type': 'output_text', 'text': json.dumps(
                            {'action': 'code', 'source': source, 'clarifications': []})}]}], **changes}


def transport(body):
    return {'httpStatus': 200, 'rawBody': json.dumps(body), 'requestId': 'synthetic-request', 'durationSeconds': 0.1}


def task_in(body):
    return json.JSONDecoder().raw_decode(body['input'].split('TASK\n', 1)[1])[0]


class NativeMaintenanceExperimentTests(unittest.TestCase):
    def setUp(self):
        self.tasks = prepare(1)
        self.specs = [task(domain) for domain in DOMAINS]

    def test_public_projection_and_tool_free_request_exclude_private_metadata(self):
        row = deepcopy(self.tasks[0])
        row['withheld'] = row['context']['private'] = 'DO_NOT_SEND'
        prompt = prompt_for(row)
        self.assertNotIn('DO_NOT_SEND', prompt)
        body = request_body(prompt, model='selected-exactly', reasoning_effort='high', maximum_output_tokens=1234)
        self.assertEqual(body['tools'], [])
        self.assertEqual(body['tool_choice'], 'none')
        self.assertFalse(body['store'])
        self.assertEqual(body['model'], 'selected-exactly')
        self.assertEqual(body['max_output_tokens'], 1234)
        self.assertNotIn('previous_response_id', body)
        self.assertTrue(body['text']['format']['strict'])

    def test_completed_response_validation_rejects_refusals_calls_incomplete_and_duplicate_json(self):
        self.assertEqual(decode_response(completion('source'))['source'], 'source')
        bad = [completion('x', status='incomplete'), completion('x', output=[{'type': 'function_call'}]),
               completion('x', output=[]), completion('x', output=[False])]
        for content in [{'type': 'refusal', 'refusal': 'no'},
                        {'type': 'output_text', 'text': '{"action":"code","action":"clarify"}'},
                        {'type': 'output_text', 'text': '{"action":"code","source":"","clarifications":[]}'},
                        {'type': 'output_text', 'text': '{"action":"code","source":"x","clarifications":[],"extra":1}'}]:
            row = completion('x')
            row['output'][0]['content'] = [content]
            bad.append(row)
        for row in bad:
            with self.subTest(row=row), self.assertRaises(ValueError):
                decode_response(row)

    def test_round_order_public_repairs_and_sealing_before_any_withheld_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider_calls, phases = [], []
            def provider(body):
                self.assertFalse((root / 'seal.json').exists())
                chosen = task_in(body)
                provider_calls.append(chosen['caseId'])
                self.assertNotIn('WITHHELD_SENTINEL', body['input'])
                # Refund repaired once, allocation public pass hides a faulty result.
                source = 'bad' if chosen['caseId'].startswith('native-maintenance-refund') and 'PREVIOUS RESPONSE' not in body['input'] else 'correct'
                return transport(completion(source))
            def evaluate(source, language, request, inputs):
                spec = next(row for row in self.specs if inputs == [probe['input'] for probe in row['probes']]
                            or inputs == [probe['input'] for probe in row['probes'] if probe['public']])
                public = [row for row in spec['probes'] if row['public']]
                if len(inputs) > len(public):
                    self.assertTrue((root / 'seal.json').exists())
                    phases.append('withheld')
                else:
                    self.assertNotIn('withheld', phases)
                    self.assertEqual(inputs, [row['input'] for row in public])
                probes = public if len(inputs) == len(public) else spec['probes']
                observed = [row['expected'] for row in probes]
                if source == 'bad' or spec['id'] == 'allocation' and len(inputs) > len(public):
                    observed = [{'result': 'wrong'} for row in probes]
                return {'error': None, 'observations': observed}
            report = run_loop(self.tasks, self.specs, provider, evaluate, root, settings=SETTINGS, metadata={'synthetic': True})
            self.assertEqual(provider_calls[:10], [row['caseId'] for row in self.tasks])
            self.assertEqual(provider_calls[10:], [row['caseId'] for row in self.tasks if row['pairId'] == 'refund'])
            for metrics in report['metrics'].values():
                self.assertEqual(metrics, {'trials': 5, 'missing': 0, 'firstPassSucceeded': 3,
                                          'finalSucceeded': 4, 'repairedTrials': 1, 'recoveredTrials': 1})
            state = json.loads((root / 'run.json').read_text())
            self.assertEqual(state['status'], 'complete')
            self.assertEqual(state['completedCalls'], 12)
            self.assertEqual(state['calls'][0]['usage']['total_tokens'], 23)
            self.assertEqual(state['calls'][0]['returnedModel'], 'returned-model')
            self.assertNotIn('pendingCall', state)

    def test_invalid_generation_consumes_attempt_and_cap_without_becoming_a_missing_trial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = []
            def provider(body):
                calls.append(body)
                return transport(completion('', status='incomplete'))
            report = run_loop(self.tasks, self.specs, provider, lambda *args: self.fail('empty source executed'), root,
                              settings={**SETTINGS, 'maximumAttempts': 2}, metadata={})
            self.assertEqual(len(calls), 20)
            self.assertIn('provider response did not complete', calls[10]['input'])
            self.assertEqual(report['metrics']['gwt']['missing'], 0)
            self.assertEqual(report['metrics']['gwt']['finalSucceeded'], 0)
            rows = [json.loads(line) for line in (root / 'responses.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows), 20)
            self.assertTrue(all(row['generationError'] for row in rows))

    def test_transport_failure_preserves_pending_call_and_never_retries_or_scores_withheld(self):
        for reply in [None, {'httpStatus': 429, 'rawBody': '{"error":"rate limited"}'}]:
            with self.subTest(reply=reply), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                def provider(body):
                    state = json.loads((root / 'run.json').read_text())
                    self.assertEqual(state['pendingCall']['attempt'], 1)
                    if reply is None:
                        raise TimeoutError('uncertain request outcome')
                    return reply
                call = Mock(side_effect=provider)
                with self.assertRaises((RuntimeError, TimeoutError)):
                    run_loop(self.tasks, self.specs, call, lambda *args: self.fail('executed'), root,
                             settings=SETTINGS, metadata={})
                self.assertEqual(call.call_count, 1)
                state = json.loads((root / 'run.json').read_text())
                self.assertEqual(state['status'], 'interrupted')
                self.assertIn('pendingCall', state)
                self.assertFalse((root / 'seal.json').exists())
                self.assertFalse((root / 'report.json').exists())

    def test_execution_infrastructure_failure_keeps_response_before_stopping(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            provider = Mock(return_value=transport(completion('source')))
            with self.assertRaisesRegex(RuntimeError, 'infrastructure'):
                run_loop(self.tasks, self.specs, provider, lambda *args: {'error': 'infrastructure_error'}, root,
                         settings=SETTINGS, metadata={})
            self.assertEqual(provider.call_count, 1)
            self.assertEqual(len((root / 'responses.jsonl').read_text().splitlines()), 1)
            self.assertNotIn('pendingCall', json.loads((root / 'run.json').read_text()))

    def test_api_transport_uses_exact_endpoint_bounded_response_and_no_retries(self):
        connection = Mock()
        response = connection.getresponse.return_value
        response.status = 200
        response.read.return_value = b'{"status":"completed"}'
        response.getheader.return_value = 'request-id'
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'synthetic-secret'}), patch(
                'evaluations.native_maintenance.provider.http.client.HTTPSConnection', return_value=connection) as create:
            provider = ResponsesProvider(socket_timeout=9)
            result = provider({'tools': []})
            create.assert_called_once_with('api.openai.com', timeout=9)
            self.assertEqual(connection.request.call_args.args[1], '/v1/responses')
            self.assertEqual(connection.request.call_args.args[3]['Authorization'], 'Bearer synthetic-secret')
            self.assertEqual(response.read.call_args.args[0], 20 * 1024 * 1024 + 1)
            self.assertNotIn('synthetic-secret', json.dumps(result))
            self.assertNotIn('synthetic-secret', json.dumps(provider.metadata))
            connection.close.assert_called_once()
        with patch.dict('os.environ', {}, clear=True), self.assertRaisesRegex(ValueError, 'OPENAI_API_KEY'):
            ResponsesProvider()

    def test_provider_io_error_closes_connection_without_retry(self):
        connection = Mock()
        connection.getresponse.side_effect = TimeoutError('uncertain outcome')
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'synthetic-secret'}), patch(
                'evaluations.native_maintenance.provider.http.client.HTTPSConnection', return_value=connection):
            with self.assertRaises(TimeoutError):
                ResponsesProvider()({'tools': []})
        connection.request.assert_called_once()
        connection.close.assert_called_once()

    def test_changed_qualification_copy_stops_before_provider_and_closes_evaluator(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            qualification = root / 'qualification'
            qualification.mkdir()
            (qualification / 'tasks.jsonl').write_text('changed since validation')
            evaluator = Mock()
            evaluator.metadata = {'nativeSha256': 'native', 'workerSha256': 'worker'}
            identities = {'qualifiedNativeSha256': 'native', 'qualifiedWorkerSha256': 'worker',
                          'taskSha256': digest(b'original')}
            provider = Mock()
            with patch('evaluations.native_maintenance.experiment.load_tasks', return_value=(self.tasks, self.specs, identities)), patch(
                    'evaluations.native_maintenance.experiment.ContainerEvaluator', return_value=evaluator):
                with self.assertRaisesRegex(ValueError, 'changed while freezing'):
                    run_experiment(qualification, 'native', 'image', root / 'output', provider, SETTINGS)
            provider.assert_not_called()
            evaluator.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
