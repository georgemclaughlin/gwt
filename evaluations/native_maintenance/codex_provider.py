"""Codex CLI transport, distinct from the tool-free Responses API protocol."""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time

from .provider import RESPONSE_SCHEMA
from .scorer import strict_json


# Pin the tested client: event/config changes need a new transport qualification.
QUALIFIED_VERSION = 'codex-cli 0.163.0'
DISABLED_FEATURES = (
    'shell_tool', 'unified_exec', 'apps', 'plugins', 'remote_plugin', 'hooks',
    'multi_agent', 'multi_agent_v2', 'browser_use', 'browser_use_external',
    'in_app_browser', 'computer_use', 'image_generation', 'view_image',
    'skill_search', 'skill_mcp_dependency_install', 'tool_suggest', 'sleep_tool',
    'unbounded_connection_retries',
)
CONFIG = (
    'web_search="disabled"', 'mcp_servers={}', 'project_doc_max_bytes=0',
    'skills.include_instructions=false', 'memories.use_memories=false',
    'memories.generate_memories=false', 'memories.dedicated_tools=false',
)


def cli_request(prompt, *, model, reasoning_effort, maximum_output_tokens):
    if maximum_output_tokens is not None:
        raise ValueError('Codex CLI has no qualified output-token cap; use None')
    return {'protocol': 'codex-cli-v1', 'prompt': prompt, 'model': model,
            'reasoningEffort': reasoning_effort, 'maximumOutputTokens': None,
            'responseSchema': RESPONSE_SCHEMA}


