"""Create and verify a local native binary bundle with explicit file identities."""
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import tarfile

MAX_ARCHIVE = 64 * 1024 * 1024
MAX_CONTENT = 128 * 1024 * 1024


def encode(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def create_bundle(archive, executable, license_text, source, build):
    """Freeze supplied bytes; compiler/host qualification belongs to the caller."""
    archive = Path(archive)
    for key in ['version', 'target']:
        if not isinstance(build.get(key), str) or not re.fullmatch(r'[A-Za-z0-9_.+-]+', build[key]):
            raise ValueError('invalid build ' + key)
    if build.get('profile') != 'release':
        raise ValueError('binary bundles require an explicit release build')
    prefix = 'gwt-' + build['version'] + '-' + build['target']
    readme = f'''# GWT (experimental)

This bundle contains an optimized build for {build['target']}.
It runs the experimental GWT language directly. Consult the accompanying release
notes for the preview scope, source revision, and qualification evidence.

From this extracted directory:

```sh
sh install.sh --prefix "$HOME/.local"
export PATH="$HOME/.local/bin:$PATH"
gwt version --json
gwt test examples/invoice.gwt
gwt run examples/invoice.gwt --request "price invoice" --input examples/invoice.json
```

To remove this installation, run `sh install.sh --prefix "$HOME/.local" --uninstall`.
The installer refuses to overwrite another program, including the old Python CLI.

The request returns a priced decision with exact decimal total "47.88".
The executable needs no Rust or Python installation. It still requires the OS,
architecture, loader, and shared-library versions recorded in manifest.json.
A null interpreter and empty shared-library list indicate a static ELF build.
Consult the separate runtime qualification for tested environments; the target
name alone does not establish compatibility with a distribution or kernel.

Keep manifest.json and the archive checksum with this executable. Their hashes
identify bytes; they are not a publisher signature. The engine source identity
is distinct from the binary hash and does not identify every compiler flag.
Existing cases still require full replay verification with their recorded engine.
The host owns persistence, networking, and other effects around the rules.
'''.encode()
    files = {
        'bin/gwt': (executable, 0o755),
        'LICENSE': (license_text, 0o644),
        'install.sh': ((Path(__file__).resolve().parents[2] / 'packaging/install.sh').read_bytes(), 0o644),
        'README.md': (readme, 0o644),
        'examples/invoice.gwt': (source, 0o644),
        'examples/invoice.json': (encode({'invoice': {'unit_price': '19.95', 'quantity': 2}}), 0o644),
    }
    manifest = {'kind': 'gwt.native-binary-artifact', 'schemaVersion': 1, 'build': build,
                'executable': 'bin/gwt', 'files': {
                    name: {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data), 'mode': mode}
                    for name, (data, mode) in files.items()}}
    files['manifest.json'] = (encode(manifest), 0o644)
    # Explicit ordering and headers make the container deterministic for identical
    # supplied bytes; this does not claim reproducible compilation across hosts.
    with archive.open('xb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w') as tar:
                for name, (data, mode) in sorted(files.items()):
                    info = tarfile.TarInfo(prefix + '/' + name)
                    info.size, info.mode, info.mtime = len(data), mode, 0
                    tar.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with archive.with_name(archive.name + '.sha256').open('x') as checksum:
        checksum.write(digest + '  ' + archive.name + '\n')
    return manifest


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate manifest key')
        result[key] = value
    return result


def verify_and_extract(archive, destination):
    """Check all members before writing; refuse overwrite and undeclared data."""
    archive, destination = Path(archive), Path(destination)
    if archive.stat().st_size > MAX_ARCHIVE:
        raise ValueError('archive exceeds size limit')
    files, root, total = {}, None, 0
    with tarfile.open(archive, 'r:gz') as tar:
        for member in tar:
            path = PurePosixPath(member.name)
            if (not member.isfile() or path.is_absolute() or '..' in path.parts or
                    str(path) != member.name or '\\' in member.name or len(path.parts) < 2):
                raise ValueError('invalid archive member')
            if root is None:
                root = path.parts[0]
            if path.parts[0] != root or member.name in files:
                raise ValueError('duplicate or inconsistent archive root')
            total += member.size
            if total > MAX_CONTENT or member.size < 0 or len(files) >= 10:
                raise ValueError('archive content exceeds limits')
            data = tar.extractfile(member).read()
            if len(data) != member.size:
                raise ValueError('truncated member')
            files[member.name] = (data, member.mode)
    if root is None or root + '/manifest.json' not in files:
        raise ValueError('missing manifest')
    manifest_bytes, mode = files.pop(root + '/manifest.json')
    manifest = json.loads(manifest_bytes, object_pairs_hook=unique_object)
    if (not isinstance(manifest, dict) or mode != 0o644 or manifest.get('kind') != 'gwt.native-binary-artifact' or
            manifest.get('schemaVersion') != 1 or manifest.get('executable') not in ('bin/gwt', 'bin/gwt-native')):
        raise ValueError('invalid manifest')
    build = manifest.get('build')
    if (not isinstance(build, dict) or build.get('profile') != 'release' or
            not all(isinstance(build.get(key), str) and re.fullmatch(r'[A-Za-z0-9_.+-]+', build[key]) for key in ['version', 'target']) or
            root != ('gwt-' if manifest['executable'] == 'bin/gwt' else 'gwt-native-') + build['version'] + '-' + build['target']):
        raise ValueError('invalid build identity')
    expected = manifest.get('files')
    if not isinstance(expected, dict) or {root + '/' + name for name in expected} != set(files):
        raise ValueError('manifest does not cover archive contents')
    for name, item in expected.items():
        data, mode = files[root + '/' + name]
        required_mode = 0o755 if name == manifest['executable'] else 0o644
        if item != {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data), 'mode': required_mode} or mode != required_mode:
            raise ValueError('file identity or mode mismatch: ' + name)
    if manifest['executable'] not in expected:
        raise ValueError('missing executable')
    destination.mkdir(parents=True, exist_ok=False)
    files[root + '/manifest.json'] = (manifest_bytes, 0o644)
    for name, (data, mode) in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
        path.chmod(mode)
    return destination / root, manifest
