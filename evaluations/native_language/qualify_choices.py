"""Observe and verify deliberate native language choices against the Python reference.

The fixture states native acceptance and independent results. Python observations
are recorded separately; a Python checker success does not substitute for a run.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import sys

from gwtlang import check_text
from gwtlang.runtime import GwtError, run_source, run_json_request

FIXTURE = Path('crates/gwt-core/tests/fixtures/language_choices.json')
CURRENT_EXPECTATIONS = Path('evaluations/native_language/current-choice-expectations.json')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--previous-runtime', type=Path, help='Retained trusted Python runtime module for before/after observations')
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
    previous = None
    if args.previous_runtime:
        spec = importlib.util.spec_from_file_location('gwtlang._choices_previous_runtime', args.previous_runtime)
        previous = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = previous
        spec.loader.exec_module(previous)

    def python_run(row, module=None):
        source_runner = module.run_source if module else run_source
        json_runner = module.run_json_request if module else run_json_request
        try:
            run = json_runner(row['source'],row['input'],request=row['request'],filename=row['id']+'.gwt') if 'request' in row else source_runner(row['source'],filename=row['id']+'.gwt')
            return {'ok':True,'state':run.state,'result':run.scenarios[0].returned_state,'output':run.output}
        except (GwtError,ZeroDivisionError) as error:
            return {'ok':False,'error':str(error)}
    observations, failures = [], []
    with tempfile.TemporaryDirectory(prefix='gwt-language-choices-') as temporary:
        directory = Path(temporary)
        for row in rows:
            source = directory/(row['id']+'.gwt')
            source.write_text(row['source'])
            checked = subprocess.run([str(native),'check',str(source)],text=True,capture_output=True,timeout=15)
            check = json.loads(checked.stdout)
            result = dict(id=row['id'],source=row['source'],nativeCheck=check,pythonCheck=check_text(row['source']).as_payload())
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
            result['pythonRun'] = python_run(row)
            if previous:
                result['previousPythonRun'] = python_run(row, previous)
            observations.append(result)
    (args.output/'observations.json').write_text(json.dumps(observations,indent=2,default=str)+'\n')
    (args.output/'failures.json').write_text(json.dumps(failures,indent=2)+'\n')
    if failures:
        print(json.dumps(failures,indent=2));raise SystemExit(1)
    summary=dict(probes=len(observations),nativeAccepted=sum(r['nativeCheck']['ok'] for r in observations),
                 nativeExecuted=sum('nativeRun' in r for r in observations),
                 nativeSuccessful=sum(r.get('nativeRun',{}).get('ok',False) for r in observations),
                 pythonChecked=sum(r['pythonCheck']['ok'] for r in observations),pythonSuccessful=sum(r['pythonRun']['ok'] for r in observations),
                 nativeExecutable=str(native),nativeSha256=hashlib.sha256(native.read_bytes()).hexdigest(),
                 fixtureSha256=hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                 expectationOverrides=overrides,
                 expectationSha256=hashlib.sha256(args.expectations.read_bytes()).hexdigest(),humanParticipants=0)
    if previous:
        summary['previousRuntimeSha256'] = hashlib.sha256(args.previous_runtime.read_bytes()).hexdigest()
        summary['pythonObservationChanges'] = [r['id'] for r in observations if r['pythonRun'] != r['previousPythonRun']]
    (args.output/'qualification.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__ == '__main__': main()
