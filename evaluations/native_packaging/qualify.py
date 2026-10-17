"""Build an offline Cargo artifact, then qualify an unrelated host and installed CLI.

Run from any directory. All build/install/consumer work takes place outside the
repository; output evidence and the exact package are retained at --output.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
from binary_artifact import create_bundle, verify_and_extract

ROOT=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--toolchain',default='1.96.0')
parser.add_argument('--profile',choices=['dev','release'],default='dev')
parser.add_argument('--target',help='Runnable target triple; defaults to the compiler host')
parser.add_argument('--previous-engine',type=Path)
parser.add_argument('--previous-case',type=Path)
args=parser.parse_args()
assert bool(args.previous_engine)==bool(args.previous_case),'previous engine and case must be supplied together'
args.output=args.output.resolve()
args.output.mkdir(parents=True,exist_ok=False)
crate=ROOT/'crates/gwt-core'
assert (ROOT/'Cargo.lock').read_bytes()==(crate/'engine-dependencies.lock').read_bytes()
workspace=Path(tempfile.mkdtemp(prefix='gwt-package-host-'))
logs=args.output/'commands.log'
commands=[]
build_env=os.environ.copy()
def run(command, *, cwd=workspace, expected=0, env=None):
    commands.append(command)
    result=subprocess.run(command,cwd=cwd,capture_output=True,text=True,env=build_env if env is None else env)
    with logs.open('a') as log:
        log.write(json.dumps(command)+'\n'+result.stderr+'\n')
    assert result.returncode==expected,(command,result.returncode,result.stderr,result.stdout[:1000])
    return result.stdout
cargo=['cargo','+'+args.toolchain]
profile_flags=['--release'] if args.profile=='release' else []
rustc=run(['rustc','+'+args.toolchain,'-vV'])
host_target=next(line.removeprefix('host: ') for line in rustc.splitlines() if line.startswith('host: '))
build_target=args.target or host_target
target_flags=['--target',build_target]
if build_target=='x86_64-unknown-linux-musl':
    # Use the selected compiler's bundled linker; no system musl tools required.
    sysroot=Path(run(['rustc','+'+args.toolchain,'--print','sysroot']).strip())
    linker=sysroot/'lib/rustlib'/host_target/'bin/rust-lld'
    assert linker.is_file(),linker
    build_env.setdefault('CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_LINKER',str(linker))
    build_env.setdefault('CARGO_TARGET_X86_64_UNKNOWN_LINUX_MUSL_RUSTFLAGS','-C link-self-contained=yes -C target-feature=+crt-static')

target=workspace/'build'
run(cargo+['package',*target_flags,'-p','gwt-core','--allow-dirty','--locked','--offline','--target-dir',str(target)],cwd=ROOT)
archive=target/'package/gwt-core-0.1.0.crate'
shutil.copyfile(archive,args.output/archive.name)
extracted=workspace/'extracted'
extracted.mkdir()
with tarfile.open(archive) as package:
    names=package.getnames()
    assert all(not Path(name).is_absolute() and '..' not in Path(name).parts for name in names)
    package.extractall(extracted,filter='data')
artifact=extracted/'gwt-core-0.1.0'
assert (artifact/'LICENSE').read_bytes()==(ROOT/'LICENSE').read_bytes()
assert (artifact/'engine-dependencies.lock').read_bytes()==(ROOT/'Cargo.lock').read_bytes()
assert (artifact/'examples/embed.rs').is_file()
assert not (artifact/'tests/cases.rs').exists() # Repository tests need external domain corpora.
manifest=tomllib.loads((artifact/'Cargo.toml').read_text())
assert manifest['package']['publish'] is False
lock=tomllib.loads((artifact/'Cargo.lock').read_text())
baseline=tomllib.loads((artifact/'engine-dependencies.lock').read_text())
assert lock==baseline
for name,info in manifest['dependencies'].items():
    selected=next(p['version'] for p in baseline['package'] if p['name']==name)
    assert info['version']=='='+selected
unit_output=run(cargo+['test',*profile_flags,*target_flags,'--lib','--manifest-path',str(artifact/'Cargo.toml'),'--target-dir',str(target),'--locked','--offline'])
unit_count=int(re.search(r'test result: ok\. (\d+) passed;',unit_output).group(1))
example=json.loads(run(cargo+['run',*profile_flags,*target_flags,'--example','embed','--manifest-path',str(artifact/'Cargo.toml'),'--target-dir',str(target),'--locked','--offline']))
assert example['ok'] and example['result']['decision']['total']=='47.88'
run(cargo+['install',*target_flags,'--path',str(artifact),'--root',str(workspace/'installed'),'--target-dir',str(target),'--locked','--offline','--profile',args.profile])
native=workspace/'installed/bin/gwt'
assert native.is_file()
source=(artifact/'tests/fixtures/invoice.gwt').read_text()
program=workspace/'program'
program.mkdir()
(program/'invoice.gwt').write_text(source)
bundle={'entry':'invoice.gwt','modules':{'invoice.gwt':source}}
(program/'bundle.json').write_text(json.dumps(bundle))
consumer=workspace/'consumer'
(consumer/'src').mkdir(parents=True)
(consumer/'Cargo.toml').write_text('''[package]
name = "gwt-external-host-qualification"
version = "0.0.0"
edition = "2024"
rust-version = "1.85"
publish = false
[workspace]
[dependencies]
gwt-core = { path = '''+json.dumps(str(artifact))+''' }
serde_json = { version = "=1.0.154", features = ["arbitrary_precision"] }
''')
shutil.copyfile(ROOT/'evaluations/native_packaging/host.rs',consumer/'src/main.rs')
run(cargo+['generate-lockfile','--manifest-path',str(consumer/'Cargo.toml'),'--offline'])
def graph(manifest_path):
    metadata=json.loads(run(cargo+['metadata','--manifest-path',str(manifest_path),'--format-version','1','--locked','--offline','--filter-platform',build_target]))
    packages={p['id']:p for p in metadata['packages']}
    return sorted([{'name':packages[node['id']]['name'],'version':packages[node['id']]['version'],'source':packages[node['id']]['source'],'features':node['features']} for node in metadata['resolve']['nodes'] if packages[node['id']]['source'] is not None],key=lambda p:(p['name'],p['version']))
package_graph=graph(artifact/'Cargo.toml')
host_graph=graph(consumer/'Cargo.toml')
assert host_graph==package_graph,'consumer dependency/feature graph differs from qualified package'
(args.output/'dependency-graph.json').write_text(json.dumps(host_graph,indent=2)+'\n')
shutil.copyfile(consumer/'Cargo.lock',args.output/'host.Cargo.lock')
run(cargo+['clippy',*profile_flags,*target_flags,'--manifest-path',str(consumer/'Cargo.toml'),'--target-dir',str(target),'--locked','--offline','--','-D','warnings'])
host=json.loads(run(cargo+['run',*profile_flags,*target_flags,'--manifest-path',str(consumer/'Cargo.toml'),'--target-dir',str(target),'--locked','--offline','--',str(program/'bundle.json')]))
assert len(host['records'])==18 and host['concurrentExecutions']==288
assert json.loads(run([str(native),'version','--json']))==host['version']
assert host['version']['engine']==host['engine']
assert host['version']['packageVersion']==manifest['package']['version']
assert host['version']['languageProfile']=='gwt-native-experimental'
assert host['version']['languageVersion'] is None
assert json.loads(run([str(native),'inspect',str(program/'invoice.gwt')]))==host['inspection']
# Independently reproduce the v2 content fingerprint with component-wise path ordering.
fields=[p.relative_to(artifact) for p in (artifact/'src').rglob('*') if p.is_file()]
fields += [Path(name) for name in ['build.rs','Cargo.toml','engine-dependencies.lock']]
h=hashlib.sha256(b'gwt-native-engine-source-v2\0')
for field in sorted(fields,key=lambda p:p.parts):
    for data in [str(field).encode(),(artifact/field).read_bytes()]:
        h.update(len(data).to_bytes(8,'big'));h.update(data)
assert host['engine']['sourceDigest']=='sha256:'+h.hexdigest()
checks=[]
for index,row in enumerate(host['records']):
    case=row['case'];record=case['record']
    path=workspace/f'case-{index}.json'
    path.write_text(json.dumps(case,ensure_ascii=False))
    replay=json.loads(run([str(native),'replay',str(path)]))
    assert replay['verified'] and replay['actual']==record['observed']
    if 'request' in record:
        input_path=workspace/'input.json'
        input_path.write_text(json.dumps(record['input'],ensure_ascii=False))
        options=['--request',record['request'],'--input',str(input_path)]
    else:
        options=['--scenario',record['scenario']]
    limits_path=workspace/'limits.json'
    limits_path.write_text(json.dumps(record['limits']))
    options += ['--limits',str(limits_path)]
    actual=json.loads(run([str(native),'run',str(program/'invoice.gwt'),*options],expected=0 if record['observed']['ok'] else 1))
    assert actual==record['observed'],row['id']
    measured=json.loads(run([str(native),'profile',str(program/'invoice.gwt'),*options],expected=0 if record['observed']['ok'] else 1))
    assert measured==row['profile'],row['id']
    capture=json.loads(run([str(native),'capture',str(program/'invoice.gwt'),*options]))
    assert capture==case,row['id']
    checks.append({'id':row['id'],'libraryIndependentExpectation':True,'installedCliReplay':True,'directCliRunAndCapture':True})
# Relocate the package to a different depth, then rebuild without repository ancestors.
relocated=workspace/'other'/'depth'/'package'
shutil.copytree(artifact,relocated)
run(cargo+['build',*profile_flags,*target_flags,'--manifest-path',str(relocated/'Cargo.toml'),'--bin','gwt','--target-dir',str(workspace/'relocated-target'),'--locked','--offline'])
relocated_native=workspace/'relocated-target'/build_target/('release' if args.profile=='release' else 'debug')/'gwt'
assert json.loads(run([str(relocated_native),'inspect',str(program/'invoice.gwt')]))==host['inspection']
assert json.loads(run([str(relocated_native),'--version']))==host['version']
for index,row in enumerate(host['records']):
    replay=json.loads(run([str(relocated_native),'replay',str(workspace/f'case-{index}.json')]))
    assert replay['verified'] and replay['actual']==row['case']['record']['observed']
    record=row['case']['record']
    if 'request' in record:
        input_path=workspace/'input.json'
        input_path.write_text(json.dumps(record['input'],ensure_ascii=False))
        options=['--request',record['request'],'--input',str(input_path)]
    else:
        options=['--scenario',record['scenario']]
    limits_path=workspace/'limits.json'
    limits_path.write_text(json.dumps(record['limits']))
    options += ['--limits',str(limits_path)]
    measured=json.loads(run([str(relocated_native),'profile',str(program/'invoice.gwt'),*options],expected=0 if record['observed']['ok'] else 1))
    assert measured==row['profile'],row['id']
migration=None
if args.previous_engine:
    original=args.previous_case.resolve().read_bytes()
    migration=json.loads(run([str(native),'migrate',str(args.previous_case.resolve()),'--previous-engine',str(args.previous_engine.resolve())]))
    assert migration['status']=='observation_preserved'
    assert migration['candidate']['record']['engine']==host['engine']
    assert args.previous_case.resolve().read_bytes()==original
    (args.output/'packaging-migration.json').write_text(json.dumps(migration,ensure_ascii=False,indent=2)+'\n')
binary_bundle=None
if args.profile=='release':
    dynamic=run(['readelf','--dynamic',str(native)])
    versions=run(['readelf','--version-info',str(native)])
    headers=run(['readelf','--program-headers',str(native)])
    interpreter=re.search(r'Requesting program interpreter: ([^\]]+)',headers)
    linkage={
        'interpreter':interpreter.group(1) if interpreter else None,
        'neededLibraries':sorted(set(re.findall(r'Shared library: \[([^\]]+)\]',dynamic))),
        'glibcVersionSymbols':sorted(set(re.findall(r'GLIBC_[0-9A-Za-z_.]+',versions))),
    }
    if build_target=='x86_64-unknown-linux-musl':
        assert linkage=={'interpreter':None,'neededLibraries':[],'glibcVersionSymbols':[]},linkage
    (args.output/'elf-linkage.txt').write_text(headers+'\n'+dynamic+'\n'+versions)
    build={'profile':'release','version':manifest['package']['version'],'target':build_target,
           'rustc':rustc,'cargo':run(cargo+['--version']),'engine':host['engine'],
           'sourcePackageSha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
           'dependencyGraphSha256':hashlib.sha256((args.output/'dependency-graph.json').read_bytes()).hexdigest(),
           'buildEnvironment':{key:build_env[key] for key in sorted(build_env) if key in ['RUSTFLAGS','CARGO_ENCODED_RUSTFLAGS','CARGO_BUILD_TARGET','CARGO_INCREMENTAL'] or key.startswith(('CARGO_PROFILE_RELEASE_','CARGO_TARGET_'))},
           'linkage':linkage}
    binary_archive=args.output/f"gwt-{manifest['package']['version']}-{build_target}.tar.gz"
    create_bundle(binary_archive,native.read_bytes(),(artifact/'LICENSE').read_bytes(),source.encode(),build)
    binary_root,binary_manifest=verify_and_extract(binary_archive,workspace/'binary-only')
    binary_executable=binary_root/'bin/gwt'
    no_tools={**os.environ,'PATH':''}
    smoke=json.loads(run([str(binary_executable),'run','examples/invoice.gwt','--request','price invoice','--input','examples/invoice.json'],cwd=binary_root,env=no_tools))
    assert smoke['ok'] and smoke['result']['decision']['total']=='47.88'
    run([str(binary_executable),'test','examples/invoice.gwt'],cwd=binary_root,env=no_tools)
    for index,row in enumerate(host['records']):
        replay=json.loads(run([str(binary_executable),'replay',str(workspace/f'case-{index}.json')],cwd=binary_root,env=no_tools))
        assert replay['verified'] and replay['actual']==row['case']['record']['observed']
    (args.output/'binary-manifest.json').write_text(json.dumps(binary_manifest,indent=2)+'\n')
    binary_bundle={'archive':binary_archive.name,'archiveSha256':hashlib.sha256(binary_archive.read_bytes()).hexdigest(),
                   'extractedRoot':str(binary_root),'pathCleared':True,'exampleScenarios':2,'exampleRequest':True,'caseReplays':18,
                   'executableBytes':binary_executable.stat().st_size,'linkage':linkage}
(args.output/'host-observations.json').write_text(json.dumps(host,ensure_ascii=False,indent=2)+'\n')
(args.output/'qualification.json').write_text(json.dumps({'toolchain':args.toolchain,'profile':args.profile,'packageVerificationProfile':'dev','packageVerificationTarget':build_target,'rustc':rustc,'target':build_target,'installedExecutableSha256':hashlib.sha256(native.read_bytes()).hexdigest(),'relocatedExecutableSha256':hashlib.sha256(relocated_native.read_bytes()).hexdigest(),'packageSha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'engine':host['engine'],'independentFingerprintVerified':True,'inspectionMatchesHostAndRelocatedCli':True,'versionMatchesHostAndRelocatedCli':True,'packageAndHostDependencyGraphsMatch':True,'packagedUnitTestsPassed':unit_count,'libraryProfilesVerified':18,'installedAndRelocatedCliProfilesVerified':18,'embeddedScenariosPassed':2,'sharedProgramThreads':4,'concurrentExecutions':288,'checks':checks,'relocatedCaseReplays':18,'previousEngineTransitionVerified':migration is not None,'binaryBundle':binary_bundle,'workspace':str(workspace),'commandCount':len(commands)},indent=2)+'\n')
print(json.dumps({'output':str(args.output),'profile':args.profile,'packageVerified':True,'hostCases':18,'concurrentExecutions':288,'relocationReplays':18,'engine':host['engine']}))
