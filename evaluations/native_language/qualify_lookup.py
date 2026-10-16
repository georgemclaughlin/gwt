"""Qualify explicit native lookup contracts and review a deliberately faulty copy rewrite."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    native = args.native.resolve()
    source = Path('examples/native_lookup/rules.gwt').read_text()
    rules = out / 'rules.gwt'
    rules.write_text(source)
    baseline = out / 'faulty-copy.gwt'
    baseline.write_text(source.replace(
        '    set item.available to reading.available',
        '    LET selected be item\n    set selected.available to reading.available',
    ))
    assert baseline.read_text() != source
    commands = []

    def run(*arguments, expected=None):
        command = [str(native), *map(str, arguments)]
        result = subprocess.run(command, text=True, capture_output=True, timeout=20)
        commands.append({'arguments': list(map(str, arguments)), 'exitCode': result.returncode})
        assert result.returncode in (0, 1), result.stderr
        payload = json.loads(result.stdout)
        if expected is not None:
            assert result.returncode == expected, payload
        return payload

    def save(name, payload):
        path = out / name
        path.write_text(json.dumps(payload, indent=2) + '\n')
        return path

    validation = run('validate', rules, expected=0)
    assert validation['ok'] and len(validation['results']) == 7
    save('validation.json', validation)
    save('inspection.json', run('inspect', rules, expected=0))
    inventories = [[], [{'sku':'widget','available':5}],
        [{'sku':'other','available':7},{'sku':'widget','available':5}],
        [{'sku':'widget','available':5},{'sku':'widget','available':9}],
        [{'sku':'other','available':7}]]
    probes = []
    for items in inventories:
        for sku in ['widget', 'other', 'missing']:
            index = next((index for index, item in enumerate(items) if item['sku'] == sku), None)
            for available in [0, 2, 5, 9]:
                data = {'inventory':{'items':items},'reading':{'sku':sku,'available':available}}
                updated = deepcopy(items)
                if index is not None:
                    updated[index]['available'] = available
                expectations = {
                    'preview stock count': {'inventory':{'items':items},'selection':{'item':{'sku':sku,'available':available} if index is not None else None}},
                    'record stock count': {'inventory':{'items':updated},'receipt':{'matched':index is not None}},
                }
                for request, expected in expectations.items():
                    actual = run('run', rules, '--request', request, '--input', save('input.json', data), expected=0)
                    assert actual['result'] == expected, (data, actual['result'], expected)
                    probes.append({'request':request,'input':data,'expected':expected,'matched':True})
            for previous in [None, {'sku':'prior','available':13}]:
                data = {'inventory':{'items':items},'query':{'sku':sku},'selection':{'item':previous}}
                expected = {'inventory':{'items':items},'selection':{'item':items[index] if index is not None else previous}}
                actual = run('run', rules, '--request', 'retain stock selection', '--input', save('input.json', data), expected=0)
                assert actual['result'] == expected
                probes.append({'request':'retain stock selection','input':data,'expected':expected,'matched':True})
    assert len(probes) == 150
    save('independent-probes.json', probes)

    selections = [
        ('first-match', 'record stock count', {'inventory':{'items':inventories[1]},'reading':{'sku':'widget','available':2}}, True),
        ('same-count', 'record stock count', {'inventory':{'items':inventories[1]},'reading':{'sku':'widget','available':5}}, False),
        ('duplicate-first', 'record stock count', {'inventory':{'items':inventories[3]},'reading':{'sku':'widget','available':2}}, True),
        ('later-match', 'record stock count', {'inventory':{'items':inventories[2]},'reading':{'sku':'widget','available':2}}, True),
        ('missing', 'record stock count', {'inventory':{'items':inventories[1]},'reading':{'sku':'missing','available':2}}, False),
        ('empty', 'record stock count', {'inventory':{'items':[]},'reading':{'sku':'widget','available':2}}, False),
        ('negative-reading', 'record stock count', {'inventory':{'items':inventories[1]},'reading':{'sku':'widget','available':-1}}, False),
        ('preview-snapshot', 'preview stock count', {'inventory':{'items':inventories[3]},'reading':{'sku':'widget','available':2}}, False),
        ('retained-prior', 'retain stock selection', {'inventory':{'items':inventories[3]},'query':{'sku':'missing'},'selection':{'item':{'sku':'prior','available':13}}}, False),
    ]
    captures = []
    for label, request, data, _changed in selections:
        case = run('capture', baseline, '--request', request, '--input', save('input.json', data), expected=0)
        case_path = save(label + '.case.json', case)
        replay = run('replay', case_path, expected=0)
        assert replay['verified']
        captures.append(case_path)
    corpus = save('corpus.json', run('corpus', *captures, expected=0))
    review = run('review', corpus, '--candidate', rules, '--html', out/'review.html', expected=0)
    save('review.json', review)
    assert len(review['cases']) == len(selections)
    for row, (label, request, data, changed) in zip(review['cases'], selections):
        assert row['comparison']['changes']['outcome'] == changed, label
        assert row['comparison']['candidate']['ok'] == (label != 'negative-reading'), label
    save('selection.json', [{'label':label,'request':request,'input':data,'outcomeChanged':changed} for label,request,data,changed in selections])
    save('commands.json', commands)
    save('qualification.json', {
        'native':str(native),'nativeSha256':hashlib.sha256(native.read_bytes()).hexdigest(),
        'engine':review['engine'],'sourceSha256':hashlib.sha256(source.encode()).hexdigest(),
        'independentRequests':150,'scenarios':7,'reviewedCases':9,'changedOutcomes':3,
        'reviewTotals':review['totals'],'baseline':'Deliberately faulty copied-record mutation; not a historical production rule',
    })
    print(json.dumps({'independentRequests':150,'scenarios':7,'reviewedCases':9,'changedOutcomes':3}))


if __name__ == '__main__':
    main()
