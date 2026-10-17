import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from tools.evidence_archive import restore


class EvidenceArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.DEVNULL)
        git('init', '-q')
        (self.repo / 'evaluations').mkdir()
        self.data = b'{"observed": "original", "decision": "pending"}\n'
        (self.repo / 'evaluations/case.json').write_bytes(self.data)
        (self.repo / 'evaluations/README.md').write_text('Original context\n')
        git('add', '.')
        git('-c', 'user.name=Archive Test', '-c', 'user.email=archive@example.test',
            'commit', '-qm', 'original evidence')
        self.manifest = {'revision': git('rev-parse', 'HEAD').decode().strip(), 'files': [
            {'path': 'evaluations/case.json', 'bytes': len(self.data),
             'sha256': hashlib.sha256(self.data).hexdigest()}]}
        # Restoration must use committed bytes, not modified local observations.
        (self.repo / 'evaluations/case.json').write_text('{}')

    def test_restores_original_bytes_and_context_without_overwriting(self):
        output = self.root / 'restored'
        result = restore(self.repo, self.manifest, output)
        self.assertEqual(result['verifiedFiles'], 1)
        self.assertEqual((output / 'evaluations/case.json').read_bytes(), self.data)
        self.assertEqual((output / 'evaluations/README.md').read_text(), 'Original context\n')
        with self.assertRaises(FileExistsError):
            restore(self.repo, self.manifest, output)
        self.assertEqual((output / 'evaluations/case.json').read_bytes(), self.data)

    def test_refuses_changed_checksum_or_size(self):
        for key, value in [('sha256', '0' * 64), ('bytes', len(self.data) + 1)]:
            manifest = json.loads(json.dumps(self.manifest))
            manifest['files'][0][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'do not match'):
                restore(self.repo, manifest, self.root / key)

    def test_requires_immutable_revision(self):
        self.manifest['revision'] = 'main'
        with self.assertRaisesRegex(ValueError, 'full Git commit'):
            restore(self.repo, self.manifest, self.root / 'bad')
        self.assertFalse((self.root / 'bad').exists())
