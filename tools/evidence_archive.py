"""Restore the historical evaluation tree and verify archived files, without reruns."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def restore(repository, manifest, output):
    revision = manifest['revision']
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise ValueError('archive revision must be a full Git commit ID')
    # Resolve before creating the destination so shallow clones fail cleanly.
    archive = subprocess.run(
        ['git', 'archive', revision, 'evaluations'], cwd=repository,
        check=True, capture_output=True).stdout
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        source.extractall(output, filter='data')
    for entry in manifest['files']:
        path = Path(entry['path'])
        if path.is_absolute() or '..' in path.parts or path.parts[0] != 'evaluations':
            raise ValueError(f'invalid archived path: {path}')
        data = (output / path).read_bytes()
        if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError(f'archived bytes do not match manifest: {path}')
    return {'revision': revision, 'verifiedFiles': len(manifest['files']),
            'output': str(output.resolve())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='new directory; restores original relative paths')
    args = parser.parse_args()
    manifest = json.loads((ROOT / 'evaluations/archive.json').read_text())
    try:
        result = restore(ROOT, manifest, args.output)
    except subprocess.CalledProcessError as error:
        parser.exit(1, error.stderr.decode() + '\nFetch repository history if this is a shallow clone.\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
