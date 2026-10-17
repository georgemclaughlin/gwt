"""Verify installed GWT, curated examples, site downloads, and install/upgrade paths."""
import argparse
import ast
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def verify(executable, site=ROOT / 'docs'):
    site = Path(site).resolve()
    executable = Path(executable).resolve(strict=True)
    def run(*args, cwd=ROOT, env=None, code=0):
        process = subprocess.run([str(executable), *map(str, args)], cwd=cwd, env=env,
                                 capture_output=True, text=True, timeout=60)
        assert process.returncode == code, (args, process.stdout, process.stderr)
        return json.loads(process.stdout)
    version = run('version', '--json', env={**os.environ, 'PATH': '/nonexistent'})
    assert version['kind'] == 'gwt.native-version' and version['packageName'] == 'gwt-core'
    assert not (ROOT / 'pyproject.toml').exists()
    assert not list((ROOT / 'gwtlang').glob('*.py'))
    for directory in ('tools', 'examples', 'evaluations', 'tests'):
        for path in (ROOT / directory).rglob('*.py'):
            if any(part.startswith('20') and len(part) >= 10 for part in path.relative_to(ROOT).parts):
                continue
            if '__pycache__' in path.parts:
                continue
            for node in ast.walk(ast.parse(path.read_text())):
                modules = [node.module or ''] if isinstance(node, ast.ImportFrom) else [n.name for n in node.names] if isinstance(node, ast.Import) else []
                assert not any(m == 'gwtlang' or m.startswith('gwtlang.') for m in modules), path
    catalog = json.loads((ROOT / 'examples/catalog.json').read_text())
    for row in catalog['entries']:
        assert run('validate', row['path'])['ok'], row['path']
    with tempfile.TemporaryDirectory(prefix='gwt-product-') as temporary:
        work = Path(temporary)
        spec = importlib.util.spec_from_file_location('site_build', ROOT / 'tools/build_site.py')
        builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
        manifest = builder.build(executable, work / 'site')
        checked = json.loads((site / 'demo/build.json').read_text())
        assert checked == manifest, 'Site artifacts are stale; run tools/build_site.py with the current engine.'
        for name, digest in manifest['artifacts'].items():
            assert hashlib.sha256((site / name).read_bytes()).hexdigest() == digest, name
        archive = work / 'site/downloads/delivery-example.zip'
        with zipfile.ZipFile(archive) as source:
            source.extractall(work / 'download')
        example = work / 'download/delivery-example'
        expected = json.loads((example / 'manifest.json').read_text())
        for name, digest in expected['files'].items():
            assert hashlib.sha256((example / name).read_bytes()).hexdigest() == digest
        minimal = {**os.environ, 'PATH': '/nonexistent'}
        for name in ('delivery.gwt', 'proposed.gwt'):
            assert run('validate', name, cwd=example, env=minimal)['ok']
        result = run('run', 'proposed.gwt', '--request', 'quote delivery', '--input', 'parcel.json', cwd=example, env=minimal)
        assert result['result'] == {'quote': {'status': 'standard', 'fee': 5}}
        review = run('review', 'delivery.corpus.json', '--candidate', 'proposed.gwt', '--html', 'review.html', cwd=example, env=minimal)
        assert review['complete'] and review['totals']['compared'] == 9 and review['totals']['outcomeChanged'] == 2
        assert review['totals']['candidateFailed'] == 1
        # Install and upgrade from a relocated bundle, then refuse an old Python command.
        bundle = work / 'bundle'; (bundle / 'bin').mkdir(parents=True)
        shutil.copy2(executable, bundle / 'bin/gwt'); shutil.copy2(ROOT / 'packaging/install.sh', bundle / 'install.sh')
        prefix = work / 'user install'
        def install(*extra, code=0):
            result = subprocess.run(['/bin/sh', str(bundle / 'install.sh'), '--prefix', str(prefix), *extra],
                                    env={**os.environ, 'PATH': str(work / 'old') + ':/usr/bin:/bin'},
                                    capture_output=True, text=True, timeout=60)
            assert result.returncode == code, (result.stdout, result.stderr)
            return result
        (work / 'old').mkdir(); old = work / 'old/gwt'
        old.write_text('#!/bin/sh\necho \'{"packageName":"gwtlang","packageVersion":"0.3.0"}\'\n');old.chmod(0o755)
        assert 'current shell resolves' in install().stdout
        assert (prefix / 'bin/gwt').read_bytes() == executable.read_bytes()
        install()  # Upgrade an existing Rust installation.
        install('--uninstall'); assert not (prefix / 'bin/gwt').exists()
        shutil.copy2(old, prefix / 'bin/gwt'); before = (prefix / 'bin/gwt').read_bytes()
        assert 'Refusing' in install(code=1).stderr
        assert 'Refusing' in install('--uninstall', code=1).stderr
        assert (prefix / 'bin/gwt').read_bytes() == before
    class Links(HTMLParser):
        def __init__(self): super().__init__(); self.links=[]; self.ids=set()
        def handle_starttag(self, tag, attrs):
            a=dict(attrs)
            if 'href' in a: self.links.append(a['href'])
            if 'id' in a: self.ids.add(a['id'])
    for name in ('index.html', 'getting-started.html', 'installation.html'):
        path=site/name; text=path.read_text(); page=Links();page.feed(text)
        assert 'target/debug' not in text and 'work/native-foundation-checkpoint' not in text
        for href in page.links:
            if href.startswith('#'): assert href[1:] in page.ids, href
            elif not href.startswith(('https:', 'http:')): assert (path.parent/href.split('#')[0].split('?')[0]).exists(), href
    return {'engine': version, 'exampleEntriesValidated': len(catalog['entries']),
            'downloadedCasesCompared': 9, 'changedOutcomes': 2, 'expectedFailures': 1,
            'runtimeWithoutToolchainPath': True, 'installUpgradeUninstall': True,
            'pythonCollisionRefused': True, 'siteArtifactsReproduced': True}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gwt', type=Path, required=True)
    parser.add_argument('--site-root', type=Path, default=ROOT / 'docs')
    args=parser.parse_args()
    print(json.dumps(verify(args.gwt, args.site_root), indent=2))
