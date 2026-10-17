"""Verify retained browser evidence against current sources and captured origins."""
import hashlib
import json
from pathlib import Path
import tomllib

here = Path(__file__).resolve().parent
root = here.parents[2]
def read(path):
    return json.loads(path.read_text())
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()
def registry(path):
    return {(p['name'], p['version'], p.get('checksum')) for p in tomllib.loads(path.read_text())['package'] if 'source' in p}

engine = read(root/'evaluations/native_review/2026-10-16-review-identity/engine-source-manifest.json')
for path, expected in engine.items():
    assert digest(root/path) == expected, path
origins = read(here/'origins.json')
for path, expected in origins.items():
    assert digest(root/path) == expected, path
rows = read(here/'cases.json')
assert len(rows) == 97
for row in rows:
    origin = read(root/row['origin'])
    candidates = [item['case']['record'] for item in origin['records']] if 'records' in origin else [origin['record']]
    request = json.loads(row['requestJson'])
    assert any(
        item.get('request') == request['request']
        and item['source'] == request['bundle']
        and item['input'] == request['input']
        and item['limits'] == request['limits']
        and item['engine'] == row['engine']
        and item['observed'] == json.loads(row['expectedJson'])
        for item in candidates
    ), row['id']
result = read(here/'browser-result.json')
assert not result.get('isError')
result = json.loads(result['result'])
assert result['count'] == len(result['checks']) == 210
assert result['offlineDuringExecution'] is True
assert len(result['observations']) == 194
assert {(o['build'], o['id']) for o in result['observations']} == {(b,r['id']) for b in range(2) for r in rows}
assert all(not module['imports'] for module in result['modules'])
example = root/'examples/native_browser_host'
for name in ['index.html','preview.mjs','worker.mjs']:
    assert digest(example/name) == digest(here/name), name
builds = []
for version, name in [('1.96.0','gwt_browser_preview.wasm'),('1.85.0','gwt_browser_preview-1.85.0.wasm')]:
    build = read(here/(version+'-build.json'))
    assert build['toolchain'] == version
    assert build['wasmSha256'] == digest(here/name)
    assert build['wasmBytes'] == (here/name).stat().st_size
    assert all(command['exitCode'] == 0 for command in build['commands'])
    assert registry(example/'bridge/Cargo.lock') == registry(Path(build['core'])/'engine-dependencies.lock')
    # The build records cargo --manifest-path immediately before its manifest.
    command = build['commands'][0]['command']
    copied = Path(command[command.index('--manifest-path')+1]).parent
    for relative in ['src/lib.rs','Cargo.lock']:
        assert digest(example/'bridge'/relative) == digest(copied/relative), relative
    expected_manifest = (example/'bridge/Cargo.toml').read_text().replace('"../../../crates/gwt-core"',json.dumps(build['core']))
    assert (copied/'Cargo.toml').read_text() == expected_manifest
    builds.append({'toolchain':version,'bytes':build['wasmBytes'],'sha256':build['wasmSha256']})
report = {
    'engineInputsUnchanged':len(engine), 'originFilesUnchanged':len(origins),
    'casesEqualOriginalCaptures':len(rows), 'browserChecks':result['count'],
    'fullExecutionComparisons':len(result['observations']),
    'browserVersion':result['browserVersion'], 'builds':builds,
    'hostSourceHashes':{str(p.relative_to(root)):digest(p) for p in sorted(example.rglob('*')) if p.is_file() and 'target' not in p.parts},
    'evidenceHashes':{p.name:digest(p) for p in [here/'cases.json',here/'origins.json',here/'browser-check.js',here/'browser-result.json',here/'desktop.png',here/'mobile.png']},
    'screenshotsInspected':['desktop.png','mobile.png'],
    'scope':'Local Chromium feasibility; no participants, production deployment, or hosted CI.'
}
(here/'verification.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ['hostSourceHashes','evidenceHashes']},indent=2))
