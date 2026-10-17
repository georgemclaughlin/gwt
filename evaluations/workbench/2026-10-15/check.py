import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description="Check generated refund review pages in Chromium.")
parser.add_argument("trial", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
errors=[]; results=[]
with sync_playwright() as p:
    browser=p.chromium.launch(args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1000}, device_scale_factor=1)
    page.on('pageerror',lambda error: errors.append(str(error)))
    for document in sorted(args.trial.resolve().glob('*/review.html')):
        page.goto(document.as_uri()); page.wait_for_load_state('load')
        choices=page.locator('[data-case-choice]')
        count=choices.count()
        groups=page.locator('[data-impact-group]').count()
        page.locator('[data-filter="output_changed"]').click()
        changed=page.locator('[data-case-choice]:visible').count()
        assert changed > 0
        search=page.locator('[data-case-search]')
        search.fill('no-such-case')
        assert page.locator('[data-case-choice]:visible').count()==0
        assert page.locator('[data-no-matches]').is_visible()
        assert page.locator('[data-case-panel]:visible').count()==0
        search.fill('/decision/reason')
        assert page.locator('[data-case-choice]:visible').count()>0
        search.fill(''); page.locator('[data-filter="all"]').click()
        for i in range(count):
            choice=choices.nth(i)
            choice.evaluate('(el) => { for (let p=el.parentElement; p; p=p.parentElement) if (p.tagName === "DETAILS") p.open=true; }')
            choice.click()
            assert page.locator('[data-case-panel]:visible').count()==1
            assert page.locator('[data-case-panel]:visible').get_attribute('id') == choice.get_attribute('data-target')
        page.locator('[data-filter="path_changed"]').click()
        queue=page.locator('[data-path-queue]')
        if queue.count() and queue.is_visible():
            assert queue.get_attribute('open') is not None
        page.locator('[data-filter="all"]').click()
        choices.first.click()
        search.scroll_into_view_if_needed()
        page.screenshot(path=str(out/f'{document.parent.name}-desktop.png'))
        page.set_viewport_size({'width':390,'height':844})
        overflow=page.evaluate('document.documentElement.scrollWidth > innerWidth')
        if overflow:
            print('OVERFLOW',document.parent.name,page.evaluate('Array.from(document.querySelectorAll("body *")).filter(e=>e.getBoundingClientRect().right>innerWidth+1).map(e=>[e.tagName,e.className,e.getBoundingClientRect().right]).slice(0,15)'))
        search.scroll_into_view_if_needed();page.screenshot(path=str(out/f'{document.parent.name}-mobile.png'))
        results.append({'workflow':document.parent.name,'cases':count,'groups':groups,'outputChanged':changed,'horizontalOverflowAt390':overflow})
        page.set_viewport_size({'width':1440,'height':1000})
    assert len(results) == 3, 'expected all three refund review pages'
    browser.close()
report={'browser':'Chromium via Playwright 1.63.0','viewports':[{'width':1440,'height':1000},{'width':390,'height':844}],'results':results,'pageErrors':errors}
(out/'browser-report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
assert not errors
assert not any(r['horizontalOverflowAt390'] for r in results)
