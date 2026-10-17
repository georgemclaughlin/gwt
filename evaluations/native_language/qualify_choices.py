"""Verify deliberate language choices against independent expected results.

The fixture states acceptance and independent results. Historical Python
observations remain available in the pre-retirement checkout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

FIXTURE = Path('crates/gwt-core/tests/fixtures/language_choices.json')
CURRENT_EXPECTATIONS = Path('evaluations/native_language/current-choice-expectations.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expectations', type=Path, default=CURRENT_EXPECTATIONS,
                        help='Explicit expectation overrides for this engine; retained fixture source stays unchanged')
    args = parser.parse_args()
    rows = json.loads(FIXTURE.read_text())
    overrides = json.loads(args.expectations.read_text())
    if not isinstance(overrides, dict):
        parser.error('expectation overrides must be an object keyed by probe ID')
    if set(overrides) - {row['id'] for row in rows}:
        parser.error('expectation override names an unknown probe')
    allowed = {'nativeCheck', 'nativeCheckDiagnostic', 'nativeRun',
               'expectedState', 'expectedResult', 'diagnostic'}
    for row in rows:
        changes = overrides.get(row['id'], {})
        if not isinstance(changes, dict) or set(changes) - allowed:
            parser.error('expectation overrides may change only native expectations')
        row.update(changes)
    args.output.mkdir(parents=True, exist_ok=False)
    native = args.native.resolve()
    observations, failures = [], []
    with tempfile.TemporaryDirectory(prefix='gwt-language-choices-') as temporary:
        directory = Path(temporary)
        for row in rows:
            source = directory/(row['id']+'.gwt')
            source.write_text(row['source'])
            checked = subprocess.run([str(native),'check',str(source)],text=True,capture_output=True,timeout=15)
            check = json.loads(checked.stdout)
            result = dict(id=row['id'],source=row['source'],nativeCheck=check)
            if check['ok'] != row['nativeCheck']: failures.append((row['id'],'check',check))
            if not check['ok'] and check['diagnostic']['code'] != row.get('nativeCheckDiagnostic'):
                failures.append((row['id'],'checkDiagnostic',check['diagnostic']))
            if check['ok']:
                command = [str(native),'run',str(source)]
                if 'request' in row:
                    ip=directory/'input.json';ip.write_text(json.dumps(row['input']))
                    command += ['--request',row['request'],'--input',str(ip)]
                run = subprocess.run(command,text=True,capture_output=True,timeout=15)
                payload=json.loads(run.stdout);result['nativeRun']=payload
                if payload['ok'] != row.get('nativeRun',True): failures.append((row['id'],'run',payload))
                for expected,key in [('expectedState','state'),('expectedResult','result')]:
                    if expected in row and payload[key] != row[expected]: failures.append((row['id'],key,payload[key]))
                if 'diagnostic' in row and (payload.get('diagnostic') or {}).get('code') != row['diagnostic']:
                    failures.append((row['id'],'diagnostic',payload.get('diagnostic')))
            observations.append(result)
    (args.output/'observations.json').write_text(json.dumps(observations,indent=2,default=str)+'\n')
    (args.output/'failures.json').write_text(json.dumps(failures,indent=2)+'\n')
    if failures:
        print(json.dumps(failures,indent=2));raise SystemExit(1)
    summary=dict(probes=len(observations),nativeAccepted=sum(r['nativeCheck']['ok'] for r in observations),
                 nativeExecuted=sum('nativeRun' in r for r in observations),
                 nativeSuccessful=sum(r.get('nativeRun',{}).get('ok',False) for r in observations),
                 nativeExecutable=str(native),nativeSha256=hashlib.sha256(native.read_bytes()).hexdigest(),
                 fixtureSha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                 expectationOverrides=overrides,
                 expectationSha256=hashlib.sha256(args.expectations.read_bytes()).hexdigest(),humanParticipants=0)
    (args.output/'qualification.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__ == '__main__': main()
