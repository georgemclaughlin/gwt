"""Build a local browser preview against an explicitly selected core source artifact."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tomllib

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--core', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--toolchain', default='1.96.0')
args = parser.parse_args()
core = args.core.resolve()
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=False)
here = Path(__file__).resolve().parent
def registry(path):
    return {(item['name'], item['version'], item.get('checksum')) for item in tomllib.loads(path.read_text())['package'] if 'source' in item}
if registry(here/'bridge/Cargo.lock') != registry(core/'engine-dependencies.lock'):
    raise SystemExit('Bridge registry dependencies differ from the selected core baseline.')
bridge = output/'bridge'
shutil.copytree(here/'bridge', bridge, ignore=shutil.ignore_patterns('target'))
manifest = (bridge/'Cargo.toml').read_text().replace('"../../../crates/gwt-core"', json.dumps(str(core)))
(bridge/'Cargo.toml').write_text(manifest)
environment = dict(os.environ)
environment['CARGO_TARGET_DIR'] = str(output/'target')
environment['CARGO_TARGET_WASM32_UNKNOWN_UNKNOWN_RUSTFLAGS'] = '-C link-arg=--max-memory=67108864'
commands = []
for label, flags in [('tests',['test']),('clippy',['clippy','--all-targets','--','-D','warnings']),('wasm',['build','--release','--target','wasm32-unknown-unknown'])]:
    command = ['rustup','run',args.toolchain,'cargo',flags[0],'--manifest-path',str(bridge/'Cargo.toml'),'--locked','--offline',*flags[1:]]
    with (output/(label+'.log')).open('w') as log:
        result = subprocess.run(command, env=environment, stdout=log, stderr=subprocess.STDOUT)
    commands.append({'command':command,'exitCode':result.returncode})
    if result.returncode: raise SystemExit(f'{label} failed; see {output/(label+".log")}')
    print(label + ' passed',flush=True)
for name in ['index.html','preview.mjs','worker.mjs']:
    shutil.copyfile(here/name, output/name)
wasm = output/'gwt_browser_preview.wasm'
shutil.copyfile(output/'target/wasm32-unknown-unknown/release/gwt_browser_preview.wasm', wasm)
source = (core/'tests/fixtures/invoice.gwt').read_text()
(output/'bundle.json').write_text(json.dumps({'entry':'invoice.gwt','modules':{'invoice.gwt':source}},indent=2)+'\n')
(output/'build.json').write_text(json.dumps({'core':str(core),'toolchain':args.toolchain,'commands':commands,'wasmBytes':wasm.stat().st_size,'wasmSha256':hashlib.sha256(wasm.read_bytes()).hexdigest(),'rustflags':environment['CARGO_TARGET_WASM32_UNKNOWN_UNKNOWN_RUSTFLAGS']},indent=2)+'\n')
