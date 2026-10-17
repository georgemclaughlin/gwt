"""Reproduce casing observations without changing the language or saved cases."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def probe(executable):
    def invoke(command, path):
        process = subprocess.run([str(executable), command, str(path)], capture_output=True, text=True, check=False)
        data = json.loads(process.stdout)
        return {'exitCode': process.returncode, 'ok': data.get('ok'),
                'diagnostic': data.get('diagnostic'),
                **({'state': data['state']} if 'state' in data else {}),
                **({'text': data['text'], 'changed': data['changed']} if 'text' in data else {})}
    mutation = 'SCENARIO mutation\nGIVEN total is 0\nWHEN set total to 2\nTHEN total == 2\n'
    binding = 'WHEN compute\n  THEN returns integer\n  LET value be 2\n  RETURN value\nSCENARIO binding\nWHEN LET total be compute\nTHEN total == 2\n'
    loop = 'WHEN collect <items> into <total>\n  GIVEN items is list<integer>\n  AND total is integer\n  FOR item in items WHERE item > 0\n    add item to total\nSCENARIO collection\nGIVEN items is [1, -1, 2]\nGIVEN total is 0\nWHEN collect items into total\nTHEN total == 3\n'
    dispatch = 'WHEN choose <flag> into <total>\n  GIVEN flag is boolean\n  AND total is integer\n  DEPENDING ON flag\n    WHEN the value is true\n      set total to 1\n    WHEN the value is false\n      set total to 2\nSCENARIO dispatch\nGIVEN total is 0\nWHEN choose true into total\nTHEN total == 1\n'
    cases = {
        'set_lowercase': mutation,
        'SET_uppercase': mutation.replace('WHEN set', 'WHEN SET'),
        'Set_titlecase': mutation.replace('WHEN set', 'WHEN Set'),
        'when_lowercase': mutation.replace('WHEN set', 'when set'),
        'IS_uppercase': mutation.replace(' is ', ' IS '),
        'LET_RETURN_uppercase': binding,
        'let_lowercase': binding.replace('LET value', 'let value'),
        'return_lowercase': binding.replace('RETURN value', 'return value'),
        'WHERE_uppercase': loop,
        'where_lowercase': loop.replace(' WHERE ', ' where '),
        'Where_titlecase': loop.replace(' WHERE ', ' Where '),
        'DEPENDING_ON_uppercase': dispatch,
        'DEPENDING_on_lowercase': dispatch.replace('DEPENDING ON', 'DEPENDING on'),
        'true_lowercase': 'SCENARIO boolean\nTHEN true\n',
        'TRUE_uppercase': 'SCENARIO boolean\nTHEN TRUE\n',
        'custom_SET_distinct_from_set': 'WHEN SET <target> to <value>\n  GIVEN target is integer\n  AND value is integer\n  set target to value + 100\n' + mutation.replace('WHEN set', 'WHEN SET').replace('THEN total == 2', 'THEN total == 102'),
        'custom_set_reserved': 'WHEN set <target> to <value>\n  GIVEN target is integer\n  AND value is integer\n  PASS\nSCENARIO name\nTHEN true\n',
        'custom_find_reserved': 'WHEN find value\n  PASS\nSCENARIO name\nWHEN find value\nTHEN true\n',
        'custom_Find_allowed': 'WHEN Find value\n  PASS\nSCENARIO name\nWHEN Find value\nTHEN true\n',
        'lowercase_record_type': 'RECORD parcel\n  weight: integer\nSCENARIO type\nGIVEN item is parcel\n  weight: 1\nTHEN item.weight == 1\n',
        'uppercase_binding': 'SCENARIO binding\nGIVEN SET is 1\nWHEN set SET to 2\nTHEN SET == 2\n',
        'keyword_field': 'RECORD Parcel\n  WHEN: integer\nSCENARIO field\nGIVEN item is Parcel\n  WHEN: 1\nTHEN item.WHEN == 1\n',
        'AND_expression': 'SCENARIO expression\nTHEN true AND true\n',
        'and_expression': 'SCENARIO expression\nTHEN true and true\n',
        'and_identifier_reserved': 'SCENARIO binding\nGIVEN and is 1\nTHEN true\n',
        'AND_identifier_allowed': 'SCENARIO binding\nGIVEN AND is 1\nTHEN AND == 1\n',
    }
    observations = []
    with tempfile.TemporaryDirectory(prefix='gwt-casing-') as temporary:
        path = Path(temporary) / 'probe.gwt'
        for name, source in cases.items():
            path.write_text(source)
            observations.append({'name': name, 'source': source, 'run': invoke('run', path), 'format': invoke('format', path)})
    catalog = json.loads((ROOT / 'examples/catalog.json').read_text())
    heads, filters = Counter(), Counter()
    for entry in catalog['entries']:
        for raw in (ROOT / entry['path']).read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith('#'):
                continue
            heads[line.split()[0]] += 1
            if line.startswith(('FOR ', 'FIND ')):
                filters.update(re.findall(r'\b(?:WHERE|where|Where)\b', line))
    syntax_spec = importlib.util.spec_from_file_location('site_syntax', ROOT / 'tools/highlight_site.py')
    syntax = importlib.util.module_from_spec(syntax_spec)
    syntax_spec.loader.exec_module(syntax)
    vocabulary = 'PROGRAM USE TYPE FIND DEPENDING ON WHERE where LET RETURN set add subtract append count sum divide print optional number text string table null SET Parcel'.split()
    website_tokens = {word: syntax.highlight(word, 'gwt') for word in vocabulary}
    audited = ['docs/native-grammar.md', 'docs/spec/native-draft.md', 'crates/gwt-core/src/program.rs',
               'crates/gwt-core/src/program_source.rs', 'crates/gwt-core/src/formatter.rs',
               'crates/gwt-core/src/editor_completion.rs', 'vscode-gwt/syntaxes/gwt.tmLanguage.json',
               'tools/highlight_site.py', 'examples/catalog.json']
    return {'kind': 'gwt.language-consistency-review', 'schemaVersion': 1,
            'reviewedRevision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'engine': json.loads(subprocess.check_output([str(executable), 'version', '--json'], text=True)),
            'sources': {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in audited},
            'catalogEntryCount': len(catalog['entries']), 'catalogLineHeads': dict(sorted(heads.items())),
            'catalogFilterSpellings': dict(filters), 'websiteTokenSamples': website_tokens, 'probes': observations}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gwt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = probe(args.gwt.resolve())
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    for row in report['probes']:
        run, formatted = row['run'], row['format']
        diagnostic = run['diagnostic'] or {}
        print(f"{row['name']}: run={run['ok']}, diagnostic={diagnostic.get('code')}, format={formatted['ok']}, changed={formatted.get('changed')}")
    print('Filter spellings:', report['catalogFilterSpellings'])
