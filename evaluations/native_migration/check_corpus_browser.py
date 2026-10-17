"""Offline corpus review interactions; all saved reviewers and choices are synthetic."""
import argparse
import copy
import json
from pathlib import Path
from playwright.sync_api import sync_playwright
parser=argparse.ArgumentParser()
parser.add_argument('fixtures',type=Path)
parser.add_argument('output',type=Path)
args=parser.parse_args()
args.output.mkdir(parents=True,exist_ok=True)
errors,requests,results=[],[],[]
with sync_playwright() as p:
    browser=p.chromium.launch(args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1100},accept_downloads=True)
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.on('request',lambda request:requests.append(request.url))
    for variant in ['complete','incomplete']:
        folder=args.fixtures/variant
        report=json.loads((folder/'report.json').read_text())
        page.goto((folder/'review.html').resolve().as_uri())
        rows=page.locator('.case')
        assert rows.count()==report['totals']['total']
        assert page.locator('.metrics strong').all_text_contents()==[str(report['totals'][key]) for key in ['total','ready','unavailable']]
        assert rows.locator(':scope > h2').all_text_contents()==[row['id'] for row in report['cases']]
        assert page.locator('img').count()==0
        with page.expect_download() as event:
            page.locator('[data-download]').click()
        downloaded=args.output/(variant+'.download.json')
        event.value.save_as(downloaded)
        assert json.loads(downloaded.read_text())==report
        assert '9007199254740993' in downloaded.read_text()
        downloaded.unlink()
        page.locator('[data-filter]').select_option('changed')
        assert page.locator('.case:visible').count()==report['totals']['observationChanged']
        page.locator('[data-filter]').select_option('unavailable')
        assert page.locator('.case:visible').count()==report['totals']['unavailable']
        page.locator('[data-filter]').select_option('all')
        page.locator('[data-search]').fill('not-a-case-zz')
        assert page.locator('[data-empty]').is_visible()
        assert page.locator('.case:visible').count()==0
        page.locator('[data-search]').fill('already-current')
        assert page.locator('.case:visible').count()==1
        current=page.locator('.case:visible')
        current.locator('[data-evidence] > summary').click()
        assert '9007199254740993' in current.inner_text()
        page.locator('[data-search]').fill('')
        # Every operand target is unique and remains in its originating corpus entry.
        ids=page.locator('[id]').evaluate_all('els=>els.map(el=>el.id)')
        assert len(ids)==len(set(ids))
        assert page.locator('[data-operand]').evaluate_all("els=>els.every(el=>document.getElementById(el.hash.slice(1))?.closest('.case')===el.closest('.case'))")
        page.locator('[data-search]').fill('preserved-exact-prints')
        row=page.locator('.case:visible')
        row.locator('[data-evidence] > summary').click()
        link=row.locator('[data-operand]').first
        link.evaluate("el=>{for(let n=el;n;n=n.parentElement)if(n.tagName==='DETAILS')n.open=true;}")
        target=link.get_attribute('href')
        link.click()
        assert page.locator(target+' .source').is_visible()
        page.locator('[data-search]').fill('')
        # Non-pending notes and a named reviewer are required, including acceptance.
        rows.first.locator('[data-status]').select_option('accept')
        page.locator('[data-save]').click()
        assert 'require a reviewer and a note' in page.locator('[data-message]').inner_text()
        page.locator('[data-reviewer]').fill('Synthetic corpus migration qualification reviewer')
        for index,row in enumerate(report['cases']):
            ready=rows.nth(index).get_attribute('data-ready')=='true'
            assert rows.nth(index).locator('[value=accept]').evaluate('el=>el.disabled')==(not ready)
            rows.nth(index).locator('[data-status]').select_option('accept' if ready else 'needs_information')
            rows.nth(index).locator('[data-note]').fill('Qualification fixture only. <img src=x onerror=alert(1)>')
        with page.expect_download() as event:
            page.locator('[data-save]').click()
        choice=args.output/(variant+'.decisions.json')
        event.value.save_as(choice)
        saved=json.loads(choice.read_text())
        assert saved['reportIntegrity']==report['integrity']
        assert len(saved['decisions'])==report['totals']['total']
        page.locator('[data-reviewer]').fill('unsaved')
        page.locator('[data-load]').set_input_files(choice)
        page.wait_for_function("()=>document.querySelector('[data-message]').textContent.includes('restored')")
        assert page.locator('[data-reviewer]').input_value()==saved['reviewer']
        invalids=[(json.dumps({**saved,'reportIntegrity':'sha256:'+'0'*64}),'different corpus'),(json.dumps({**saved,'decisions':saved['decisions'][:-1]}),'every case'),(json.dumps(saved)[:-1]+',"rev\\u0069ewer":"duplicate"}','duplicate JSON key'),(' '*2097153,'two MiB')]
        if variant=='incomplete':
            bad=copy.deepcopy(saved)
            next(item for item in bad['decisions'] if item['status']=='needs_information')['status']='accept'
            invalids.append((json.dumps(bad),'unavailable case'))
        for content,expected in invalids:
            page.locator('[data-load]').set_input_files({'name':'bad.json','mimeType':'application/json','buffer':content.encode()})
            page.wait_for_function('(text)=>document.querySelector("[data-message]").textContent.includes(text)',arg=expected)
            assert page.locator('[data-reviewer]').input_value()==saved['reviewer']
            assert rows.locator('[data-status]').evaluate_all('els=>els.map(el=>el.value)')==[d['status'] for d in saved['decisions']]
            assert rows.locator('[data-note]').evaluate_all('els=>els.map(el=>el.value)')==[d['note'] for d in saved['decisions']]
        page.locator('[data-load]').set_input_files(choice)
        page.wait_for_function("()=>document.querySelector('[data-message]').textContent.includes('restored')")
        page.locator('[data-filter]').select_option('pending')
        assert page.locator('.case:visible').count()==0
        page.locator('[data-filter]').select_option('changed' if variant=='complete' else 'unavailable')
        page.screenshot(path=str(args.output/(variant+'-desktop.png')),full_page=False)
        page.locator('[data-filter]').select_option('all')
        page.locator('[data-search]').fill('changed-message-expected-rejection' if variant=='complete' else 'corrupt-case')
        focused=page.locator('.case:visible')
        focused.locator('[data-evidence]').evaluate('el=>el.open=true')
        focused.screenshot(path=str(args.output/(variant+'-evidence.png')))
        page.locator('[data-search]').fill('')
        page.locator('[data-filter]').select_option('changed' if variant=='complete' else 'unavailable')
        page.locator('[data-reviewer]').scroll_into_view_if_needed()
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(args.output/(variant+'-mobile.png')),full_page=False)
        page.set_viewport_size({'width':1440,'height':1100})
        results.append({'variant':variant,'cases':rows.count(),'exactReportDownload':True,'metadataPreserved':True,'filters':True,'operandTargetsUniqueAndLocal':True,'decisionRoundTrip':True,'invalidLoadPreservesForm':True,'unavailableAcceptanceDisabled':True,'mobileFits':True})
    plain=browser.new_context(java_script_enabled=False).new_page()
    plain.goto((args.fixtures/'incomplete'/'review.html').resolve().as_uri())
    assert plain.locator('.case').count()==21
    assert plain.locator('[data-operand]').count()>0
    assert 'no explicitly selected executable' in plain.locator('body').text_content()
    browser.close()
assert not errors,errors
assert all(url.startswith('file:') for url in requests),requests
(args.output/'browser.json').write_text(json.dumps({'results':results,'pageErrors':errors,'externalRequests':[],'noJavaScriptReadable':True},indent=2)+'\n')
print(json.dumps({'corpora':len(results),'cases':sum(row['cases'] for row in results),'pageErrors':errors}))
