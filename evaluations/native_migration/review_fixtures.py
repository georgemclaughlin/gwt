"""Regenerate offline reviews by replaying retained cases with real previous engines."""
import argparse
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('cases', type=Path)
parser.add_argument('output', type=Path)
parser.add_argument('--previous-engine', required=True)
parser.add_argument('--changed-engine', required=True)
parser.add_argument('--native', default='target/debug/gwt')
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
results = []
for variant, executable in [('preserved', args.previous_engine), ('changed-message', args.changed_engine)]:
    for case in sorted((args.cases / variant).glob('*.original.json')):
        name = variant + '-' + case.name.removesuffix('.original.json')
        folder = args.output / name
        folder.mkdir()
        original = case.read_bytes()
        result = subprocess.run([
            args.native, 'migrate', str(case), '--previous-engine', executable,
            '--html', str(folder / 'review.html'),
            '--decision-template', str(folder / 'decision.json'),
        ], capture_output=True, text=True, check=True)
        proposal = json.loads(result.stdout)
        assert case.read_bytes() == original
        assert proposal['original'] == json.loads(original)
        assert proposal['approved'] is False
        (folder / 'proposal.json').write_text(result.stdout)
        (folder / 'original.json').write_bytes(original)
        (folder / 'engine.txt').write_text(str(Path(executable).resolve()))
        results.append({'id': name, 'status': proposal['status'], 'changes': proposal['changes'], 'proposalIntegrity': proposal['integrity']})
assert len(results) == 18
(args.output / 'generation.json').write_text(json.dumps(results, indent=2) + '\n')
