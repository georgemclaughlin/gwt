"""Check an extracted release bundle in explicitly supplied local Linux images."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualification', type=Path, required=True)
    parser.add_argument('--image', action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    package = args.qualification.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = json.loads((package / 'qualification.json').read_text())
    assert report['profile'] == 'release' and report['binaryBundle']['pathCleared']
    root = Path(report['binaryBundle']['extractedRoot'])
    executable = root / 'bin/gwt'
    assert hashlib.sha256(executable.read_bytes()).hexdigest() == report['installedExecutableSha256']
    host = json.loads((package / 'host-observations.json').read_text())
    cases = output / 'cases'
    cases.mkdir()
    for index, record in enumerate(host['records']):
        (cases / f'{index}.json').write_text(json.dumps(record['case']) + '\n')
    checks, commands = [], []

    def command(argv):
        result = subprocess.run(argv, text=True, capture_output=True, timeout=60)
        commands.append({'command': argv, 'exitCode': result.returncode, 'stderr': result.stderr, 'stdout': result.stdout})
        (output / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        return result

    for requested in args.image:
        inspection = command(['docker', 'image', 'inspect', requested])
        assert inspection.returncode == 0, inspection.stderr
        image = json.loads(inspection.stdout)[0]
        identity = image['Id']
        common = ['docker', 'run', '--rm', '--network', 'none', '--read-only', '--env', 'PATH=',
                  '--mount', f'type=bind,src={root},dst=/native,readonly',
                  '--mount', f'type=bind,src={cases},dst=/cases,readonly', '--workdir', '/native']
        libc = command([*common, '--entrypoint', '/usr/bin/getconf', identity, 'GNU_LIBC_VERSION'])
        if libc.returncode == 0:
            libc_description = libc.stdout.strip()
        else:
            # Alpine has no getconf. Inspect its actual loader rather than
            # inferring libc from a mutable image tag.
            musl = command([*common, '--entrypoint', '/lib/ld-musl-x86_64.so.1', identity, '--version'])
            assert 'musl libc' in musl.stderr and 'Version ' in musl.stderr, (libc.stderr, musl.stderr)
            libc_description = musl.stderr.strip()
        kernel = command([*common, '--entrypoint', '/bin/uname', identity, '-srmo'])
        assert kernel.returncode == 0, kernel.stderr
        prefix = [*common, '--entrypoint', '/native/bin/gwt', identity]
        smoke = command([*prefix, 'run', 'examples/invoice.gwt', '--request', 'price invoice', '--input', 'examples/invoice.json'])
        entry = {'requestedImage': requested, 'imageId': identity, 'repoDigests': image.get('RepoDigests', []),
                 'architecture': image['Architecture'], 'os': image['Os'], 'libc': libc_description, 'kernel': kernel.stdout.strip(),
                 'requestExitCode': smoke.returncode}
        if smoke.returncode and 'GLIBC_' in smoke.stderr and 'not found' in smoke.stderr:
            entry.update({'status': 'incompatible_libc', 'loaderDiagnostic': smoke.stderr, 'verifiedCaseReplays': 0})
            checks.append(entry)
            continue
        assert smoke.returncode == 0, smoke.stderr + smoke.stdout
        observed = json.loads(smoke.stdout)
        normal = next(row for row in host['records'] if row['id'] == 'normal')['case']['record']['observed']
        assert observed == normal
        if 'inspection' in host:
            inspected = command([*prefix, 'inspect', 'examples/invoice.gwt'])
            assert inspected.returncode == 0, inspected.stdout + inspected.stderr
            assert json.loads(inspected.stdout) == host['inspection']
            entry['inspectionMatchesHost'] = True
        normal_row = next(row for row in host['records'] if row['id'] == 'normal')
        if 'profile' in normal_row:
            profiled = command([*prefix, 'profile', 'examples/invoice.gwt', '--request', 'price invoice', '--input', 'examples/invoice.json'])
            assert profiled.returncode == 0, profiled.stdout + profiled.stderr
            assert json.loads(profiled.stdout) == normal_row['profile']
            entry['profileMatchesHost'] = True
        tested = command([*prefix, 'test', 'examples/invoice.gwt'])
        assert tested.returncode == 0, tested.stdout + tested.stderr
        for index, row in enumerate(host['records']):
            replay = command([*prefix, 'replay', f'/cases/{index}.json'])
            assert replay.returncode == 0, replay.stdout + replay.stderr
            replay = json.loads(replay.stdout)
            assert replay['verified'] and replay['actual'] == row['case']['record']['observed']
        entry.update({'status': 'qualified', 'exampleScenarios': 2, 'exactExampleObservation': True,
                      'verifiedCaseReplays': len(host['records'])})
        checks.append(entry)
    assert any(row['status'] == 'qualified' for row in checks)
    result = {'kind': 'gwt.native-binary-runtime-qualification', 'schemaVersion': 1,
              'binarySha256': report['installedExecutableSha256'], 'engine': report['engine'],
              'profile': report['profile'], 'toolchain': report['toolchain'],
              'target': report['target'], 'linkage': report['binaryBundle']['linkage'],
              'networkDisabled': True, 'pathCleared': True, 'readOnlyFilesystem': True,
              'checks': checks, 'commands': commands}
    (output / 'qualification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'toolchain': report['toolchain'], 'checks': checks}))


if __name__ == '__main__':
    main()
