"""Pressure-test native kind contracts against the explicit-payload MiniLang engine.

The candidate is an evaluation artifact, not a second maintained policy module
or a general source translator.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from qualify import expected, matches, probes

ROOT = Path(__file__).resolve().parents[2]


def candidate(source):
    aliases = [('NumberStatement', 'let_number'), ('ListStatement', 'let_number_list'),
               ('ThresholdStatement', 'if_add_gt_print'), ('MapStatement', 'print_map_double')]
    source = source.replace('RECORD MiniNumberList\n', ''.join(
        f'TYPE {name} is MiniStatement of kind {kind}\n' for name, kind in aliases)
        + '\nRECORD MiniNumberList\n')
    edits = [
        ('store number statement.number_value as statement.name into runtime',
         'store number statement into runtime'),
        ('store list statement.name using front_end into runtime',
         'store list statement using front_end into runtime'),
        ('compare sum of statement.left_name and statement.right_name to statement.threshold printing statement.then_text otherwise statement.else_text into runtime',
         'compare sum statement into runtime'),
        ('double list statement.list_name into runtime', 'double list statement into runtime'),
    ]
    for before, after in edits:
        assert source.count(before) == 1, before
        source = source.replace(before, after)
    helpers = [
        ('WHEN store number <value> as <name> into <runtime>\n  GIVEN value is number\n  AND name is text',
         'WHEN store number <statement> into <runtime>\n  GIVEN statement is NumberStatement',
         [('binding.name == name', 'binding.name == statement.name'),
          ('number_value to value', 'number_value to statement.number_value'),
          ('+ name', '+ statement.name')]),
        ('WHEN store list <name> using <front_end> into <runtime>\n  GIVEN name is text',
         'WHEN store list <statement> using <front_end> into <runtime>\n  GIVEN statement is ListStatement',
         [('literal.name == name', 'literal.name == statement.name'),
          ('binding.name == name', 'binding.name == statement.name'), ('+ name', '+ statement.name')]),
        ('WHEN compare sum of <left_name> and <right_name> to <threshold> printing <then_text> otherwise <else_text> into <runtime>\n  GIVEN left_name is text\n  AND right_name is text\n  AND threshold is number\n  AND then_text is text\n  AND else_text is text',
         'WHEN compare sum <statement> into <runtime>\n  GIVEN statement is ThresholdStatement',
         [(name, 'statement.' + name) for name in ['left_name', 'right_name', 'threshold', 'then_text', 'else_text']]),
        ('WHEN double list <name> into <runtime>\n  GIVEN name is text',
         'WHEN double list <statement> into <runtime>\n  GIVEN statement is MapStatement',
         [('binding.name == name', 'binding.name == statement.list_name'), ('+ name', '+ statement.list_name')]),
    ]
    for before, after, edits in helpers:
        assert source.count(before) == 1, before
        start = source.index(before)
        end = source.find('\nWHEN ', start + 1)
        assert end >= 0
        body = source[start + len(before):end]
        for old, new in edits:
            assert old in body, old
            body = body.replace(old, new)
        source = source[:start] + after + body + source[end:]
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    baseline = ROOT / 'examples/minilang_spec/engine.gwt'
    selected = candidate(baseline.read_text())
    for name, source in [('baseline', baseline.read_text()), ('selected', selected)]:
        directory = out / name
        directory.mkdir()
        (directory / 'engine.gwt').write_text(source)
        (directory / 'native_scenarios.gwt').write_text(
            (ROOT / 'examples/minilang_spec/native_scenarios.gwt').read_text())
    native = args.native.resolve()
    base = json.loads((ROOT / 'examples/minilang_spec/request.json').read_text())
    observations = []
    with tempfile.TemporaryDirectory(prefix='gwt-kind-contracts-') as tmp:
        input_path = Path(tmp) / 'input.json'
        for index, (name, facts) in enumerate(probes(base)):
            input_path.write_text(json.dumps(facts))
            oracle = expected(facts)
            outputs = []
            for revision in ['baseline', 'selected']:
                run = subprocess.run([str(native), 'run', str(out / revision / 'engine.gwt'),
                                      '--request', 'run mini source', '--input', str(input_path)],
                                     capture_output=True, text=True, timeout=15)
                result = json.loads(run.stdout)
                assert run.returncode == 0 and result['ok'], (name, revision, result.get('diagnostic'))
                assert matches(result['result'], oracle), (name, revision)
                outputs.append(result['result'])
            assert outputs[0] == outputs[1], name
            observations.append({'id': name, 'input': facts, 'expected': oracle,
                                 'baselineMatches': True, 'selectedMatches': True,
                                 'identicalNativeResult': True})
            if index % 100 == 0:
                print('Verified', index + 1, 'kind-contract probes', flush=True)
    for revision in ['baseline', 'selected']:
        run = subprocess.run([str(native), 'validate', str(out / revision / 'native_scenarios.gwt')],
                             capture_output=True, text=True, timeout=30)
        (out / (revision + '-validation.json')).write_text(run.stdout)
        assert run.returncode == 0 and json.loads(run.stdout)['ok'], run.stdout[:500]
    (out / 'observations.json').write_text(json.dumps(observations) + '\n')
    report = {'ok': True, 'cases': len(observations), 'statementOrderings': 720,
              'numericCases': 125, 'nativeExecutable': str(native),
              'nativeSha256': hashlib.sha256(native.read_bytes()).hexdigest(),
              'baselineSha256': hashlib.sha256(baseline.read_bytes()).hexdigest(),
              'selectedSha256': hashlib.sha256(selected.encode()).hexdigest(),
              'limitations': 'Integer-domain semantic checks; candidate is an evaluation artifact, not a human readability result or general translation tool.'}
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
