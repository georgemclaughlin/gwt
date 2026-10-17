"""Freshly assess browser-saved synthetic choices and exercise separate case export."""
import argparse
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('fixtures', type=Path)
parser.add_argument('choices', type=Path)
parser.add_argument('output', type=Path)
parser.add_argument('--native', default='target/debug/gwt')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
results = []
for folder in sorted(args.fixtures.iterdir()):
    if not folder.is_dir():
        continue
    original = folder / 'original.json'
    frozen = original.read_bytes()
    executable = (folder / 'engine.txt').read_text()
    decision = args.choices / (folder.name + '.decision.json')
    saved = json.loads(decision.read_text())
    proposal = json.loads((folder / 'proposal.json').read_text())
    base = [str(original), '--previous-engine', executable, '--decision', str(decision)]
    assessed = subprocess.run([args.native, 'assess-migration', *base], capture_output=True, text=True, check=True)
    assessment = json.loads(assessed.stdout)
    assert assessment['status'] == saved['status']
    assert assessment['proposalIntegrity'] == proposal['integrity']
    assert assessment['accepted'] == (saved['status'] == 'accept')
    destination = args.output / (folder.name + '.case.json')
    command = [args.native, 'export-migration', *base, '--output', str(destination)]
    exported = subprocess.run(command, capture_output=True, text=True)
    assert (exported.returncode == 0) == assessment['accepted']
    assert destination.exists() == assessment['accepted']
    if assessment['accepted']:
        content = destination.read_bytes()
        assert json.loads(content) == proposal['candidate']
        replay = subprocess.run([args.native, 'replay', str(destination)], capture_output=True, text=True, check=True)
        assert json.loads(replay.stdout)['verified']
        refused = subprocess.run(command, capture_output=True, text=True)
        assert refused.returncode != 0
        assert destination.read_bytes() == content
        (args.output / (folder.name + '.export.json')).write_text(exported.stdout)
    assert original.read_bytes() == frozen
    (args.output / (folder.name + '.proposal.json')).write_text((folder / 'proposal.json').read_text())
    results.append({'id': folder.name, 'assessment': assessment, 'exported': assessment['accepted'], 'originalUnchanged': True})
assert len(results) == 18
assert sum(item['exported'] for item in results) == 1
# A valid acceptance from another proposal cannot create an output file.
wrong_folder = args.fixtures / 'changed-message-exact-prints'
refused_path = args.output / 'stale-must-not-exist.json'
stale = subprocess.run([args.native, 'export-migration', str(wrong_folder / 'original.json'), '--previous-engine', (wrong_folder / 'engine.txt').read_text(), '--decision', str(args.choices / 'preserved-exact-prints.decision.json'), '--output', str(refused_path)], capture_output=True, text=True)
assert stale.returncode != 0
assert json.loads(stale.stdout)['diagnostic']['code'] == 'migration_decision_stale'
assert not refused_path.exists()
(args.output / 'assessments.json').write_text(json.dumps({'cases': results, 'staleExportRefused': True}, indent=2) + '\n')
print(json.dumps({'assessed': len(results), 'exportedSyntheticCases': 1, 'staleExportRefused': True}))
