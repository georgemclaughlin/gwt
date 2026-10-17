"""Execute trusted research fixtures; this process is not a security sandbox."""
from contextlib import redirect_stdout
from copy import deepcopy
import json
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile


def main():
    language, filename, native = sys.argv[1:]
    if language not in ('gwt', 'python'):
        raise ValueError('unknown fixture language')
    payload = json.load(sys.stdin)
    outcomes = []
    with redirect_stdout(sys.stderr), tempfile.TemporaryDirectory(prefix='gwt-paired-input-') as temporary:
        decide = runpy.run_path(filename)['decide'] if language == 'python' else None
        input_path = Path(temporary) / 'input.json'
        for value in payload['inputs']:
            if language == 'python':
                try:
                    outcomes.append({'result': deepcopy(decide(deepcopy(value)))})
                except ValueError as error:
                    outcomes.append({'rejected': True} if str(error) == 'policy_rejected' else {'error': str(error)})
                except Exception as error:
                    outcomes.append({'error': f'{type(error).__name__}: {error}'})
            else:
                input_path.write_text(json.dumps(value))
                result = subprocess.run([native, 'run', filename, '--request', payload['request'],
                                         '--input', str(input_path)], capture_output=True, text=True, timeout=10)
                try:
                    observed = json.loads(result.stdout)
                    if result.returncode == 0 and observed['ok'] is True:
                        outcomes.append({'result': observed['result']})
                    elif result.returncode == 1 and observed.get('diagnostic', {}).get('code') == 'assertion_failed':
                        outcomes.append({'rejected': True})
                    else:
                        outcomes.append({'error': observed.get('diagnostic') or result.stderr})
                except (ValueError, KeyError, TypeError):
                    outcomes.append({'error': 'invalid native response'})
    print(json.dumps(outcomes, allow_nan=False))


if __name__ == '__main__':
    main()
