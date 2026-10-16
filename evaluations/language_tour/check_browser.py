"""Inspect the local nine-case, outcome-preserving refactor review offline."""
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
        assert choices.count() == 9
        for index in range(choices.count()):
            choice = choices.nth(index)
            choice.click()
            panel = page.locator('[data-case-panel]:visible')
            assert panel.count() == 1
            assert panel.get_attribute('id') == choice.get_attribute('data-target')
        search = page.locator('[data-case-search]')
        search.fill('no-such-case')
        assert page.locator('[data-case-choice]:visible').count() == 0
        assert page.locator('[data-no-matches]').is_visible()
        assert page.locator('[data-case-panel]:visible').count() == 0
        search.fill('original-four-lines')
        assert page.locator('[data-case-choice]:visible').count() == 1
        page.locator('[data-case-choice]:visible').click()
        assert page.locator('[data-case-panel]:visible').count() == 1
        search.scroll_into_view_if_needed()
        page.screenshot(path=str(output / f'refactor-{width}.png'))
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        checks.append({'width': width, 'allNineCasesSelected': True,
                       'pathFilterAndSearch': True, 'noHorizontalOverflow': True})
    assert not errors, errors
    assert all(url.startswith('file:') for url in requests), requests
    report = {'ok': True, 'browser': browser.version, 'checks': checks,
              'scriptErrors': errors, 'externalRequests': []}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    browser.close()
