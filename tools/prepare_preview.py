"""Prepare verified preview assets from one successful Build distribution run.

Download with `gh run download RUN --dir ARTIFACTS`. Save run metadata with
`gh run view RUN --json databaseId,headSha,status,conclusion,url,workflowName,jobs`.
This command prepares files only; it never tags, uploads, or publishes a release.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluations.native_packaging.binary_artifact import verify_and_extract

TARGETS = ('x86_64-unknown-linux-gnu', 'x86_64-unknown-linux-musl')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def one(root, name):
    paths = list(root.rglob(name))
    if len(paths) != 1:
        raise ValueError(f'expected one {name} under {root}, found {len(paths)}')
    return paths[0]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare(artifacts, run, tag, output):
    require(re.fullmatch(r'preview-[1-9][0-9]*', tag), 'use an explicit preview-N tag')
    require(run['status'] == 'completed' and run['conclusion'] == 'success'
            and run['workflowName'] == 'Build distribution', 'distribution run must pass')
    require(re.fullmatch(r'[0-9a-f]{40}', run['headSha']), 'full source commit required')
    require(run['url'] == f'https://github.com/georgemclaughlin/gwt/actions/runs/{run["databaseId"]}',
            'unexpected workflow repository or run URL')
    require({job['name'] for job in run['jobs']} == {f'prepare ({target})' for target in TARGETS}
            and all(job['conclusion'] == 'success' for job in run['jobs']), 'both target jobs must pass')
    output = Path(output)
    require(not output.exists(), 'output directory already exists')
    assets, builds = {}, {}
    def include(path, name=None):
        name = name or path.name
        if name in assets:
            require(path.read_bytes() == assets[name].read_bytes(), f'targets disagree on {name}')
        else:
            assets[name] = path
    with tempfile.TemporaryDirectory(prefix='gwt-preview-check-') as temporary:
        for target in TARGETS:
            folder = Path(artifacts) / ('gwt-preview-' + target)
            q_path = one(folder, 'qualification.json')
            q = json.loads(q_path.read_text())
            product_path = one(folder, 'product.json')
            product = json.loads(product_path.read_text())
            binary = one(folder, f'gwt-0.1.0-{target}.tar.gz')
            checksum = one(folder, binary.name + '.sha256')
            require(checksum.read_text().split() == [sha(binary), binary.name], 'binary checksum mismatch')
            extracted, manifest = verify_and_extract(binary, Path(temporary) / target)
            build = manifest['build']
            source = one(folder, 'gwt-core-0.1.0.crate')
            graph = one(folder, 'dependency-graph.json')
            require(q['target'] == build['target'] == target and q['profile'] == 'release', 'target/profile mismatch')
            require(q['binaryBundle']['archiveSha256'] == sha(binary), 'qualification refers to different binary archive')
            require(q['installedExecutableSha256'] == sha(extracted / manifest['executable']), 'qualification refers to different executable')
            require(q['packageSha256'] == build['sourcePackageSha256'] == sha(source), 'source package mismatch')
            with tarfile.open(source) as package:
                vcs = json.load(package.extractfile('gwt-core-0.1.0/.cargo_vcs_info.json'))
            require(vcs['git']['sha1'] == run['headSha'] and not vcs['git'].get('dirty', False),
                    'source package is not the clean workflow revision')
            require(build['dependencyGraphSha256'] == sha(graph), 'dependency graph mismatch')
            require(q['engine'] == build['engine'] == product['engine']['engine'], 'qualified engine mismatch')
            require(product['exampleEntriesValidated'] == 28 and product['downloadedCasesCompared'] == 9
                    and product['changedOutcomes'] == 2 and product['expectedFailures'] == 1,
                    'unexpected product qualification counts')
            for key in ('runtimeWithoutToolchainPath', 'installUpgradeUninstall',
                        'pythonCollisionRefused', 'siteArtifactsReproduced'):
                require(product[key] is True, f'product gate missing: {key}')
            for key in ('independentFingerprintVerified', 'inspectionMatchesHostAndRelocatedCli',
                        'versionMatchesHostAndRelocatedCli', 'packageAndHostDependencyGraphsMatch'):
                require(q[key] is True, f'package gate missing: {key}')
            require(q['relocatedCaseReplays'] == q['binaryBundle']['caseReplays'] == 18,
                    'package replay coverage missing')
            if target.endswith('-musl'):
                require(build['linkage'] == {'interpreter': None, 'neededLibraries': [], 'glibcVersionSymbols': []},
                        'static build has dynamic dependencies')
            else:
                versions = build['linkage']['glibcVersionSymbols']
                require(max(tuple(map(int, v.removeprefix('GLIBC_').split('.'))) for v in versions) == (2, 39),
                        'update documented GNU runtime requirements')
            site_path = one(folder, 'build.json')
            site = json.loads(site_path.read_text())
            example = one(folder, 'delivery-example.zip')
            review = one(folder, 'delivery-review.html')
            require(site['engine'] == product['engine'], 'site engine mismatch')
            require(site['artifacts']['downloads/delivery-example.zip'] == sha(example)
                    and site['artifacts']['demo/delivery-review.html'] == sha(review), 'site bytes mismatch')
            with zipfile.ZipFile(example) as archive:
                prefix = 'delivery-example/'
                identity = json.loads(archive.read(prefix + 'engine.json'))
                require(identity == product['engine'], 'example engine mismatch')
                index = json.loads(archive.read(prefix + 'manifest.json'))
                require(index['engine'] == identity, 'example manifest engine mismatch')
                require(set(archive.namelist()) == {prefix + name for name in index['files']} | {prefix + 'manifest.json'},
                        'example manifest does not cover ZIP')
                for name, digest in index['files'].items():
                    require(hashlib.sha256(archive.read(prefix + name)).hexdigest() == digest, 'example checksum mismatch')
            for path in (binary, checksum, source, example, review):
                include(path)
            include(q_path, target + '-qualification.json')
            include(product_path, target + '-product.json')
            include(graph, target + '-dependencies.json')
            builds[target] = build
        require(len({json.dumps(build['engine'], sort_keys=True) for build in builds.values()}) == 1,
                'targets have different engines')
        release = {'kind': 'gwt.preview-release', 'schemaVersion': 1, 'tag': tag,
                   'sourceCommit': run['headSha'], 'workflow': run['url'], 'builds': builds,
                   'files': {name: {'sha256': sha(path), 'bytes': path.stat().st_size}
                             for name, path in sorted(assets.items())}}
        output.mkdir(parents=True, exist_ok=False)
        for name, path in assets.items():
            shutil.copyfile(path, output / name)
        (output / 'release-manifest.json').write_text(json.dumps(release, indent=2) + '\n')
        checksums = ''.join(f'{sha(path)}  {path.name}\n' for path in sorted(output.iterdir()))
        (output / 'SHA256SUMS').write_text(checksums)
    return release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--run-info', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.artifacts, json.loads(args.run_info.read_text()), args.tag, args.output)
    print(json.dumps({'tag': result['tag'], 'sourceCommit': result['sourceCommit'],
                      'verifiedAssets': len(result['files']), 'output': str(args.output)}, indent=2))


if __name__ == '__main__':
    main()
