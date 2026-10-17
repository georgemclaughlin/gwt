import copy
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

from evaluations.native_packaging.binary_artifact import create_bundle, verify_and_extract, MAX_CONTENT


class NativeBinaryArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='gwt-binary-artifact-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive = self.root / 'first.tar.gz'
        self.build = {'version': '0.1.0', 'profile': 'release', 'target': 'x86_64-unknown-linux-gnu',
                      'engine': {'sourceDigest': 'fixture-only'}}
        # These tests qualify archive handling, not a runnable compiler artifact.
        self.executable = b'fixture executable bytes\x00\xff'
        self.source = '# café 😀\nTHEN true\n'.encode()
        create_bundle(self.archive, self.executable, b'MIT license fixture\n', self.source, self.build)

    def members(self):
        with tarfile.open(self.archive, 'r:gz') as archive:
            return [(copy.copy(member), archive.extractfile(member).read()) for member in archive]

    def rewritten(self, members, name='modified.tar.gz'):
        path = self.root / name
        with tarfile.open(path, 'w:gz') as archive:
            for member, content in members:
                member = copy.copy(member)
                if content is not None:
                    member.size = len(content)
                archive.addfile(member, None if content is None else io.BytesIO(content))
        return path

    def test_deterministic_container_preserves_bytes_modes_and_identities(self):
        second = self.root / 'second.tar.gz'
        create_bundle(second, self.executable, b'MIT license fixture\n', self.source, self.build)
        self.assertEqual(self.archive.read_bytes(), second.read_bytes())
        checksum = self.archive.with_name(self.archive.name + '.sha256').read_text().split()[0]
        self.assertEqual(checksum, hashlib.sha256(self.archive.read_bytes()).hexdigest())
        root, manifest = verify_and_extract(self.archive, self.root / 'extracted')
        self.assertEqual((root / 'bin/gwt').read_bytes(), self.executable)
        self.assertEqual((root / 'examples/invoice.gwt').read_bytes(), self.source)
        self.assertEqual((root / 'bin/gwt').stat().st_mode & 0o777, 0o755)
        self.assertEqual((root / 'LICENSE').stat().st_mode & 0o777, 0o644)
        self.assertEqual(manifest['build'], self.build)
        self.assertEqual(json.loads((root / 'examples/invoice.json').read_text()),
                         {'invoice': {'unit_price': '19.95', 'quantity': 2}})

    def test_changed_content_or_modes_fail_before_writing(self):
        for label in ['bytes', 'mode']:
            with self.subTest(label=label):
                members = self.members()
                for index, (member, content) in enumerate(members):
                    if member.name.endswith('/bin/gwt'):
                        if label == 'bytes':
                            members[index] = (member, content + b'changed')
                        else:
                            member.mode = 0o4755
                destination = self.root / ('failed-' + label)
                with self.assertRaisesRegex(ValueError, 'identity or mode'):
                    verify_and_extract(self.rewritten(members, label + '.tar.gz'), destination)
                self.assertFalse(destination.exists())

    def test_unsafe_duplicate_or_undeclared_members_are_refused(self):
        for label in ['traversal', 'absolute', 'symlink', 'duplicate', 'undeclared']:
            with self.subTest(label=label):
                members = self.members()
                extra = copy.copy(members[0][0])
                if label == 'traversal':
                    extra.name = '../outside'
                elif label == 'absolute':
                    extra.name = '/outside'
                elif label == 'symlink':
                    extra.type, extra.linkname = tarfile.SYMTYPE, '../../outside'
                elif label == 'undeclared':
                    extra.name = extra.name.split('/')[0] + '/surprise'
                members.append((extra, b''))
                destination = self.root / ('failed-' + label)
                with self.assertRaises(ValueError):
                    verify_and_extract(self.rewritten(members, label + '.tar.gz'), destination)
                self.assertFalse(destination.exists())
        self.assertFalse((self.root / 'outside').exists())

    def test_manifest_shape_identity_and_duplicate_keys_are_checked(self):
        for label in ['list', 'profile', 'root', 'duplicate', 'missing-executable']:
            with self.subTest(label=label):
                members = self.members()
                for index, (member, content) in enumerate(members):
                    if member.name.endswith('/manifest.json'):
                        manifest = json.loads(content)
                        if label == 'list':
                            content = b'[]'
                        elif label == 'duplicate':
                            content = content.replace(b'"schemaVersion": 1', b'"schemaVersion": 1, "schemaVersion": 1')
                        else:
                            if label == 'profile':
                                manifest['build']['profile'] = 'dev'
                            elif label == 'root':
                                manifest['build']['target'] = 'another-target'
                            else:
                                del manifest['files']['bin/gwt']
                            content = json.dumps(manifest).encode()
                        members[index] = (member, content)
                destination = self.root / ('failed-' + label)
                with self.assertRaises(ValueError):
                    verify_and_extract(self.rewritten(members, label + '.tar.gz'), destination)
                self.assertFalse(destination.exists())

    def test_oversized_content_is_rejected_before_payload_read_or_writes(self):
        member = tarfile.TarInfo('bundle/large')
        member.size = MAX_CONTENT + 1
        archive = self.root / 'oversized.tar.gz'
        archive.write_bytes(gzip.compress(member.tobuf() + b'\x00' * 1024))
        destination = self.root / 'failed-size'
        with self.assertRaisesRegex(ValueError, 'exceeds limits'):
            verify_and_extract(archive, destination)
        self.assertFalse(destination.exists())

    def test_existing_archives_and_extractions_are_not_overwritten(self):
        original = self.archive.read_bytes()
        with self.assertRaises(FileExistsError):
            create_bundle(self.archive, b'changed', b'other', self.source, self.build)
        self.assertEqual(self.archive.read_bytes(), original)
        destination = self.root / 'occupied'
        destination.mkdir()
        sentinel = destination / 'user-file'
        sentinel.write_bytes(b'preserve')
        with self.assertRaises(FileExistsError):
            verify_and_extract(self.archive, destination)
        self.assertEqual(list(destination.iterdir()), [sentinel])
        self.assertEqual(sentinel.read_bytes(), b'preserve')
