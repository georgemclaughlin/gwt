import json
from pathlib import Path
import tempfile
import unittest

from evaluations.native_maintenance.codex_provider import CodexProvider, cli_request, normalize_events
from evaluations.native_maintenance.experiment import run_loop
from evaluations.native_maintenance.provider import decode_response
from evaluations.native_maintenance.corpus import DOMAINS, task
from evaluations.native_maintenance.study import prepare


FINAL = json.dumps({'action': 'code', 'source': 'qualification', 'clarifications': []})


def events(extra=()):
    return '\n'.join(json.dumps(row) for row in [
        {'type': 'thread.started', 'thread_id': 'synthetic-thread'},
        {'type': 'turn.started'}, *extra,
        {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': FINAL}},
        {'type': 'turn.completed', 'usage': {'input_tokens': 7, 'output_tokens': 3}},
    ])


class CodexMaintenanceTests(unittest.TestCase):
    def test_final_and_reported_usage_survive_without_inventing_returned_model(self):
        normalized = normalize_events(events(), FINAL + '\n')
        self.assertEqual(decode_response(normalized)['source'], 'qualification')
        self.assertEqual(normalized['usage'], {'input_tokens': 7, 'output_tokens': 3})
        self.assertIsNone(normalized['model'])

    def test_tools_unknown_events_and_failed_turns_stop_protocol(self):
        for row in [
            {'type': 'item.started', 'item': {'type': 'command_execution'}},
            {'type': 'item.completed', 'item': {'type': 'mcp_tool_call'}},
            {'type': 'item.updated', 'item': {'type': 'file_change'}},
            {'type': 'error', 'message': 'reconnecting'},
            {'type': 'turn.failed'}, {'type': 'future.event'},
        ]:
            with self.subTest(row=row), self.assertRaises(ValueError):
                normalize_events(events([row]), FINAL)

    def test_missing_duplicate_or_mismatching_completions_are_not_success(self):
        for stdout, final in [(events().rsplit('\n', 1)[0], FINAL),
                              (events() + '\n' + json.dumps({'type': 'turn.completed'}), FINAL),
                              (events(), 'different'), ('{"type":"turn.started","type":"turn.completed"}', FINAL)]:
            with self.subTest(stdout=stdout), self.assertRaises(ValueError):
                normalize_events(stdout, final)

    def test_cli_does_not_silently_claim_api_token_cap(self):
        with self.assertRaisesRegex(ValueError, 'output-token cap'):
            cli_request('prompt', model='exact', reasoning_effort='medium', maximum_output_tokens=16000)
        body = cli_request('prompt', model='exact', reasoning_effort='medium', maximum_output_tokens=None)
        self.assertEqual(body['model'], 'exact')
        self.assertIsNone(body['maximumOutputTokens'])
        self.assertNotIn('tools', body)

    def fake_cli(self, root, code):
        executable = root / 'fake-codex'
        executable.write_text('#!/usr/bin/env python3\nimport json,sys,time\nfrom pathlib import Path\n'
                              'if "--version" in sys.argv:\n print("codex-cli 0.163.0");sys.exit(0)\n' + code)
        executable.chmod(0o755)
        return str(executable)

    def test_transport_keeps_original_events_command_and_output(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = self.fake_cli(Path(directory),
                'Path(sys.argv[sys.argv.index("--output-last-message")+1]).write_text(' + repr(FINAL) + ')\n'
                'print(' + repr(events()) + ')\n')
            provider = CodexProvider(executable=executable)
            result = provider(cli_request('public prompt', model='exact', reasoning_effort='medium', maximum_output_tokens=None))
            self.assertIsNone(result['transportError'])
            self.assertNotIn('httpStatus', result)
            self.assertEqual(result['stdout'].strip(), events())
            self.assertIn('--ignore-user-config', result['command'])
            self.assertIn('shell_tool', result['command'])
            self.assertEqual(decode_response(json.loads(result['rawBody']))['source'], 'qualification')

    def test_timeout_preserves_partial_events_instead_of_retrying(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = self.fake_cli(Path(directory), 'print("partial",flush=True)\ntime.sleep(10)\n')
            result = CodexProvider(timeout=0.2, executable=executable)(
                cli_request('public', model='exact', reasoning_effort='medium', maximum_output_tokens=None))
            self.assertIn('deadline', result['transportError'])
            self.assertEqual(result['stdout'].strip(), 'partial')
            self.assertNotIn('rawBody', result)

    def test_cli_protocol_failure_is_persisted_and_stops_before_candidate_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = {'model': 'exact', 'reasoningEffort': 'medium', 'maximumAttempts': 3,
                        'maximumOutputTokens': None}
            calls = []
            def provider(body):
                calls.append(body)
                return {'transport': 'codex-cli', 'transportError': 'tool activity', 'stdout': 'retained'}
            with self.assertRaisesRegex(RuntimeError, 'tool activity'):
                run_loop(prepare(1), [task(domain) for domain in DOMAINS], provider,
                         lambda *args: self.fail('candidate executed'), root,
                         settings=settings, metadata={}, build_request=cli_request)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]['protocol'], 'codex-cli-v1')
            state = json.loads((root / 'run.json').read_text())
            self.assertEqual(state['status'], 'interrupted')
            self.assertIn('pendingCall', state)
            record = next((root / 'calls').glob('*/transport.json'))
            self.assertEqual(json.loads(record.read_text())['stdout'], 'retained')
            self.assertFalse((root / 'seal.json').exists())


if __name__ == '__main__':
    unittest.main()
