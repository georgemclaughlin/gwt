"""Create frozen refactor and boundary-mutation reviews for the MiniLang fixture."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--checkpoint', type=Path, required=True)
parser.add_argument('--native', type=Path, required=True)
args = parser.parse_args()
p = args.checkpoint.resolve()
after = p / 'after'
native = str(args.native.resolve())
base = json.loads((after / 'request.json').read_text())
inputs = {name: deepcopy(base) for name in
          ['original', 'equal-threshold', 'function-after-call', 'missing-list', 'missing-map']}
inputs['equal-threshold']['front_end']['statements'][3]['threshold'] = 30
statements = inputs['function-after-call']['front_end']['statements']
statements[2], statements[3] = statements[3], statements[2]
inputs['missing-list']['front_end']['lists'] = []
inputs['missing-map']['front_end']['statements'].pop()
corpus = ['python', '-m', 'gwtlang', 'corpus', 'create', '--name', 'MiniLang explicit payload helpers']
native_cases = []
with (p / 'artifact-commands.log').open('w') as log:
    def run(cmd, output=None):
        cmd = list(map(str, cmd))
        log.write(repr(cmd) + '\n')
        log.flush()
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if output:
            (p / output).write_text(result.stdout)
        assert result.returncode == 0, (cmd, result.stderr, result.stdout[:500])
        return json.loads(result.stdout) if output and output.endswith('.json') else None

    for name, facts in inputs.items():
        ip = p / (name + '.input.json')
        ip.write_text(json.dumps(facts) + '\n')
        cp = p / (name + '.python.case.json')
        run(['python', '-m', 'gwtlang', 'capture', p / 'before.gwt', '--json-input', ip,
             '--request', 'run mini source', '--output', cp])
        corpus += ['--case', name + '=' + str(cp)]
        nc = p / (name + '.native.case.json')
        run([native, 'capture', after / 'engine.gwt', '--request', 'run mini source',
             '--input', ip], nc.name)
        assert run([native, 'replay', nc], name + '.native.replay.json')['verified']
        native_cases.append(nc)
    run(corpus + ['--output', p / 'python-corpus.json'])
    run(['python', '-m', 'gwtlang', 'compare', '--corpus', p / 'python-corpus.json',
         '--old', p / 'before.gwt', '--new', after / 'rules.gwt', '--json'], 'python-comparison.json')
    run(['python', '-m', 'gwtlang', 'workbench', '--corpus', p / 'python-corpus.json',
         '--old', p / 'before.gwt', '--new', after / 'rules.gwt',
         '--output', p / 'refactor-review.html'])
    run([native, 'corpus', *native_cases], 'native-corpus.json')
    candidate = p / 'candidate.gwt'
    candidate.write_text((after / 'engine.gwt').read_text().replace('> threshold', '>= threshold'))
    review = run([native, 'review', p / 'native-corpus.json', '--candidate', candidate,
                  '--html', p / 'boundary-review.html'], 'boundary-review.json')
    assert review['complete'] and review['totals']['outcomeChanged'] == 1
    validation = run([native, 'validate', after / 'native_scenarios.gwt',
                      '--html', p / 'native-validation.html'], 'native-validation.json')
    assert validation['ok']
print('Five fixture cases captured; native replay, boundary review and scenario validation pass')
