"""Check kind decisions and operand navigation in a local offline review."""
import argparse
import json
import re
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
        page.goto((checkpoint / 'delivery-review.html').as_uri())
        choices = page.locator('[data-case]:visible')
        assert choices.count() == 3
        for index in range(3):
            choices.nth(index).click()
            panel = page.locator('[data-case-panel]:visible')
            decisions = panel.locator('.event').filter(
                has=page.locator('summary > strong').filter(has_text=re.compile('^kind branch$')))
            assert decisions.count() == 6
            assert all(decisions.nth(i).is_visible() for i in range(6))
            assert decisions.locator('summary').filter(has_text='branch selected').count() == 2
        choices.first.click()
        panel = page.locator('[data-case-panel]:visible')
        decision = panel.locator('.event').filter(
            has=page.locator('summary > strong').filter(has_text=re.compile('^kind branch$'))).first
        decision.locator('summary').first.click()
        link = decision.locator('[data-operand]').first
        target = link.get_attribute('href')
        link.click()
        assert page.locator(target).is_visible()
        decision.scroll_into_view_if_needed()
        page.screenshot(path=str(output / f'kind-decisions-{width}.png'))
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        checks.append({'width': width, 'allThreeCasesSelected': True,
                       'defaultKindDecisionsVisible': True, 'operandNavigation': True,
                       'noHorizontalOverflow': True})
    assert not errors, errors
    assert all(url.startswith('file:') for url in requests), requests
    report = {'ok': True, 'browser': browser.version, 'checks': checks,
              'scriptErrors': errors, 'externalRequests': []}
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    browser.close()
