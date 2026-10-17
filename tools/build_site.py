"""Generate the public worked review and standalone example from checked sources."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
syntax_spec = importlib.util.spec_from_file_location('site_syntax', ROOT / 'tools/highlight_site.py')
syntax = importlib.util.module_from_spec(syntax_spec)
syntax_spec.loader.exec_module(syntax)


def build(executable, destination):
    spec = importlib.util.spec_from_file_location('walkthrough', ROOT / 'examples/native_review_walkthrough/prepare.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    destination = Path(destination)
    (destination / 'demo').mkdir(parents=True, exist_ok=True)
    (destination / 'downloads').mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='gwt-site-build-') as temporary:
        output = Path(temporary) / 'review'
        summary = helper.prepare(executable, output)
        (destination / 'demo/delivery-review.html').write_text(syntax.highlight_review((output / 'review.html').read_text()))
        files = {
            'delivery.gwt': (ROOT / 'examples/native_delivery/rules.gwt').read_bytes(),
            'proposed.gwt': (ROOT / 'examples/native_review_walkthrough/candidate.gwt').read_bytes(),
            'parcel.json': (ROOT / 'examples/native_review_walkthrough/input.json').read_bytes(),
            'delivery.corpus.json': (output / 'corpus.json').read_bytes(),
            'expected-cases.json': (ROOT / 'examples/native_review_walkthrough/cases.json').read_bytes(),
            'engine.json': (output / 'version.json').read_bytes(),
            'LICENSE': (ROOT / 'LICENSE').read_bytes(),
            'README.md': b'''# Delivery policy walkthrough

Use the matching GWT development build identified in engine.json.
From this directory with the installed gwt command:

```sh
gwt version --json
gwt validate delivery.gwt
gwt validate proposed.gwt
gwt run proposed.gwt --request "quote delivery" --input parcel.json
gwt review delivery.corpus.json --candidate proposed.gwt --html delivery-review.html
```

Open delivery-review.html. Nine cases compare; two fees change from 9 to 5.
The zero-weight failure is preserved. Review decisions start pending.
expected-cases.json contains independent expected before/after results.
A different engine must migrate the original cases explicitly; a source or
engine change may change the identity of the report and invalidate old decisions.
These are illustrative fixtures, not participant responses or a public release.
''',
        }
        files['manifest.json'] = (json.dumps({
            'kind': 'gwt.delivery-example', 'schemaVersion': 1,
            'engine': json.loads(files['engine.json']),
            'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
        }, indent=2) + '\n').encode()
        archive = destination / 'downloads/delivery-example.zip'
        # Store this small example without compression: zlib versions can emit
        # different bytes for identical input on development and CI machines.
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as bundle:
            for name, data in sorted(files.items()):
                info = zipfile.ZipInfo('delivery-example/' + name, (2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_STORED
                info.create_system = 3
                info.external_attr = 0o100644 << 16
                bundle.writestr(info, data)
        checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
        archive.with_suffix('.zip.sha256').write_text(checksum + '  ' + archive.name + '\n')
        manifest = {'kind': 'gwt.site-build', 'schemaVersion': 1,
                    'engine': json.loads(files['engine.json']),
                    'sources': {**summary['sourceSha256'], **{path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in ['tools/build_site.py', 'tools/highlight_site.py', 'tools/gwt_syntax.py', 'crates/gwt-core/src/vocabulary.json']}},
                    'reviewTotals': summary['reviewTotals'],
                    'artifacts': {str(p.relative_to(destination)): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in [destination / 'demo/delivery-review.html', archive]}}
        (destination / 'demo/build.json').write_text(json.dumps(manifest, indent=2) + '\n')
        return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gwt', type=Path, default=ROOT / 'target/debug/gwt')
    parser.add_argument('--output', type=Path, default=ROOT / 'docs')
    args = parser.parse_args()
    print(json.dumps(build(args.gwt.resolve(), args.output), indent=2))
