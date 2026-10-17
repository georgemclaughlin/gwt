"""Qualify explicit rounding against decimal arithmetic and a policy revision."""
import argparse
from decimal import Decimal, localcontext, ROUND_HALF_EVEN, ROUND_HALF_UP
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native',type=Path,required=True)
    parser.add_argument('--previous-engine',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    native,previous,output=args.native.resolve(),args.previous_engine.resolve(),args.output.resolve()
    output.mkdir(parents=True,exist_ok=False)
    source=output/'rules.gwt';source.write_text(Path('examples/native_rounded_division/rules.gwt').read_text())
    candidate=output/'candidate.gwt';candidate.write_text(source.read_text().replace('half_even','half_away_from_zero'))
    commands=[]
    def run(engine,*args,expected_exit=0):
        command=[str(engine),*map(str,args)]
        r=subprocess.run(command,capture_output=True,text=True,timeout=30)
        commands.append({'command':command,'exitCode':r.returncode,'stderr':r.stderr})
        (output/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        assert r.returncode==expected_exit,r.stdout+r.stderr
        return json.loads(r.stdout)
    def save(name,data):
        path=output/name;path.write_text(json.dumps(data,indent=2)+'\n');return path
    def expected(total,units,mode):
        if units==0:return None
        with localcontext() as context:
            context.prec=1600
            value=(Decimal(total)/Decimal(units)).quantize(Decimal('0.01'),rounding=mode)
            return '0' if not value else format(value.normalize(),'f')
    cases=[];changes=0
    for total in ['-10.15','-10.05','-1.01','0','1','1.01','2','10.05','10.15']:
        for units in [0,1,2,3,4,7]:
            i=len(cases);input_value={'total':total,'units':units}
            input_path=save(f'input-{i}.json',input_value)
            case=run(native,'capture',source,'--request','quote unit price','--input',input_path)
            before=case['record']['observed'];value=expected(total,units,ROUND_HALF_EVEN)
            if value is None:assert not before['ok'] and before['diagnostic']['code']=='assertion_failed'
            else:assert before['ok'] and before['result']=={'price':value}
            path=save(f'case-{i}.json',case);assert run(native,'replay',path)['verified']
            after_case=run(native,'capture',candidate,'--request','quote unit price','--input',input_path)
            after=after_case['record']['observed'];other=expected(total,units,ROUND_HALF_UP)
            if other is None:assert not after['ok'] and after['diagnostic']['code']=='assertion_failed'
            else:assert after['ok'] and after['result']=={'price':other}
            changes+=value!=other;cases.append(path)
    corpus=save('corpus.json',run(native,'corpus',*cases))
    review=run(native,'review',corpus,'--candidate',candidate,'--html',output/'review.html')
    save('review.json',review)
    # Inspect the public totals rather than silently accepting a partially compared corpus.
    totals=review['totals']
    assert totals['compared']==len(cases),totals
    assert totals['outcomeChanged']==changes,totals
    assert totals['unavailable']==0 and totals['baselineMismatch']==0,totals
    # The new built-in reserves its verb; retain the actual old-engine failure to migrate.
    legacy=output/'legacy.gwt'
    legacy.write_text('WHEN divide <value> into <result>\n  GIVEN value is decimal\n  AND result is decimal\n  set result to value\nREQUEST copy\n  GIVEN value is decimal\n  GIVEN result is 0.0\n  WHEN divide value into result\n  OUTPUT result is decimal\n')
    inp=save('legacy-input.json',{'value':'1'})
    original=save('legacy-case.json',run(previous,'capture',legacy,'--request','copy','--input',inp))
    before=original.read_bytes()
    migration=run(native,'migrate',original,'--previous-engine',previous,expected_exit=1)
    assert migration['status']=='candidate_unavailable' and migration['candidateDiagnostic']['code']=='behavior_name'
    assert original.read_bytes()==before and not migration['approved']
    save('reserved-verb-migration.json',migration)
    renamed=output/'renamed.gwt';renamed.write_text(legacy.read_text().replace('divide','allocate'))
    renamed_case=run(previous,'capture',renamed,'--request','copy','--input',inp)
    assert renamed_case['record']['observed']['result']=={'result':'1'}
    renamed_path=save('renamed-original.json',renamed_case)
    rename_bytes=renamed_path.read_bytes()
    renamed_migration=run(native,'migrate',renamed_path,'--previous-engine',previous)
    assert renamed_migration['status']=='observation_preserved' and not renamed_migration['approved']
    assert renamed_path.read_bytes()==rename_bytes
    save('renamed-migration.json',renamed_migration)
    replay_path=save('renamed-candidate.json',renamed_migration['candidate'])
    assert run(native,'replay',replay_path)['verified']

    save('qualification.json',{'cases':len(cases),'independentOutcomeChanges':changes,'reviewTotals':totals,'reservedVerbMigration':migration['status'],'legacyCaseSha256':hashlib.sha256(before).hexdigest(),'reviewApproved':False,'renamedCaseMigration':'observation_preserved'})
    print(json.dumps({'ok':True,'cases':len(cases),'outcomeChanges':changes}))


if __name__=='__main__':main()
