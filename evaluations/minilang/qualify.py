"""Compare explicit payload helpers with independent MiniLang fixture semantics.

Integer-domain semantic probes, not a parser, performance, or human review study.
"""
import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from gwtlang.runtime import Runtime, parse_program


def expected(facts):
    """Independent host model of the documented fixture checks and AST actions."""
    source, front, runtime = (deepcopy(facts[k]) for k in ['source', 'front_end', 'runtime'])
    statements = front['statements']
    front.update(token_count=len(front['tokens']), statement_count=len(statements),
                 lexed=False, parsed=len(statements) == 6, errors=[])
    runtime.update(add_defined=False, outputs=[], mapped_numbers=[], errors=[], status='new')
    for binding in runtime['bindings']:
        binding.update(kind='unset', number_value=0, list_values=[])
    if source['name'] != 'map sample':
        front['errors'].append('unknown_source')
    else:
        lexemes = {t['lexeme'] for t in front['tokens']}
        front['errors'] += ['missing_token_' + word for word in
                            ['let', 'fn', 'return', 'if', 'else', 'map'] if word not in lexemes]
        front['lexed'] = len(front['tokens']) == 73
        if not front['lexed']:
            front['errors'].append('unexpected_token_count')
    kinds = {s['kind'] for s in statements}
    front['errors'] += ['missing_' + kind for kind in
                       ['let_number', 'fn_add', 'if_add_gt_print', 'let_number_list', 'print_map_double']
                       if kind not in kinds]
    if not front['parsed']:
        front['errors'].append('unexpected_statement_count')
        runtime['errors'].append('parse_failed')
    else:
        def first(items, name):
            return next((item for item in items if item['name'] == name), None)

        for statement in statements:
            kind = statement['kind']
            if kind == 'fn_add':
                runtime['add_defined'] = True
            elif kind == 'let_number':
                binding = first(runtime['bindings'], statement['name'])
                if binding is None:
                    runtime['errors'].append('missing_binding_' + statement['name'])
                else:
                    binding.update(kind='number', number_value=statement['number_value'])
            elif kind == 'let_number_list':
                literal = first(front['lists'], statement['name'])
                binding = first(runtime['bindings'], statement['name'])
                if literal is None:
                    runtime['errors'].append('missing_list_literal_' + statement['name'])
                elif binding is None:
                    runtime['errors'].append('missing_binding_' + statement['name'])
                else:
                    binding.update(kind='number_list', list_values=deepcopy(literal['values']))
            elif kind == 'print_map_double':
                binding = first(runtime['bindings'], statement['list_name'])
                if binding is None:
                    runtime['errors'].append('missing_binding_' + statement['list_name'])
                elif binding['kind'] != 'number_list':
                    runtime['errors'].append('map_expected_number_list')
                else:
                    runtime['mapped_numbers'] = [value * 2 for value in binding['list_values']]
            elif kind == 'if_add_gt_print':
                left = first(runtime['bindings'], statement['left_name'])
                right = first(runtime['bindings'], statement['right_name'])
                if not runtime['add_defined']:
                    runtime['errors'].append('missing_function_add')
                elif left is None:
                    runtime['errors'].append('missing_binding_' + statement['left_name'])
                elif right is None:
                    runtime['errors'].append('missing_binding_' + statement['right_name'])
                elif left['kind'] != 'number' or right['kind'] != 'number':
                    runtime['errors'].append('add_expected_numbers')
                else:
                    above = left['number_value'] + right['number_value'] > statement['threshold']
                    runtime['outputs'].append(statement['then_text' if above else 'else_text'])
            else:
                raise AssertionError('probe outside the declared AST contract')
    runtime['status'] = 'failed' if front['errors'] or runtime['errors'] else 'passed'
    return {'front_end': front, 'runtime': runtime}


def matches(actual, oracle):
    """Compare numbers by value only at oracle numeric leaves; text stays text."""
    if isinstance(oracle, bool):
        return type(actual) is bool and actual == oracle
    if isinstance(oracle, int):
        return not isinstance(actual, bool) and Decimal(str(actual)) == Decimal(oracle)
    if isinstance(oracle, dict):
        return isinstance(actual, dict) and actual.keys() == oracle.keys() and all(
            matches(actual[k], value) for k, value in oracle.items())
    if isinstance(oracle, list):
        return isinstance(actual, list) and len(actual) == len(oracle) and all(
            matches(a, b) for a, b in zip(actual, oracle))
    return type(actual) is type(oracle) and actual == oracle


