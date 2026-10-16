"""Exercise real container boundaries and the larger correct policy references."""
import argparse
import json
import os
from pathlib import Path
import subprocess

from .corpus import source_path, task
from .isolated import ContainerEvaluator
from .study import exact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    results = []

    def record(name, evaluator, source, expected_error=None, language='python', inputs=None, request='assess'):
        result = evaluator.evaluate(source, language, request, [{}] if inputs is None else inputs)
        assert result['error'] == expected_error, (name, result)
        container = result['command'][result['command'].index('--name') + 1]
        absent = subprocess.run(['docker', 'inspect', container], capture_output=True, text=True, timeout=10)
        assert absent.returncode != 0 and 'no such object' in absent.stderr.lower(), 'owned container removal is not verified'
        (args.output / f'{name}.json').write_text(json.dumps(result, ensure_ascii=False) + '\n')
        results.append({'name': name, 'error': result['error'], 'containerRemovedVerified': True,
                        'environment': evaluator.metadata})
        return result

    evaluator = ContainerEvaluator(args.native, args.image)
    try:
        source = '''import os, socket
from pathlib import Path
def decide(state):
    checks = {"uid": os.getuid(), "hostEnvironmentAbsent": "GWT_EVALUATION_SENTINEL" not in os.environ,
              "repositoryAbsent": not Path("/home/g/code/gwt/docs/project-goal.md").exists()}
    for path, key in [("/candidate", "candidateReadOnly"), ("/write-probe", "rootWriteBlocked")]:
        try:
            Path(path).write_text("must not write")
            checks[key] = False
        except OSError:
            checks[key] = True
    Path("/tmp/probe").write_text("scratch")
    checks["scratchWritable"] = Path("/tmp/probe").read_text() == "scratch"
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
        try:
            connection.connect(("203.0.113.1", 9))
            checks["networkBlocked"] = False
        except OSError:
            checks["networkBlocked"] = True
    for name in ["memory.max", "pids.max", "cpu.max"]:
        checks[name] = Path("/sys/fs/cgroup", name).read_text().strip()
    return checks
'''
        old = os.environ.get('GWT_EVALUATION_SENTINEL')
        os.environ['GWT_EVALUATION_SENTINEL'] = 'synthetic-host-only-value'
        try:
            boundary = record('boundaries', evaluator, source)['observations'][0]['result']
        finally:
            if old is None:
                del os.environ['GWT_EVALUATION_SENTINEL']
            else:
                os.environ['GWT_EVALUATION_SENTINEL'] = old
        assert boundary == {'uid': 65534, 'hostEnvironmentAbsent': True, 'repositoryAbsent': True,
            'candidateReadOnly': True, 'rootWriteBlocked': True, 'scratchWritable': True, 'networkBlocked': True,
            'memory.max': '268435456', 'pids.max': '64', 'cpu.max': '100000 100000'}, boundary
        spec = task('allocation')
        for language in ('gwt', 'python'):
            result = record(f'allocation-correct-{language}', evaluator, source_path('allocation', 'correct', language).read_text(),
                language=language, inputs=[row['input'] for row in spec['probes']], request=spec['request'])
            assert all(exact(actual, probe['expected']) for actual, probe in zip(result['observations'], spec['probes']))
        result = record('noisy-output', evaluator, 'def decide(state):\n print("candidate log")\n return {"value":9007199254740993}\n')
        assert result['observations'] == [{'result': {'value': 9007199254740993}}]
        assert 'candidate log' in result['stderr']
        record('syntax-error', evaluator, 'def broken(', 'process_error')
        for name, raw in [('wrong-count', '[]'), ('duplicate-key', '[{"result":1,"result":2}]'),
                          ('nonfinite', '[{"result":NaN}]'), ('false-rejection', '[{"rejected":1}]')]:
            record(name, evaluator, f'import os\nos.write(1, {raw.encode()!r})\nos._exit(0)\n', 'invalid_worker_response')
    finally:
        evaluator.close()
    bounded = ContainerEvaluator(args.native, args.image, timeout=2, output_bytes=1024, stderr_bytes=1024)
    try:
        record('timeout', bounded, 'def decide(state):\n while True: pass\n', 'timeout')
        record('stdout-limit', bounded, 'import os\ndef decide(state):\n os.write(1,b"x"*10000)\n return 1\n', 'stdout_limit')
        record('stderr-limit', bounded, 'def decide(state):\n print("x"*10000)\n return 1\n', 'stderr_limit')
    finally:
        bounded.close()
    (args.output / 'qualification.json').write_text(json.dumps({'checks': results, 'correctAllocationExecutions': 1996,
        'liveModelCalls': 0, 'humanParticipants': 0}, indent=2) + '\n')
    print(json.dumps({'checksPassed': len(results), 'correctAllocationExecutions': 1996}))


if __name__ == '__main__':
    main()
