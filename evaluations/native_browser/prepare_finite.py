"""Prepare current-engine browser observations and verify the retained engine transition."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--native',type=Path,required=True)
parser.add_argument('--previous-native',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
root=Path(__file__).resolve().parents[2]
out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
for name in ['originals','migrations','finite','precision']: (out/name).mkdir()
def read(path):return json.loads(path.read_text())
def save(path,value):path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n');return path
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
native=args.native.resolve(); previous=args.previous_native.resolve();commands=[]
def run(*arguments):
    result=subprocess.run([str(native),*map(str,arguments)],capture_output=True,text=True,timeout=30)
    commands.append({'arguments':list(map(str,arguments)),'exitCode':result.returncode})
    assert result.returncode==0,(arguments,result.stderr,result.stdout)
    return json.loads(result.stdout)
rows=[];origins={}
def origin(path):origins[str(path.relative_to(root))]=digest(path)
def append(case,id,source):
    record=case['record']
    rows.append({'id':id,'requestJson':json.dumps({'bundle':record['source'],'request':record['request'],'input':record['input'],'limits':record['limits']},separators=(',',':')),'expectedJson':json.dumps(record['observed'],separators=(',',':')),'engine':record['engine'],'origin':str(source.relative_to(root))})
old_path=root/'evaluations/native_browser/2026-10-16/cases.json';origin(old_path)
old_rows=read(old_path)
for index,row in enumerate(old_rows):
    path=root/row['origin'];origin(path); document=read(path)
    candidates=[item['case'] for item in document['records']] if 'records' in document else [document]
    request=json.loads(row['requestJson'])
    case=next(c for c in candidates if c['record']['observed']==json.loads(row['expectedJson']) and c['record']['source']==request['bundle'] and c['record']['input']==request['input'] and c['record']['request']==request['request'] and c['record']['limits']==request['limits'] and c['record']['engine']==row['engine'])
    frozen=save(out/'originals'/f'{index}.json',case)
    migration=run('migrate',frozen,'--previous-engine',previous)
    assert not migration['approved'] and migration['status']=='observation_preserved'
    assert migration['baselineReplay']['verified'] and not any(migration['changes'].values())
    assert migration['candidate']['record']['observed']==case['record']['observed']
    assert migration['previousExecutableSha256']=='sha256:'+digest(previous)
    proposal=save(out/'migrations'/f'{index}.json',migration)
    append(migration['candidate'],row['id'],proposal)
assert len(rows)==97
finite=root/'evaluations/native_language/2026-10-16-finite/packaged'
probes=read(finite/'independent-probes.json');origin(finite/'independent-probes.json');origin(finite/'case-0.json')
template=read(finite/'case-0.json')['record']
rules=out/'finite'/'rules.gwt';rules.write_text(template['source']['modules']['rules.gwt'])
limits=save(out/'finite'/'limits.json',template['limits'])
for index,probe in enumerate(probes):
    case=run('capture',rules,'--request',template['request'],'--input',save(out/'finite/input.json',probe['input']),'--limits',limits)
    assert case['record']['observed']==probe['actual']
    assert case['record']['observed']['result']==probe['expectedResult']
    capture=save(out/'finite'/f'{index}.case.json',case)
    append(case,f'finite-{index}',capture)
assert len(rows)==241
precision=[
 ('integer','-1 | 9007199254740993',[-1,9007199254740993,9007199254740992,'9007199254740993',True],[-1,9007199254740993,None,None,None]),
 ('decimal','0.1000000000000000000000000001 | 0.1000000000000000000000000002',['0.1000000000000000000000000001','0.1000000000000000000000000002','0.1000000000000000000000000003',0.1],['0.1000000000000000000000000001','0.1000000000000000000000000002',None,None]),
 ('negative','-2.5 | 1.0',['-2.500',1,'1.00',2],['-2.5','1','1',None]),
 ('true','true',[True,False,1],[True,None,None]),
 ('false','false',[False,True,0],[False,None,None]),
 ('boolean','true | false',[True,False,'true'],[True,False,None]),
]
for label,ty,inputs,expected in precision:
    rules=out/'precision'/f'{label}.gwt'
    rules.write_text(f'TYPE Code is {ty}\nREQUEST echo\n  GIVEN value is Code\n  WHEN PASS\n  OUTPUT value is Code\n')
    for index,(value,want) in enumerate(zip(inputs,expected)):
        case=run('capture',rules,'--request','echo','--input',save(out/'precision/input.json',{'value':value}))
        observed=case['record']['observed']
        assert observed['ok']==(want is not None),(label,index,observed)
        assert observed['result']==({'value':want} if want is not None else None)
        if want is None:assert observed['diagnostic']['code']=='input_type' and not observed['events']
        capture=save(out/'precision'/f'{label}-{index}.case.json',case)
        append(case,f'precision-{label}-{index}',capture)
assert len(rows)==263
assert all(row['engine']==rows[0]['engine'] for row in rows)
save(out/'cases.json',rows);save(out/'origins.json',origins);save(out/'commands.json',commands)
save(out/'preparation.json',{'native':str(native),'nativeSha256':digest(native),'previousNative':str(previous),'previousNativeSha256':digest(previous),'engine':rows[0]['engine'],'unchangedPreviousObservations':97,'receiptRequests':144,'precisionAndBoundaryRequests':22,'totalRequests':263,'migrationApprovals':0})
print(json.dumps({'requests':len(rows),'previousObservationsPreserved':97}))
