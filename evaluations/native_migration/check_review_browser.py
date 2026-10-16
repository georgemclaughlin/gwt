"""Offline Chromium qualification; saved choices belong to synthetic test reviewers."""
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument('fixtures', type=Path)
parser.add_argument('output', type=Path)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
errors, requests, results = [], [], []
with sync_playwright() as p:
    browser = p.chromium.launch(args=['--no-sandbox'])
    page = browser.new_page(viewport={'width': 1440, 'height': 1100}, accept_downloads=True)
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('request', lambda request: requests.append(request.url))
    for folder in sorted(args.fixtures.glob('*')):
        if not folder.is_dir():
            continue
        proposal = json.loads((folder / 'proposal.json').read_text())
        template = json.loads((folder / 'decision.json').read_text())
        page.goto((folder / 'review.html').resolve().as_uri())
        assert page.locator('h1').inner_text() == (proposal['original']['record'].get('request') or proposal['original']['record']['scenario'])
        metrics = page.locator('.metrics strong').all_text_contents()
        assert metrics == ['Changed' if proposal['changes'][key] else 'Same' for key in ['outcome', 'state', 'evidence']]
        # Download raw proposal JSON: Python checks exact integers and the entire object.
        with page.expect_download() as event:
            page.locator('[data-download]').click()
        download = args.output / (folder.name + '.proposal.json')
        event.value.save_as(download)
        assert json.loads(download.read_text()) == proposal
        download.unlink()
        if 'exact-prints' in folder.name:
            assert '9007199254740993' in page.locator('body').text_content()
        events = page.locator('.event-trail')
        for trail in events.all():
            trail.locator(':scope > summary').click()
        operand = page.locator('[data-operand]').first
        if operand.count():
            # Open source event; target event may remain collapsed until link navigation.
            operand.evaluate("el => { for(let n=el;n;n=n.parentElement) if(n.tagName==='DETAILS') n.open=true; }")
            target = operand.get_attribute('href')
            operand.click()
            assert page.locator(target + ' > details').get_attribute('open') is not None
            assert page.locator(target + ' .source').is_visible()
        for trail in events.all():
            trail.evaluate('el => el.open=false')
        page.locator('[data-status]').select_option('accept')
        page.locator('[data-save]').click()
        assert 'requires a reviewer and a note' in page.locator('[data-message]').inner_text()
        page.locator('[data-reviewer]').fill('Synthetic migration qualification reviewer')
        page.locator('[data-note]').fill('Qualification fixture only; no real corpus approval. <img src=x onerror=alert(1)>')
        status = 'accept' if folder.name == 'preserved-exact-prints' else 'reject' if folder.name == 'changed-message-raw-failure' else 'needs_information' if folder.name == 'changed-message-expected-rejection' else 'pending'
        page.locator('[data-status]').select_option(status)
        with page.expect_download() as event:
            page.locator('[data-save]').click()
        decision_path = args.output / (folder.name + '.decision.json')
        event.value.save_as(decision_path)
        decision = json.loads(decision_path.read_text())
        assert decision['proposalIntegrity'] == proposal['integrity']
        assert decision['status'] == status
        page.locator('[data-reviewer]').fill('unsaved')
        page.locator('[data-load]').set_input_files(decision_path)
        page.wait_for_function("() => document.querySelector('[data-message]').textContent.includes('restored')")
        assert page.locator('[data-reviewer]').input_value() == decision['reviewer']
        assert page.locator('[data-note]').input_value() == decision['note']
        assert page.locator('img').count() == 0
        for invalid, expected in [
            (json.dumps({**decision, 'proposalIntegrity': 'sha256:' + '0' * 64}), 'different proposal'),
            (json.dumps(decision)[:-1] + ',"st\\u0061tus":"accept"}', 'duplicate JSON key'),
            ('{}', 'schema version'),
            (' ' * 32769, '32 KiB'),
        ]:
            page.locator('[data-load]').set_input_files({'name': 'invalid.json', 'mimeType': 'application/json', 'buffer': invalid.encode()})
            page.wait_for_function('(text) => document.querySelector("[data-message]").textContent.includes(text)', arg=expected)
            assert page.locator('[data-reviewer]').input_value() == decision['reviewer']
            assert page.locator('[data-status]').input_value() == status
            assert page.locator('[data-note]').input_value() == decision['note']
        if folder.name in ['preserved-exact-prints', 'changed-message-raw-failure', 'changed-message-expected-rejection']:
            page.locator('[data-load]').set_input_files(decision_path)
            page.wait_for_function("() => document.querySelector('[data-message]').textContent.includes('restored')")
            page.screenshot(path=str(args.output / (folder.name + '-desktop.png')), full_page=True)
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'), folder.name
        if folder.name == 'changed-message-raw-failure':
            page.screenshot(path=str(args.output / (folder.name + '-mobile.png')), full_page=True)
        page.set_viewport_size({'width': 1440, 'height': 1100})
        results.append({'id': folder.name, 'status': status, 'proposalIntegrity': proposal['integrity'], 'exactProposalDownload': True, 'decisionRoundTrip': True, 'invalidDecisionPreservesForm': True, 'mobileFits': True, 'operandFollowed': bool(operand.count())})
    # Core recorded material remains available without running JavaScript.
    offline = browser.new_context(java_script_enabled=False)
    plain = offline.new_page()
    plain.goto((args.fixtures / 'changed-message-raw-failure' / 'review.html').resolve().as_uri())
    assert 'assertion was false (qualification engine)' in plain.locator('body').text_content()
    assert plain.locator('.execution').count() == 2
    assert plain.locator('[data-operand]').count() > 0
    browser.close()
assert len(results) == 18
assert not errors, errors
assert all(url.startswith('file:') for url in requests), requests
(args.output / 'browser.json').write_text(json.dumps({'cases': results, 'pageErrors': errors, 'externalRequests': [], 'noJavaScriptReadable': True}, indent=2) + '\n')
print(json.dumps({'cases': len(results), 'pageErrors': errors, 'externalRequests': []}))
