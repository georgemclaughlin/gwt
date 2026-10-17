"""Optional Chromium interaction check of native-generated offline review pages."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from playwright.sync_api import sync_playwright

parser=argparse.ArgumentParser()
parser.add_argument('fixtures',type=Path)
parser.add_argument('output',type=Path)
parser.add_argument('--workflows', nargs='+', default=['damage-precedence', 'member-window', 'clearance-exclusion', 'faults', 'stock-reservation'])
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)
errors=[]
requests=[]
results=[]
exact_integer_download=False
with sync_playwright() as p:
    browser=p.chromium.launch(args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1100},accept_downloads=True)
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.on('request',lambda request:requests.append(request.url))
    for document in sorted(args.fixtures.resolve().glob('*/review.html')):
        expected=json.loads(document.with_suffix('.json').read_text())
        page.goto(document.as_uri())
        choices=page.locator('[data-case]')
        assert choices.count()==expected['totals']['total']
        assert page.locator('[data-case-panel]').count()==1
        page.locator('[data-filter]').select_option('outcome_changed')
        assert page.locator('[data-case]:visible').count()==expected['totals']['outcomeChanged']
        page.locator('[data-search]').fill('no-such-case-zzzz')
        assert page.locator('[data-case]:visible').count()==0
        assert page.locator('[data-empty]').is_visible()
        assert page.locator('[data-case-panel]').count()==0
        page.locator('[data-search]').fill('')
        page.locator('[data-filter]').select_option('all')
        for index in range(choices.count()):
            choices.nth(index).click()
            assert page.locator('[data-case-panel] h2').inner_text()==expected['cases'][index]['id']
            assert page.locator('[data-case][aria-pressed=true]').count()==1
        page.locator('[data-filter]').select_option('unverified')
        assert page.locator('[data-case]:visible').count()==expected['totals']['baselineMismatch']+expected['totals']['unavailable']
        page.locator('[data-filter]').select_option('candidate_failed')
        assert page.locator('[data-case]:visible').count()==expected['totals']['candidateFailed']
        page.locator('[data-filter]').select_option('all')
        choices.first.click()
        if document.parent.name=='faults':
            page.locator('[data-search]').fill('huge')
            assert page.locator('[data-case]:visible').count()==1
            assert page.evaluate('globalThis.injected') is None
            assert page.locator('img').count()==0
            page.locator('[data-case-panel] > details').first.locator('summary').click()
            assert '9007199254740993' in page.locator('[data-case-panel]').inner_text()
            with page.expect_download() as event:
                page.locator('[data-download]').click()
            downloaded=args.output/'downloaded-review.json'
            event.value.save_as(downloaded)
            actual=json.loads(downloaded.read_text())
            assert actual==expected
            huge=next(row for row in actual['cases'] if row['id']=='huge')
            assert huge['input']['invoice']['quantity']==9007199254740993
            exact_integer_download=True
            downloaded.unlink()
            page.locator('[data-search]').fill('')
        elif document.parent.name == 'scenarios':
            page.locator('[data-search]').fill('printed exact integer')
            assert page.locator('[data-case]:visible').count() == 1
            page.locator('[data-case]:visible').click()
            panel = page.locator('[data-case-panel]')
            assert 'Scenario: printed exact integer' in panel.inner_text()
            assert 'Scenario result' in panel.inner_text()
            assert "including its setup and assertions" in panel.inner_text()
            assert 'Supplied input' not in panel.inner_text()
            for details in panel.locator('details').filter(has=page.locator('summary', has_text='State and captured output')).all():
                details.locator(':scope > summary').click()
            assert '9007199254740993' in panel.inner_text()
            assert '9007199254740994' in panel.inner_text()
            with page.expect_download() as downloaded:
                page.locator('[data-download]').click()
            path = args.output / 'downloaded-review.json'
            downloaded.value.save_as(path)
            assert json.loads(path.read_text()) == expected
            exact_integer_download=True
            path.unlink()
            page.locator('[data-search]').fill('')
        else:
            page.locator('[data-filter]').select_option('outcome_changed')
            page.locator('[data-case]:visible').first.click()
            # Follow an operand from a recorded write to its expression result.
            operation = {'stock-reservation': 'subtract', 'returns': 'return', 'arguments': 'argument value', 'prints': 'assert prints', 'failures': 'assert failure'}.get(document.parent.name, 'set')
            event=page.locator('[data-case-panel] .event').filter(has=page.locator('summary strong',has_text=re.compile('^' + operation + '$'))).first
            assert event.is_visible()
            if document.parent.name == 'returns':
                assert 'Value satisfied its return contract' in event.inner_text()
            if document.parent.name == 'arguments':
                assert 'copied it into local state' in event.inner_text()
            if document.parent.name == 'prints':
                assert 'Captured output matched the expected sequence' in event.inner_text()
            if document.parent.name == 'failures':
                assert 'Action failed with the expected code; the scenario can continue.' in event.inner_text()
            event.locator(':scope > details > summary').click()
            if document.parent.name == 'failures':
                assert 'Observed action failure' in event.inner_text()
                assert 'REQUIRE stock.available >= order.quantity' in event.inner_text()
                assert 'Action did not fail with the expected code.' in page.locator('[data-case-panel]').inner_text()
            link=event.locator('[data-operand]').first
            target=link.get_attribute('href')
            link.click()
            assert page.locator('[data-all-events]').is_checked()
            assert page.locator(target).is_visible()
            assert page.locator(target+'>details').get_attribute('open') is not None
            page.locator('[data-all-events]').uncheck()
            if document.parent.name == 'returns':
                event.evaluate('(element) => element.scrollIntoView({block: "start"})')
                page.screenshot(path=str(args.output/'returns-evidence.png'))
            if document.parent.name == 'arguments':
                event.evaluate('(element) => element.scrollIntoView({block: "start"})')
                page.screenshot(path=str(args.output/'arguments-evidence.png'))
            if document.parent.name == 'failures':
                event.evaluate('(element) => element.scrollIntoView({block: "start"})')
                page.screenshot(path=str(args.output/'failures-evidence.png'))
            if document.parent.name == 'prints':
                event.evaluate('(element) => element.scrollIntoView({block: "start"})')
                page.screenshot(path=str(args.output/'prints-evidence.png'))
                assert '9007199254740993' in event.inner_text()
                assert 'Captured output differed from the expected sequence' in page.locator('[data-case-panel]').inner_text()
                with page.expect_download() as downloaded:
                    page.locator('[data-download]').click()
                path = args.output / 'downloaded-review.json'
                downloaded.value.save_as(path)
                assert json.loads(path.read_text()) == expected
                exact_integer_download=True
                path.unlink()
            if document.parent.name == 'stock-reservation':
                for operation in ['collection item', 'collection selection', 'sum item', 'subtract']:
                    event = page.locator('[data-case-panel] .event').filter(
                        has=page.locator('summary strong', has_text=re.compile('^' + operation + '$'))).first
                    assert event.is_visible(), operation
                subtotal = page.locator('[data-case-panel] .event').filter(
                    has=page.locator('summary strong', has_text=re.compile('^sum item$'))).first
                subtotal.locator(':scope > details > summary').click()
                assert 'subtotal' in subtotal.inner_text()
                subtotal.evaluate('(element) => element.scrollIntoView({block: "start"})')
                page.screenshot(path=str(args.output/'reservation-evidence.png'))
        # Explicit synthetic decisions: test storage/validation, never approval of this project.
        selected_id=page.locator('[data-case-panel] h2').inner_text()
        page.locator('[data-reviewer]').fill('Synthetic browser test reviewer')
        page.locator('[data-decision]').select_option('reject')
        page.locator('[data-download-decisions]').click()
        assert 'requires a note' in page.locator('[data-decision-message]').inner_text()
        note='Synthetic test note: verify boundary. <img src=x onerror="globalThis.injected=true">'
        page.locator('[data-decision-note]').fill(note)
        with page.expect_download() as saved:
            page.locator('[data-download-decisions]').click()
        decision_path=args.output/('decisions-'+document.parent.name+'.json')
        saved.value.save_as(decision_path)
        decisions=json.loads(decision_path.read_text())
        digest=hashlib.sha256(b'gwt-native-review-sha256-v1\0'+json.dumps(expected,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        assert decisions['reportIdentity']['digest']=='sha256:'+digest
        assert len(decisions['decisions'])==expected['totals']['total']
        assert next(item for item in decisions['decisions'] if item['id']==selected_id)['note']==note
        page.reload()
        assert page.locator('[data-reviewer]').input_value()==''
        page.locator('[data-load-decisions]').set_input_files(decision_path)
        page.locator('[data-decision-message]').filter(has_text='restored').wait_for()
        assert page.locator('[data-reviewer]').input_value()=='Synthetic browser test reviewer'
        page.locator('[data-filter]').select_option('decision_reject')
        assert page.locator('[data-case]:visible').count()==1
        assert page.locator('[data-case-panel] h2').inner_text()==selected_id
        assert page.locator('[data-decision-note]').input_value()==note
        assert page.locator('img').count()==0
        assert page.evaluate('globalThis.injected') is None
        # Rejected imports must leave all existing decisions intact.
        for corruption in ['stale', 'missing', 'status', 'duplicate_key']:
            corrupt=json.loads(json.dumps(decisions))
            if corruption=='stale': corrupt['reportIdentity']['digest']='sha256:'+'0'*64
            if corruption=='missing': corrupt['decisions'].pop()
            if corruption=='status': corrupt['decisions'][0]['status']=['accept']
            bad_path=args.output/'invalid-decisions.json'
            encoded=json.dumps(corrupt)
            if corruption=='duplicate_key': encoded=encoded.replace('{', '{\"kind\":\"gwt.native-review-decisions\",', 1)
            bad_path.write_text(encoded)
            page.locator('[data-load-decisions]').set_input_files(bad_path)
            page.locator('[data-decision-message].error').wait_for()
            assert page.locator('[data-decision-note]').input_value()==note
            bad_path.unlink()
        if document.parent.name=='faults':
            corrupt=json.loads(json.dumps(decisions))
            next(item for item in corrupt['decisions'] if item['id']=='invalid')['status']='accept'
            bad_path=args.output/'invalid-decisions.json'
            bad_path.write_text(json.dumps(corrupt))
            page.locator('[data-load-decisions]').set_input_files(bad_path)
            page.locator('[data-decision-message]').filter(has_text='Unverified cases').wait_for()
            assert page.locator('[data-decision-note]').input_value()==note
            bad_path.unlink()
            page.locator('[data-filter]').select_option('unverified')
            page.locator('[data-case]:visible').first.click()
            assert page.locator('[data-decision] option[value=accept]').get_attribute('disabled') is not None
        page.locator('[data-filter]').select_option('decision_reject')
        page.locator('[data-case]:visible').first.click()
        overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth')
        assert not overflow
        if document.parent.name=='damage-precedence':
            page.locator('[data-case-panel]').evaluate('(element) => element.scrollIntoView({block: "start"})')
            page.screenshot(path=str(args.output/'desktop.png'))
        if document.parent.name=='stock-reservation':
            page.locator('[data-case-panel]').evaluate('(element) => element.scrollIntoView({block: "start"})')
            page.screenshot(path=str(args.output/'reservation-desktop.png'))
        if document.parent.name=='scenarios':
            page.locator('[data-case-panel]').evaluate('(element) => element.scrollIntoView({block: "start"})')
            page.screenshot(path=str(args.output/'scenario-desktop.png'))
        if document.parent.name=='returns':
            page.locator('[data-case-panel]').evaluate('(element) => element.scrollIntoView({block: "start"})')
            page.screenshot(path=str(args.output/'returns-desktop.png'))
        if document.parent.name=='arguments':
            page.locator('[data-case-panel]').evaluate('(element) => element.scrollIntoView({block: "start"})')
            page.screenshot(path=str(args.output/'arguments-desktop.png'))
        page.set_viewport_size({'width':390,'height':844})
        page.locator('[data-case-panel]').evaluate('(element) => element.scrollIntoView({block: "start"})')
        assert not page.evaluate('document.documentElement.scrollWidth > innerWidth')
        if document.parent.name=='damage-precedence':
            page.screenshot(path=str(args.output/'mobile.png'))
        if document.parent.name=='stock-reservation':
            page.screenshot(path=str(args.output/'reservation-mobile.png'))
        if document.parent.name=='scenarios':
            page.screenshot(path=str(args.output/'scenario-mobile.png'))
        if document.parent.name=='returns':
            page.screenshot(path=str(args.output/'returns-mobile.png'))
        if document.parent.name=='arguments':
            page.screenshot(path=str(args.output/'arguments-mobile.png'))
        if document.parent.name=='prints':
            page.screenshot(path=str(args.output/'prints-mobile.png'))
        if document.parent.name=='failures':
            page.screenshot(path=str(args.output/'failures-mobile.png'))
        results.append({'workflow':document.parent.name,'cases':choices.count(),'allCasesSelectable':True,'filters':True,'operandLinks':document.parent.name not in {'faults', 'scenarios'},'horizontalOverflowAt390':False,'decisionRoundTrip':True,'staleDecisionsRefused':True})
        page.set_viewport_size({'width':1440,'height':1100})
    browser.close()
assert results and {result['workflow'] for result in results} == set(args.workflows)
assert not errors,errors
assert all(url.startswith('file:') for url in requests),requests
report={'results':results,'javascriptErrors':errors,'externalRequests':[],'exactIntegerDownload':exact_integer_download,'htmlInjectionExecuted':False}
(args.output/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
