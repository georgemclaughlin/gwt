"""Bounded container execution for cooperative maintenance candidates."""
import hashlib
import json
import math
from pathlib import Path
import selectors
import shutil
import subprocess
import tempfile
import time
import uuid


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate worker JSON field')
        value[key] = item
    return value


def _finite_constant(value):
    raise ValueError(f'nonfinite worker JSON: {value}')


def _remove_owned(name):
    result = subprocess.run(['docker', 'rm', '--force', name], capture_output=True, text=True, timeout=15)
    if result.returncode == 0 or 'no such container' in result.stderr.lower():
        return
    if 'removal of container' in result.stderr.lower() and 'already in progress' in result.stderr.lower():
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            inspected = subprocess.run(['docker', 'inspect', name], capture_output=True, text=True, timeout=2)
            if inspected.returncode and any(message in inspected.stderr.lower() for message in ('no such object', 'no such container')):
                return
            if inspected.returncode:
                raise RuntimeError(f'cannot verify container removal: {inspected.stderr[:1000]}')
            time.sleep(0.05)
    raise RuntimeError(f'container cleanup failed: {result.stderr[:1000]}')


class ContainerEvaluator:
    def __init__(self, native, image, *, timeout=120, output_bytes=16 * 1024 * 1024, stderr_bytes=256 * 1024):
        if not math.isfinite(timeout) or timeout <= 0 or type(output_bytes) is not int or output_bytes < 1:
            raise ValueError('positive finite timeout and output bound required')
        if type(stderr_bytes) is not int or stderr_bytes < 1:
            raise ValueError('positive stderr bound required')
        inspected = subprocess.run(['docker', 'image', 'inspect', image], capture_output=True, text=True, timeout=15, check=True)
        info = json.loads(inspected.stdout)[0]
        self.image = info['Id']
        self.timeout, self.output_bytes, self.stderr_bytes = timeout, output_bytes, stderr_bytes
        self.temporary = tempfile.TemporaryDirectory(prefix='gwt-isolated-evaluation-')
        root = Path(self.temporary.name)
        self.native = root / 'native'
        self.worker = root / 'worker.py'
        shutil.copyfile(native, self.native)
        self.native.chmod(0o555)
        shutil.copyfile(Path(__file__).with_name('worker.py'), self.worker)
        self.worker.chmod(0o444)
        self.metadata = {'imageId': self.image, 'repoDigests': info.get('RepoDigests', []),
            'architecture': info['Architecture'], 'os': info['Os'],
            'nativeSha256': hashlib.sha256(self.native.read_bytes()).hexdigest(),
            'workerSha256': hashlib.sha256(self.worker.read_bytes()).hexdigest(),
            'timeoutSeconds': timeout, 'stdoutBytes': output_bytes, 'stderrBytes': stderr_bytes,
            'network': 'none', 'readOnlyRoot': True, 'user': '65534:65534',
            'memoryBytes': 256 * 1024 * 1024, 'cpus': 1, 'pids': 64, 'temporaryBytes': 32 * 1024 * 1024}

    def close(self):
        self.temporary.cleanup()

    def evaluate(self, source, language, request, inputs):
        if language not in ('gwt', 'python') or not isinstance(source, str):
            raise ValueError('invalid candidate language/source')
        if len(source.encode()) > 1_048_576:
            return {'error': 'source_limit', 'observations': None}
        payload = json.dumps({'request': request, 'inputs': inputs}, allow_nan=False).encode()
        if len(payload) > 8 * 1024 * 1024:
            raise ValueError('input batch exceeds eight MiB')
        name = 'gwt-evaluation-' + uuid.uuid4().hex
        with tempfile.TemporaryDirectory(dir=self.temporary.name) as directory:
            candidate = Path(directory) / 'candidate'
            candidate.write_text(source)
            candidate.chmod(0o444)
            stdin = Path(directory) / 'inputs.json'
            stdin.write_bytes(payload)
            command = ['docker', 'run', '--rm', '--pull', 'never', '--name', name, '--init', '-i',
                '--network', 'none', '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                '--user', '65534:65534', '--memory', '256m', '--memory-swap', '256m', '--cpus', '1',
                '--pids-limit', '64', '--log-driver', 'none', '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=32m',
                '--env', 'PYTHONDONTWRITEBYTECODE=1', '--workdir', '/tmp']
            for host, target in [(candidate, '/candidate'), (self.worker, '/worker.py'), (self.native, '/native')]:
                # --mount uses commas as separators; reject ambiguous host paths.
                if ',' in str(host):
                    raise ValueError('container mount paths cannot contain commas')
                command += ['--mount', f'type=bind,src={host},dst={target},readonly']
            command += ['--entrypoint', '/usr/local/bin/python', self.image, '-I', '/worker.py', language, '/candidate', '/native']
            chunks = {'stdout': bytearray(), 'stderr': bytearray()}
            error, process = None, None
            started = time.monotonic()
            try:
                with stdin.open('rb') as input_stream, selectors.DefaultSelector() as selector:
                    process = subprocess.Popen(command, stdin=input_stream, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    for label in chunks:
                        selector.register(getattr(process, label), selectors.EVENT_READ, label)
                    while selector.get_map():
                        remaining = self.timeout - (time.monotonic() - started)
                        if remaining <= 0:
                            error = 'timeout'
                            break
                        for key, _ in selector.select(min(remaining, 0.1)):
                            data = key.fileobj.read1(65536)
                            if not data:
                                selector.unregister(key.fileobj)
                                continue
                            limit = self.output_bytes if key.data == 'stdout' else self.stderr_bytes
                            available = limit - len(chunks[key.data])
                            chunks[key.data].extend(data[:available])
                            if len(data) > available:
                                error = f'{key.data}_limit'
                                break
                        if error:
                            break
                    if not error:
                        try:
                            process.wait(timeout=max(0.01, self.timeout - (time.monotonic() - started)))
                        except subprocess.TimeoutExpired:
                            error = 'timeout'
            finally:
                # Terminate only this invocation's uniquely named container.
                try:
                    _remove_owned(name)
                finally:
                    if process is not None:
                        if process.poll() is None:
                            process.kill()
                        process.wait(timeout=5)
                        process.stdout.close()
                        process.stderr.close()
            stdout = bytes(chunks['stdout']).decode('utf-8', errors='replace')
            stderr = bytes(chunks['stderr']).decode('utf-8', errors='replace')
            observations = None
            if not error and process.returncode:
                error = 'infrastructure_error' if process.returncode in (125, 126, 127) else 'process_error'
            if not error:
                try:
                    observations = json.loads(stdout, object_pairs_hook=_unique_object, parse_constant=_finite_constant)
                    if not isinstance(observations, list) or len(observations) != len(inputs):
                        raise ValueError('wrong observation count')
                    if any(not isinstance(value, dict) or len(value) != 1 or not set(value) <= {'result', 'rejected', 'error'}
                           or ('rejected' in value and value['rejected'] is not True) for value in observations):
                        raise ValueError('invalid observation shape')
                except (ValueError, TypeError):
                    error, observations = 'invalid_worker_response', None
            return {'error': error, 'observations': observations, 'exitCode': process.returncode,
                    'durationSeconds': round(time.monotonic() - started, 3), 'command': command,
                    'stdout': stdout, 'stderr': stderr, 'containerRemoved': True}
