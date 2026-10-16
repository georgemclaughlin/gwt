"""Check table evidence in an existing offline receiving review artifact."""
import argparse
import json
from pathlib import Path
import re

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('checkpoint', type=Path)
args = parser.parse_args()
checkpoint = args.checkpoint.resolve()
output = checkpoint / 'browser'
output.mkdir(exist_ok=False)
errors, requests, checks = [], [], []
with sync_playwright() as p:
    browser = p.chromium.launch(args=['--no-sandbox'])
    page = browser.new_page(accept_downloads=True)
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: requests.append(request.url))
    for width in [1440, 390]:
        page.set_viewport_size({'width': width, 'height': 1000})
        page.goto((checkpoint / 'receiving-review.html').as_uri())
        assert page.locator('[data-case]').count() == 3
        page.locator('[data-filter]').select_option('outcome_changed')
        assert page.locator('[data-case]:visible').count() == 1
        page.locator('[data-case]:visible').click()
        assert not page.locator('[data-all-events]').is_checked()
        for operation in ['table row', 'initialize field']:
            event = page.locator('[data-case-panel] .event').filter(
                has=page.locator('summary strong', has_text=re.compile('^' + operation + '$'))).first
            assert event.is_visible(), operation
            event.locator(':scope > details > summary').click()
            if operation == 'table row':
                assert 'record contract' in event.inner_text()
                assert 'quantity' in event.inner_text()
                operand = event.locator('[data-operand]').first
                target = operand.get_attribute('href')
                operand.click()
                assert page.locator('[data-all-events]').is_checked()
                assert page.locator(target).is_visible()
                page.locator('[data-all-events]').uncheck()
            else:
                assert 'before' in event.inner_text()
                assert 'after' in event.inner_text()
            event.scroll_into_view_if_needed()
            page.screenshot(path=str(output / f'{operation.replace(" ", "-")}-{width}.png'))
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
        checks.append({'width': width, 'defaultTableEventsVisible': True,
                       'operandNavigation': True, 'noHorizontalOverflow': True})
    with page.expect_download() as downloaded:
        page.locator('[data-download]').click()
    path = output / 'downloaded-review.json'
    downloaded.value.save_as(path)
    assert json.loads(path.read_text()) == json.loads((checkpoint / 'receiving-review.json').read_text())
    path.unlink()
    assert not errors, errors
    assert not [url for url in requests if not url.startswith('file:')], requests
    result = {'browser': browser.version, 'checks': checks, 'exactDownload': True,
              'scriptErrors': errors, 'networkRequests': [], 'ok': True}
    (output / 'report.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    browser.close()