def normalize_events(stdout, final):
    """Fail closed on tool activity, errors, unknown events, or partial turns.

    This inspects emitted CLI events; it is not a raw API request/response capture.
    The CLI may add its own system context. Do not call this API-equivalent.
    """
    events = [strict_json(line) for line in stdout.splitlines() if line.strip()]
    thread, usage, completed, messages = None, None, 0, []
    started = 0
    for event in events:
        if not isinstance(event, dict):
            raise ValueError('invalid CLI event')
        kind = event.get('type')
        if kind == 'thread.started':
            if thread is not None or not isinstance(event.get('thread_id'), str):
                raise ValueError('invalid or repeated CLI thread')
            thread = event['thread_id']
        elif kind == 'turn.started':
            started += 1
        elif kind == 'turn.completed':
            completed += 1
            usage = event.get('usage')
        elif kind in ('item.started', 'item.updated', 'item.completed'):
            item = event.get('item')
            if not isinstance(item, dict) or item.get('type') not in ('agent_message', 'reasoning'):
                raise ValueError('CLI tool activity or unknown item; experiment stopped')
            if kind == 'item.completed' and item['type'] == 'agent_message':
                messages.append(item.get('text'))
        else:
            raise ValueError('CLI error or unknown event; experiment stopped')
    if thread is None or started != 1 or completed != 1 or not messages or messages[-1] != final.strip():
        raise ValueError('incomplete or inconsistent CLI result')
    # This is our normalized envelope, not a fabricated API response. The CLI
    # does not report the returned model, so that field deliberately stays null.
    return {'id': thread, 'model': None, 'status': 'completed', 'usage': usage,
            'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                        'content': [{'type': 'output_text', 'text': final}]}]}


class CodexProvider:
    build_request = staticmethod(cli_request)

    def __init__(self, *, timeout=300, executable='codex'):
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError('positive finite CLI timeout required')
        self.executable = shutil.which(executable)
        if not self.executable:
            raise ValueError('Codex CLI is unavailable')
        self.version = subprocess.run([self.executable, '--version'], check=True,
                                      capture_output=True, text=True, timeout=10).stdout.strip()
        if self.version != QUALIFIED_VERSION:
            raise ValueError(f'CLI version needs qualification: {self.version}')
        self.timeout = timeout
        self.metadata = {'provider': 'codex-cli', 'protocol': 'codex-cli-v1', 'synthetic': False,
            'version': self.version, 'executable': self.executable,
            'launcherSha256': hashlib.sha256(Path(self.executable).read_bytes()).hexdigest(),
            'orchestratorRetries': 0, 'internalRetries': 'CLI-managed; not asserted absent',
            'maximumOutputTokens': None, 'timeoutSeconds': timeout,
            'disabledFeatures': list(DISABLED_FEATURES), 'config': list(CONFIG),
            'toolEvents': 'stop experiment', 'systemContext': 'Codex CLI built-in context',
            'authentication': 'existing Codex login; no credential export'}

    def __call__(self, body):
        if body.get('protocol') != 'codex-cli-v1':
            raise ValueError('expected a CLI request')
        current = subprocess.run([self.executable, '--version'], check=True,
                                 capture_output=True, text=True, timeout=10).stdout.strip()
        if current != self.version or hashlib.sha256(Path(self.executable).read_bytes()).hexdigest() != self.metadata['launcherSha256']:
            raise RuntimeError('Codex CLI changed during experiment')
        with tempfile.TemporaryDirectory(prefix='gwt-codex-trial-') as directory:
            root = Path(directory)
            schema, response = root / 'schema.json', root / 'response.json'
            schema.write_text(json.dumps(body['responseSchema']))
            command = [self.executable, 'exec', '--ephemeral', '--ignore-user-config', '--ignore-rules',
                       '--skip-git-repo-check', '--sandbox', 'read-only', '--color', 'never', '--json',
                       '--cd', directory, '--model', body['model'], '--output-schema', str(schema),
                       '--output-last-message', str(response)]
            for feature in DISABLED_FEATURES:
                command += ['--disable', feature]
            for config in (*CONFIG, 'model_reasoning_effort=' + json.dumps(body['reasoningEffort'])):
                command += ['-c', config]
            command.append('-')
            prompt = root / 'prompt.txt'
            prompt.write_text(body['prompt'])
            stdout_path, stderr_path = root / 'stdout.jsonl', root / 'stderr.txt'
            started, error = time.monotonic(), None
            with prompt.open('rb') as stdin, stdout_path.open('wb') as stdout, stderr_path.open('wb') as stderr:
                process = subprocess.Popen(command, cwd=root, stdin=stdin, stdout=stdout, stderr=stderr,
                                           start_new_session=True)
                try:
                    while process.poll() is None:
                        if time.monotonic() - started > self.timeout:
                            error = 'CLI deadline exceeded; outcome may be uncertain'
                            break
                        if any(path.exists() and path.stat().st_size > 20 * 1024 * 1024
                               for path in (stdout_path, stderr_path, response)):
                            error = 'CLI output exceeds twenty MiB'
                            break
                        time.sleep(0.05)
                finally:
                    # The npm launcher starts a native child. Stop this owned
                    # process group too, so a deadline cannot leave a live call.
                    if error is not None or process.poll() is None:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    process.wait(timeout=10)
            def read(path):
                if not path.exists():
                    return ''
                with path.open('rb') as stream:
                    return stream.read(20 * 1024 * 1024).decode('utf-8', errors='replace')
            stdout, stderr, final = read(stdout_path), read(stderr_path), read(response)
            if any(path.exists() and path.stat().st_size > 20 * 1024 * 1024
                   for path in (stdout_path, stderr_path, response)):
                error = 'CLI output exceeds twenty MiB'
            result = {'transport': 'codex-cli', 'command': command, 'exitCode': process.returncode,
                      'stdout': stdout, 'stderr': stderr, 'finalMessage': final,
                      'durationSeconds': time.monotonic() - started, 'requestId': None,
                      'rawBodyMeaning': 'normalized envelope; see stdout for original CLI events'}
            if error is None and process.returncode:
                error = 'CLI exited unsuccessfully; no orchestrator retry'
            if error is None:
                try:
                    result['rawBody'] = json.dumps(normalize_events(stdout, final))
                except (ValueError, TypeError) as failure:
                    error = str(failure)
            result['transportError'] = error
            return result
