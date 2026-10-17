"""Inventory native example validation without treating paired inputs as entries."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess


def summarize(records):
    categories, diagnostics = Counter(), Counter()
    attempted = passed = failed = 0
    for record in records:
        validation = record.get('validation')
        if validation is None:
            categories['python_paired_input'] += 1
            continue
        results = validation.get('results', [])
        attempted += len(results)
        passed += sum(row['ok'] for row in results)
        failed += sum(not row['ok'] for row in results)
        if validation['ok']:
            categories['validated'] += 1
            continue
        # A failed scenario gate can have no gate-level diagnostic: each
        # execution owns its diagnostic. Do not label that "not exercised".
        phase = next(name for name in ('load', 'check', 'format', 'scenarios')
                     if validation[name]['status'] != 'passed')
        status = validation[phase]['status']
        categories[f'{phase}:{status}'] += 1
        diagnostic = validation[phase].get('diagnostic')
        if diagnostic:
            diagnostics[diagnostic['code']] += 1
        if phase == 'scenarios':
            for row in results:
                if row.get('diagnostic'):
                    diagnostics[row['diagnostic']['code']] += 1
    return dict(files=len(records), categories=dict(categories), diagnostics=dict(diagnostics),
                scenarioExecutions=attempted, scenariosPassed=passed, scenariosFailed=failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    native = args.native.resolve()
    digest = hashlib.sha256(native.read_bytes()).hexdigest()
    pairs = {str(p): str(p.parent/'rules.gwt') for p in Path('examples').glob('*/request*.gwt')
             if (p.parent/'rules.gwt').is_file()}
    sources = {str(p): p.read_text() for p in sorted(Path('examples').rglob('*.gwt'))}
    records = []
    for path, source in sources.items():
        record = dict(path=path, sha256=hashlib.sha256(source.encode()).hexdigest())
        if path in pairs:
            record.update(role='python_paired_input', pairedRules=pairs[path])
        else:
            process = subprocess.run([str(native), 'validate', path], text=True,
                                     capture_output=True, timeout=30)
            validation = json.loads(process.stdout)
            assert process.returncode in (0, 1), (path, process.stderr)
            assert (process.returncode == 0) == validation['ok'], path
            record.update(role='entry_or_module', exitCode=process.returncode,
                          validation=validation)
        records.append(record)
    assert all(Path(path).read_text() == source for path, source in sources.items())
    assert hashlib.sha256(native.read_bytes()).hexdigest() == digest
    report = dict(nativeExecutable=str(native), nativeSha256=digest, files=records,
                  summary=summarize(records), humanParticipants=0,
                  scope='First blocking phase per entry; paired Python inputs are not executed standalone. No completeness, production, or external-pilot claim.')
    (output/'audit.json').write_text(json.dumps(report, indent=2)+'\n')
    (output/'sources.json').write_text(json.dumps(sources, indent=2)+'\n')
    print(json.dumps(report['summary']))


if __name__ == '__main__':
    main()
