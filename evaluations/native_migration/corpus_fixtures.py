"""Build mixed-engine corpus migration reviews using explicitly selected real executables."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess

parser=argparse.ArgumentParser()
parser.add_argument('cases',type=Path)
parser.add_argument('output',type=Path)
parser.add_argument('--previous-engine',required=True)
parser.add_argument('--changed-engine',required=True)
parser.add_argument('--native',default='target/debug/gwt-native')
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)
def digest(domain,value):
    encoded=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()
    return 'sha256:'+hashlib.sha256(domain.encode()+b'\0'+encoded).hexdigest()
entries=[]
engines=[]
for variant,exe in [('preserved',args.previous_engine),('changed-message',args.changed_engine)]:
    cases=sorted((args.cases/variant).glob('*.original.json'))
    assert len(cases)==9
    for path in cases:
        case=json.loads(path.read_text())
        entries.append({'id':variant+'-'+path.name.removesuffix('.original.json'),'label':'Qualification case: '+path.name.removesuffix('.original.json'),'case':case})
    engines.append({'sourceDigest':entries[-1]['case']['record']['engine']['sourceDigest'],'executable':str(Path(exe).resolve())})
# Retain a freshly migrated case as a current-engine corpus entry.
raw=subprocess.run([args.native,'migrate',str(args.cases/'preserved/exact-prints.original.json'),'--previous-engine',args.previous_engine],capture_output=True,text=True,check=True)
current=json.loads(raw.stdout)['candidate']
entries.append({'id':'already-current','label':'Already verified on this engine </script><img src=x onerror=alert(1)>','case':current})
assert len(entries)==19
results=[]
for variant in ['complete','incomplete']:
    folder=args.output/variant
    folder.mkdir()
    rows=copy.deepcopy(entries)
    selected=copy.deepcopy(engines)
    if variant=='incomplete':
        selected.pop() # Deliberately absent second previous engine; all nine cases must remain visible.
        rows.append({'id':'corrupt-case','label':'Intentionally invalid case fixture','case':{}})
        forged=copy.deepcopy(current)
        forged['record']['observed']['steps']+=1
        del forged['integrity']
        forged['integrity']=digest('gwt-native-case-sha256-v1',forged)
        rows.append({'id':'forged-current','label':'Recomputed checksum must not bypass replay','case':forged})
    corpus={'kind':'gwt.native-corpus','schemaVersion':1,'cases':rows}
    (folder/'corpus.json').write_text(json.dumps(corpus,ensure_ascii=False)+'\n')
    original=(folder/'corpus.json').read_bytes()
    (folder/'engines.json').write_text(json.dumps({'kind':'gwt.native-migration-engines','schemaVersion':1,'engines':selected})+'\n')
    run=subprocess.run([args.native,'migrate-corpus',str(folder/'corpus.json'),'--engines',str(folder/'engines.json'),'--html',str(folder/'review.html'),'--decisions-template',str(folder/'decisions.json')],capture_output=True,text=True)
    assert (run.returncode==0)==(variant=='complete'),run.stderr
    report=json.loads(run.stdout)
    assert report['originalCorpusIntegrity']==digest('gwt-native-corpus-sha256-v1',corpus)
    unhashed=copy.deepcopy(report)
    identity=unhashed.pop('integrity')
    assert identity==digest('gwt-native-corpus-migration-sha256-v1',unhashed)
    assert report['totals']==({'total':19,'ready':19,'retainedCurrent':1,'observationPreserved':15,'observationChanged':3,'unavailable':0} if variant=='complete' else {'total':21,'ready':10,'retainedCurrent':1,'observationPreserved':9,'observationChanged':0,'unavailable':11})
    assert [(r['id'],r['label']) for r in report['cases']]==[(r['id'],r['label']) for r in rows]
    for row,old in zip(report['cases'],rows):
        if row['proposal']:
            proposal=row['proposal']
            assert proposal['original']==old['case']
            assert proposal['candidate']['record']['source']==old['case']['record']['source']
            assert proposal['candidate']['record']['migration']['parentCaseIntegrity']==old['case']['integrity']
        if row['id']=='already-current':
            assert row['retainedCase']==current
            assert row['currentReplay']['verified']
    assert (folder/'corpus.json').read_bytes()==original
    (folder/'report.json').write_text(run.stdout)
    results.append({'variant':variant,'totals':report['totals'],'reportIntegrity':report['integrity'],'independentHashesVerified':True,'originalUnchanged':True})
(args.output/'generation.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results))
