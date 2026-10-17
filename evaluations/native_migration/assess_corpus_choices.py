"""Reexecute every row before assessing browser choices and exporting a separate corpus."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
parser=argparse.ArgumentParser()
parser.add_argument('fixtures',type=Path)
parser.add_argument('choices',type=Path)
parser.add_argument('output',type=Path)
parser.add_argument('--native',default='target/debug/gwt')
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)
results=[]
for variant in ['complete','incomplete']:
    folder=args.fixtures/variant
    original=(folder/'corpus.json').read_bytes()
    original_value=json.loads(original)
    report=json.loads((folder/'report.json').read_text())
    decisions=args.choices/(variant+'.decisions.json')
    base=[str(folder/'corpus.json'),'--engines',str(folder/'engines.json'),'--decisions',str(decisions)]
    assessed=subprocess.run([args.native,'assess-corpus-migration',*base],capture_output=True,text=True,check=True)
    assessment=json.loads(assessed.stdout)
    assert assessment['allAccepted']==(variant=='complete')
    assert assessment['accepted']==report['totals']['ready']
    assert assessment['reportIntegrity']==report['integrity']
    output=args.output/(variant+'.promoted.json')
    command=[args.native,'export-corpus-migration',*base,'--output',str(output)]
    exported=subprocess.run(command,capture_output=True,text=True)
    assert (exported.returncode==0)==(variant=='complete'),exported.stderr
    assert output.exists()==(variant=='complete')
    checks=[]
    if variant=='complete':
        frozen=output.read_bytes()
        corpus=json.loads(frozen)
        assert len(corpus['cases'])==19
        for index,(row,old) in enumerate(zip(corpus['cases'],original_value['cases'])):
            assert row['id']==old['id'] and row['label']==old['label']
            expected=report['cases'][index]['proposal']['candidate'] if report['cases'][index]['proposal'] else old['case']
            assert row['case']==expected
            case_file=args.output/('replay-'+str(index)+'.json')
            case_file.write_text(json.dumps(row['case'],ensure_ascii=False))
            replay=subprocess.run([args.native,'replay',str(case_file)],capture_output=True,text=True,check=True)
            assert json.loads(replay.stdout)['verified']
            case_file.unlink()
            checks.append({'id':row['id'],'verified':True,'metadataPreserved':True})
        refused=subprocess.run(command,capture_output=True,text=True)
        assert refused.returncode!=0 and output.read_bytes()==frozen
        (args.output/'export-receipt.json').write_text(exported.stdout)
        # Relabeling an otherwise identical corpus cannot reuse the acceptance.
        changed=copy.deepcopy(original_value)
        changed['cases'][0]['label']='Changed label requires new review'
        altered=args.output/'relabeled-corpus.json'
        altered.write_text(json.dumps(changed,ensure_ascii=False))
        forbidden=args.output/'stale-must-not-exist.json'
        stale=subprocess.run([args.native,'export-corpus-migration',str(altered),*base[1:],'--output',str(forbidden)],capture_output=True,text=True)
        assert stale.returncode!=0
        assert json.loads(stale.stdout)['diagnostic']['code']=='migration_decisions_stale'
        assert not forbidden.exists()
        altered.unlink()
    assert (folder/'corpus.json').read_bytes()==original
    for name in ['corpus.json','report.json']:
        (args.output/(variant+'.'+name)).write_bytes((folder/name).read_bytes())
    results.append({'variant':variant,'assessment':assessment,'exported':variant=='complete','originalUnchanged':True,'replayedCases':checks})
(args.output/'assessments.json').write_text(json.dumps({'results':results,'existingExportUnchanged':True,'relabeledCorpusAcceptanceRefused':True},indent=2)+'\n')
print(json.dumps({'corpora':2,'exportedSyntheticCorpusCases':19,'incompleteExportRefused':True,'relabeledAcceptanceRefused':True}))
