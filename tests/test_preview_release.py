"""Archive/provenance tests with synthetic bytes, not runtime qualification."""
import copy
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
import zipfile

from evaluations.native_packaging.binary_artifact import create_bundle
from tools.prepare_preview import prepare, sha, TARGETS


class PreviewReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = {'databaseId': 123, 'headSha': 'a' * 40, 'status': 'completed',
                    'conclusion': 'success', 'workflowName': 'Build distribution',
                    'url': 'https://github.com/georgemclaughlin/gwt/actions/runs/123',
                    'jobs': [{'name': f'prepare ({t})', 'conclusion': 'success'} for t in TARGETS]}
        engine = {'sourceDigest': 'fixture-engine', 'profile': 'fixture-only'}
        identity = {'engine': engine}
        for target in TARGETS:
            folder = self.root / ('gwt-preview-' + target)
            folder.mkdir()
            def save(name, obj):
                (folder / name).write_text(json.dumps(obj))
            source = folder / 'gwt-core-0.1.0.crate'
            with tarfile.open(source, 'w') as archive:
                data = json.dumps({'git': {'sha1': self.run['headSha']}}).encode()
                member = tarfile.TarInfo('gwt-core-0.1.0/.cargo_vcs_info.json')
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
            save('dependency-graph.json', [])
            build = {'profile': 'release', 'version': '0.1.0', 'target': target, 'engine': engine,
                     'sourcePackageSha256': sha(source), 'dependencyGraphSha256': sha(folder / 'dependency-graph.json'),
                     'linkage': {'interpreter': None, 'neededLibraries': [],
                                 'glibcVersionSymbols': [] if target.endswith('-musl') else ['GLIBC_2.39']}}
            binary = folder / f'gwt-0.1.0-{target}.tar.gz'
            create_bundle(binary, b'fixture executable', b'MIT fixture', b'THEN true', build)
            import hashlib
            save('qualification.json', {'target': target, 'profile': 'release', 'engine': engine,
                 'binaryBundle': {'archiveSha256': sha(binary), 'caseReplays': 18},
                 'installedExecutableSha256': hashlib.sha256(b'fixture executable').hexdigest(),
                 'packageSha256': sha(source), 'relocatedCaseReplays': 18,
                 **{key: True for key in ('independentFingerprintVerified', 'inspectionMatchesHostAndRelocatedCli',
                                         'versionMatchesHostAndRelocatedCli', 'packageAndHostDependencyGraphsMatch')}})
            save('product.json', {'engine': identity, 'exampleEntriesValidated': 28, 'downloadedCasesCompared': 9,
                 'changedOutcomes': 2, 'expectedFailures': 1,
                 **{key: True for key in ('runtimeWithoutToolchainPath', 'installUpgradeUninstall',
                                         'pythonCollisionRefused', 'siteArtifactsReproduced')}})
            with zipfile.ZipFile(folder / 'delivery-example.zip', 'w') as archive:
                engine_bytes = json.dumps(identity).encode()
                # Fixed headers keep the two independently made fixtures identical.
                archive.writestr(zipfile.ZipInfo('delivery-example/engine.json'), engine_bytes)
                archive.writestr(zipfile.ZipInfo('delivery-example/manifest.json'), json.dumps({
                    'engine': identity, 'files': {'engine.json': hashlib.sha256(engine_bytes).hexdigest()}}))
            (folder / 'delivery-review.html').write_text('synthetic review')
            save('build.json', {'engine': identity, 'artifacts': {
                'downloads/delivery-example.zip': sha(folder / 'delivery-example.zip'),
                'demo/delivery-review.html': sha(folder / 'delivery-review.html')}})

    def test_prepares_exact_assets_with_provenance_and_refuses_overwrite(self):
        output = self.root / 'release'
        result = prepare(self.root, self.run, 'preview-1', output)
        self.assertEqual(result['sourceCommit'], self.run['headSha'])
        self.assertEqual(len(result['files']), 13)
        for name, record in result['files'].items():
            self.assertEqual(sha(output / name), record['sha256'])
        self.assertIn('release-manifest.json', (output / 'SHA256SUMS').read_text())
        with self.assertRaisesRegex(ValueError, 'already exists'):
            prepare(self.root, self.run, 'preview-1', output)

    def test_refuses_failed_run_wrong_commit_or_wrong_engine_before_output(self):
        for label in ('run', 'commit', 'engine'):
            with self.subTest(label=label):
                run = copy.deepcopy(self.run)
                if label == 'run':
                    run['jobs'][0]['conclusion'] = 'failure'
                elif label == 'commit':
                    run['headSha'] = 'b' * 40
                else:
                    path = self.root / ('gwt-preview-' + TARGETS[0]) / 'product.json'
                    record = json.loads(path.read_text())
                    record['engine']['engine']['sourceDigest'] = 'different'
                    path.write_text(json.dumps(record))
                output = self.root / label
                with self.assertRaises(ValueError):
                    prepare(self.root, run, 'preview-1', output)
                self.assertFalse(output.exists())

    def test_refuses_changed_archive_before_output(self):
        binary = self.root / ('gwt-preview-' + TARGETS[0]) / f'gwt-0.1.0-{TARGETS[0]}.tar.gz'
        binary.write_bytes(binary.read_bytes() + b'changed')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            prepare(self.root, self.run, 'preview-1', self.root / 'corrupt')
        self.assertFalse((self.root / 'corrupt').exists())
