"""Inspect the MiniLang refactor and native boundary reviews offline."""
import argparse
import json
from pathlib import Path
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
    page = browser.new_page()
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: requests.append(request.url))
    for width in [1440, 390]:
        page.set_viewport_size({'width': width, 'height': 1000})
        page.goto((checkpoint / 'refactor-review.html').as_uri())
        page.locator('[data-filter="path_changed"]').click()
        choices = page.locator('[data-case-choice]:visible')
        assert choices.count() == 4
        for index in range(4):
            choices.nth(index).click()
            panel = page.locator('[data-case-panel]:visible')
            assert panel.count() == 1
            assert panel.get_attribute('id') == choices.nth(index).get_attribute('data-target')
        search = page.locator('[data-case-search]')
        search.fill('equal-threshold')
        assert page.locator('[data-case-choice]:visible').count() == 1
        search.scroll_into_view_if_needed()
        page.screenshot(path=str(output / f'refactor-{width}.png'))
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.goto((checkpoint / 'boundary-review.html').as_uri())
        choices = page.locator('[data-case]:visible')
        assert choices.count() == 5
        for index in range(5):
            choices.nth(index).click()
            assert page.locator('[data-case-panel]:visible').count() == 1
        page.locator('[data-filter]').select_option('outcome_changed')
        assert page.locator('[data-case]:visible').count() == 1
        assert 'equal-threshold' in page.locator('[data-case]:visible').inner_text()
        panel = page.locator('[data-case-panel]:visible')
        assert 'kind branch' in panel.inner_text()
        page.locator('[data-filter]').scroll_into_view_if_needed()
        page.screenshot(path=str(output / f'boundary-{width}.png'))
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        checks.append({'width': width, 'fourRefactorPathsSelected': True,
                       'refactorSearch': True, 'fiveNativeCasesSelected': True,
                       'nativeBoundaryFilter': True, 'noHorizontalOverflow': True})
    assert not errors, errors
    assert all(url.startswith('file:') for url in requests), requests
    report = {'ok': True, 'browser': browser.version, 'checks': checks,
              'scriptErrors': errors, 'externalRequests': []}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    browser.close()
