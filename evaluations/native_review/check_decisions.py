"""Check synthetic browser-downloaded decisions against freshly executed native reviews."""
import argparse
import json
from pathlib import Path, PurePosixPath
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument('fixtures', type=Path)
parser.add_argument('browser_output', type=Path)
parser.add_argument('--native', type=Path, default=ROOT / 'target/debug/gwt')
parser.add_argument('--expected-count', type=int, default=5)
args = parser.parse_args()
results = []
for report_path in sorted(args.fixtures.resolve().glob('*/review.json')):
    report = json.loads(report_path.read_text())
    source = report['sources'][report['candidateIdentity']['digest']]
    decision_path = args.browser_output.resolve() / ('decisions-' + report_path.parent.name + '.json')
    with tempfile.TemporaryDirectory(prefix='gwt-decision-assessment-') as temporary:
        directory = Path(temporary)
        for name, text in source['modules'].items():
            logical = PurePosixPath(name)
            if logical.is_absolute() or '..' in logical.parts:
                raise ValueError('invalid fixture module path')
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        command = [str(args.native.resolve()), 'assess-review', str(report_path.parent / 'corpus.json'),
                   '--candidate', str(directory / source['entry']), '--import-root', str(directory),
                   '--decisions', str(decision_path)]
        result = subprocess.run(command, check=False, text=True, capture_output=True)
        assessment = json.loads(result.stdout)
        assert assessment['kind'] == 'gwt.native-review-assessment', assessment
        assert assessment['reviewer'] == 'Synthetic browser test reviewer'
        assert assessment['rejected'] == 1 and assessment['accepted'] == 0
        assert assessment['pending'] == report['totals']['total'] - 1
        assert assessment['needsInformation'] == 0 and not assessment['allAccepted']
        assert result.returncode == 1
        results.append({'workflow': report_path.parent.name, 'assessment': assessment})
assert results and len(results) == args.expected_count
(args.browser_output / 'cli-assessment-report.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results))
