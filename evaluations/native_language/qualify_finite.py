"""Qualify closed scalar contracts through an explicitly selected native executable."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--native', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
native = args.native.resolve()
source = (root/'examples/native_finite_codes/rules.gwt').read_text()
rules = out/'rules.gwt'
rules.write_text(source)
fault = out/'fault.gwt'
fault.write_text(source.replace('10 * receipt.retry_factor', '12 * receipt.retry_factor'))
commands = []
def save(name, value):
    path = out/name
    path.write_text(json.dumps(value, indent=2, sort_keys=True)+'\n')
    return path
def run(*arguments, expected=0):
    result = subprocess.run([str(native), *map(str,arguments)], capture_output=True, text=True, timeout=30)
    commands.append({'arguments':list(map(str,arguments)), 'exitCode':result.returncode})
    assert result.returncode == expected, (arguments,result.stderr,result.stdout)
    return json.loads(result.stdout)
validation = run('validate',rules)
assert validation['ok'] and len(validation['results']) == 5
save('validation.json',validation)
save('inspection.json',run('inspect',rules))
observations = []
for code in [-1,0,9,10,11,19,20,21,29,30,31,9007199254740993]:
    for factor, delay in [('0',0),('0.5',5),('1',10),('1.000',10),('1.5',15),('2.0',20)]:
        for confirmed in [False,True]:
            data = {'receipt':{'code':code,'retry_factor':factor,'confirmed':confirmed}}
            valid = code in (10,20,30) and delay in (5,10,20) and confirmed
            result = run('run',rules,'--request','review receipt','--input',save('input.json',data),expected=0 if valid else 1)
            assert result['ok'] == valid
            expected = {'decision':{'action':{10:'complete',20:'retry',30:'manual'}.get(code),'delay_minutes':str(delay if code==20 else 0)}} if valid else None
            assert result['result'] == expected
            if not valid:
                assert result['diagnostic']['code'] == 'input_type' and not result['events']
            observations.append({'input':data,'expectedResult':expected,'actual':result})
assert len(observations) == 144
save('independent-probes.json',observations)
selections = [{'receipt':{'code':code,'retry_factor':factor,'confirmed':True}} for code in (10,20,30) for factor in ('0.5','1','2')]
selections += [{'receipt':{'code':99,'retry_factor':'1','confirmed':True}}, {'receipt':{'code':20,'retry_factor':'1.5','confirmed':True}}, {'receipt':{'code':20,'retry_factor':'1','confirmed':False}}]
captures=[]
for index,data in enumerate(selections):
    case=run('capture',rules,'--request','review receipt','--input',save('input.json',data))
    path=save(f'case-{index}.json',case)
    replay=run('replay',path)
    assert replay['verified']
    captures.append(path)
corpus=save('corpus.json',run('corpus',*captures))
review=run('review',corpus,'--candidate',fault,'--html',out/'review.html')
assert len(review['cases'])==12
for index,row in enumerate(review['cases']):
    assert row['comparison']['changes']['outcome'] == (3 <= index <= 5)
    assert row['comparison']['candidate']['ok'] == (index < 9)
save('review.json',review)
save('commands.json',commands)
save('qualification.json',{'native':str(native),'nativeSha256':hashlib.sha256(native.read_bytes()).hexdigest(),'engine':review['engine'],'sourceSha256':hashlib.sha256(source.encode()).hexdigest(),'independentRequests':144,'accepted':12,'rejectedBeforeExecution':132,'scenarios':5,'capturedCases':12,'changedOutcomes':3,'fault':'Intentional candidate changes retry multiplier from ten to twelve; no approval','totals':review['totals']})
print(json.dumps({'independentRequests':144,'capturedCases':12,'changedOutcomes':3}))
