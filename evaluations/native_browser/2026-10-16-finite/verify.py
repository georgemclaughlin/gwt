"""Check recorded browser evidence, native origins, build sources, and WASM bounds."""
import hashlib
import json
from pathlib import Path
import tomllib

here=Path(__file__).resolve().parent
root=here.parents[2]
def read(path):return json.loads(path.read_text())
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def registry(path):return {(p['name'],p['version'],p.get('checksum')) for p in tomllib.loads(path.read_text())['package'] if 'source' in p}

def memory_limits(path):
    data=path.read_bytes();assert data[:8]==b'\0asm\x01\0\0\0';offset=8
    def integer():
        nonlocal offset
        value=0
        for shift in range(0,35,7):
            byte=data[offset];offset+=1;value|=(byte&127)<<shift
            if byte<128:return value
        raise AssertionError('invalid LEB integer')
    while offset<len(data):
        section=data[offset];offset+=1;size=integer();end=offset+size
        if section==5:
            assert integer()==1
            assert integer()==1 # memory32, maximum present, not shared
            minimum=integer();maximum=integer();assert offset==end
            return {'minimumPages':minimum,'maximumPages':maximum,'maximumBytes':maximum*65536}
        offset=end
    raise AssertionError('missing linear memory')

manifest=read(root/'evaluations/native_language/2026-10-16-finite/engine-source-manifest.json')
for name,expected in manifest.items():assert digest(root/name)==expected,name
prep=read(here/'corpus/preparation.json')
assert digest(Path(prep['native']))==prep['nativeSha256']
assert digest(Path(prep['previousNative']))==prep['previousNativeSha256']
for name,expected in read(here/'corpus/origins.json').items():assert digest(root/name)==expected,name
rows=read(here/'corpus/cases.json');assert len(rows)==263
for row in rows:
    capture=read(root/row['origin'])
    if capture['kind']=='gwt.native-case-migration':
        assert not capture['approved'] and capture['baselineReplay']['verified']
        assert capture['status']=='observation_preserved' and not any(capture['changes'].values())
        assert capture['previousExecutableSha256']=='sha256:'+prep['previousNativeSha256']
        assert capture['original']['record']['observed']==capture['candidate']['record']['observed']
        capture=capture['candidate']
    record=capture['record'];request=json.loads(row['requestJson'])
    assert record['observed']==json.loads(row['expectedJson'])
    assert record['engine']==row['engine']==prep['engine']
    assert request=={'bundle':record['source'],'input':record['input'],'request':record['request'],'limits':record['limits']}
assert len(list((here/'corpus/migrations').glob('*.json')))==97

builds=[]
example=root/'examples/native_browser_host'
for version,name in [('1.96.0','gwt_browser_preview.wasm'),('1.85.0','gwt_browser_preview-1.85.0.wasm')]:
    build=read(here/(version+'-build.json'));assert build['toolchain']==version
    assert build['wasmSha256']==digest(here/name) and build['wasmBytes']==(here/name).stat().st_size
    assert all(command['exitCode']==0 for command in build['commands'])
    assert registry(example/'bridge/Cargo.lock')==registry(Path(build['core'])/'engine-dependencies.lock')
    for path in manifest:
        relative=Path(path).relative_to('crates/gwt-core')
        copied=Path(build['core'])/relative
        if relative.as_posix()=='Cargo.toml':copied=Path(build['core'])/'Cargo.toml.orig'
        assert digest(copied)==manifest[path]
    command=build['commands'][0]['command'];bridge=Path(command[command.index('--manifest-path')+1]).parent
    for path in ['src/lib.rs','Cargo.lock']:assert digest(example/'bridge'/path)==digest(bridge/path)
    assert (bridge/'Cargo.toml').read_text()==(example/'bridge/Cargo.toml').read_text().replace('"../../../crates/gwt-core"',json.dumps(build['core']))
    limits=memory_limits(here/name);assert limits['maximumBytes']==64*1048576
    builds.append({'toolchain':version,'bytes':build['wasmBytes'],'sha256':build['wasmSha256'],'memory':limits})
for name in ['index.html','preview.mjs','worker.mjs']:assert digest(here/name)==digest(example/name)
browsers=[]
for browser in ['chromium','firefox','webkit']:
    raw=read(here/browser/'browser-result.json');assert not raw.get('isError'),raw
    result=json.loads(raw['result']);assert result['count']==len(result['checks'])==542
    assert result['offlineDuringExecution'] and len(result['observations'])==526
    assert {(o['build'],o['id']) for o in result['observations']}=={(b,row['id']) for b in range(2) for row in rows}
    expected={row['id']:json.loads(row['expectedJson'])['ok'] for row in rows}
    assert all(o['ok']==expected[o['id']] for o in result['observations'])
    assert all(not module['imports'] for module in result['modules'])
    browsers.append({'engine':browser,'version':result['browserVersion'],'checks':result['count'],'executionComparisons':len(result['observations'])})
# The extracted WebKit result must be the actual retained CLI output.
transcript=(here/'webkit/prepared-run.log').read_text()
raw,_=json.JSONDecoder().raw_decode(transcript[transcript.index('\n{\n')+1:])
assert raw==read(here/'webkit/browser-result.json')
files=[here/'corpus/cases.json',here/'corpus/preparation.json',here/'corpus/origins.json',root/'evaluations/native_browser/prepare_finite.py']
files += [example/name for name in ['build.py','index.html','preview.mjs','worker.mjs']]
for browser in ['chromium','firefox','webkit']:
    files.extend([here/(browser+'-check.js'),here/browser/'browser-result.json',here/browser/'desktop.png',here/browser/'mobile.png'])
report={'engine':prep['engine'],'engineInputsUnchanged':len(manifest),'previousObservationsPreserved':97,'unapprovedMigrations':97,'caseCount':263,'browsers':browsers,'totalBrowserChecks':sum(b['checks'] for b in browsers),'totalExecutionComparisons':sum(b['executionComparisons'] for b in browsers),'builds':builds,'screenshotsInspected':6,'hashes':{str(p.relative_to(root)):digest(p) for p in files},'scope':'Local Linux browser engines; no Safari/mobile-device, production, hosted CI, or human-benefit qualification.'}
(here/'verification.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='hashes'},indent=2))