def probes(base):
    yield 'original', deepcopy(base)
    for order in itertools.permutations(range(6)):
        value = deepcopy(base)
        value['front_end']['statements'] = [value['front_end']['statements'][i] for i in order]
        yield 'order-' + ''.join(map(str, order)), value
    for x, y, limit in itertools.product([-1, 0, 10, 20, 30], [-1, 0, 10, 20, 30], [0, 1, 25, 30, 50]):
        value = deepcopy(base)
        statements = value['front_end']['statements']
        statements[0]['number_value'], statements[1]['number_value'], statements[3]['threshold'] = x, y, limit
        yield f'arithmetic-{x}-{y}-{limit}', value
    for word in ['let', 'fn', 'return', 'if', 'else', 'map']:
        value = deepcopy(base)
        for token in value['front_end']['tokens']:
            if token['lexeme'] == word:
                token['lexeme'] = 'absent'
        yield 'missing-token-' + word, value
    for collection, key in [('front_end', 'tokens'), ('front_end', 'statements'),
                            ('front_end', 'lists'), ('runtime', 'bindings')]:
        for index in range(len(base[collection][key])):
            value = deepcopy(base)
            del value[collection][key][index]
            yield f'drop-{key}-{index}', value
    value = deepcopy(base)
    value['source']['name'] = 'unrecognized'
    yield 'unknown-source', value
    for values in [[], [0], [-2, 0, 3], [1, 1, 1]]:
        value = deepcopy(base)
        value['front_end']['lists'][0]['values'] = values
        yield 'list-' + repr(values), value
    value = deepcopy(base)
    value['runtime'].update(outputs=['stale'], mapped_numbers=[999], errors=['stale'], status='failed')
    value['front_end'].update(errors=['stale'], parsed=True, lexed=True)
    for binding in value['runtime']['bindings']:
        binding.update(kind='number_list', number_value=999, list_values=[999])
    yield 'dirty-state', value
    value = deepcopy(base)
    value['runtime']['bindings'].append(deepcopy(value['runtime']['bindings'][0]))
    yield 'duplicate-binding-first-match', value
    value = deepcopy(base)
    value['front_end']['lists'].insert(0, {'name': 'nums', 'values': [7, 8]})
    yield 'duplicate-list-first-match', value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--checkpoint', type=Path, required=True)
    args = parser.parse_args()
    checkpoint = args.checkpoint.resolve()
    output = checkpoint / 'comparison'
    output.mkdir(exist_ok=False)
    before = checkpoint / 'before.gwt'
    after = ROOT / 'examples/minilang_spec/rules.gwt'
    engine = after.with_name('engine.gwt')
    baseline = Runtime(parse_program(before.read_text(), filename=str(before)))
    revised = Runtime(parse_program(after.read_text(), filename=str(after)))
    native = args.native.resolve()
    base = json.loads(after.with_name('request.json').read_text())
    witnesses = {'inclusive-threshold': [], 'triple-map': []}
    observations = []
    with tempfile.TemporaryDirectory(prefix='gwt-minilang-') as temp:
        temp = Path(temp)
        mutants = {
            'inclusive-threshold': engine.read_text().replace('> threshold', '>= threshold'),
            'triple-map': engine.read_text().replace('append value * 2', 'append value * 3'),
        }
        for name, source in mutants.items():
            assert source != engine.read_text()
            (temp / (name + '.gwt')).write_text(source)
        def run(path, facts):
            (temp / 'input.json').write_text(json.dumps(facts))
            result = subprocess.run([str(native), 'run', str(path), '--request', 'run mini source',
                                     '--input', str(temp / 'input.json')], capture_output=True, text=True, timeout=15)
            payload = json.loads(result.stdout)
            assert result.returncode == 0 and payload['ok'], payload.get('diagnostic')
            return payload['result']
        for index, (name, facts) in enumerate(probes(base)):
            oracle = expected(facts)
            old = baseline.run_json(deepcopy(facts), 'run mini source').scenarios[0].returned_state
            new = revised.run_json(deepcopy(facts), 'run mini source').scenarios[0].returned_state
            actual = run(engine, facts)
            assert matches(old, oracle), ('old', name, old, oracle)
            assert old == new, ('revised Python', name)
            assert matches(actual, oracle), ('native', name, actual, oracle)
            detected = []
            # Arithmetic and ordinary fixture probes suffice to witness both faults.
            if name == 'original' or name.startswith('arithmetic-'):
                for mutation in mutants:
                    if not matches(run(temp / (mutation + '.gwt'), facts), oracle):
                        witnesses[mutation].append(name)
                        detected.append(mutation)
            observations.append({'id': name, 'input': facts, 'expected': oracle,
                                 'pythonBeforeMatches': True, 'pythonAfterMatches': True,
                                 'nativeMatches': True, 'mutantsDetected': detected})
            if index % 100 == 0:
                print('Verified', index + 1, 'probes', flush=True)
    assert all(witnesses.values())
    (output / 'observations.json').write_text(json.dumps(observations) + '\n')
    report = {'ok': True, 'cases': len(observations), 'allStatementPermutations': 720,
              'arithmeticCases': 125, 'pythonBeforeMatches': len(observations),
              'pythonAfterMatches': len(observations), 'nativeMatches': len(observations),
              'mutationWitnesses': witnesses, 'nativeExecutable': str(native),
              'nativeSha256': hashlib.sha256(native.read_bytes()).hexdigest(),
              'beforeSha256': hashlib.sha256(before.read_bytes()).hexdigest(),
              'engineSha256': hashlib.sha256(engine.read_bytes()).hexdigest(),
              'limitations': 'Integer-domain fixtures only; decimal transport is compared numerically at typed numeric leaves. No general migration, parser, performance, or human benefit claim.'}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'mutationWitnesses'}))


if __name__ == '__main__':
    main()
