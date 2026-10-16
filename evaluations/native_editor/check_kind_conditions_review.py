"""Inspect kind-condition policy evidence in an offline browser review."""
import argparse
import json
import re
from pathlib import Path
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("checkpoint", type=Path)
args = parser.parse_args()
root = args.checkpoint.resolve()
output = root / "browser"
output.mkdir(exist_ok=False)
errors, requests, checks = [], [], []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(args=["--no-sandbox"])
    page = browser.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("request", lambda r: requests.append(r.url))
    for width in [1440, 390]:
        page.set_viewport_size({"width": width, "height": 1000})
        page.goto((root / "kind-review.html").as_uri())
        choices = page.locator("[data-case]:visible")
        assert choices.count() == 8
        for index in range(8):
            choices.nth(index).click()
            panel = page.locator("[data-case-panel]:visible")
            branches = panel.locator(".event").filter(
                has=page.locator("summary > strong").filter(has_text=re.compile("^branch$")))
            assert branches.count() >= 2
            assert all(branches.nth(i).is_visible() for i in range(branches.count()))
        page.locator("[data-case]:visible").filter(has_text="missing").click()
        panel = page.locator("[data-case-panel]:visible")
        assert panel.locator(".event summary > strong").filter(has_text="read facts.contact.kind").count() == 0
        assert panel.locator(".event summary > strong").filter(has_text="read facts.contact.address").count() == 0
        page.locator("[data-filter]").select_option("outcome_changed")
        assert page.locator("[data-case]:visible").count() == 3
        page.locator("[data-case]:visible").filter(has_text="sms-consent").click()
        panel = page.locator("[data-case-panel]:visible")
        branch = panel.locator(".event").filter(
            has=page.locator("summary > strong").filter(has_text=re.compile("^branch$"))).filter(
                has_text='facts.contact.kind == "sms" and facts.contact.opted_in').first
        branch.locator("summary").click()
        link = branch.locator("[data-operand]").first
        target = link.get_attribute("href")
        link.click()
        compound = page.locator(target)
        assert compound.is_visible()
        assert compound.locator("summary > strong").inner_text() == "and"
        presence = compound.locator("[data-operand]").first
        target = presence.get_attribute("href")
        presence.click()
        assert page.locator(target).is_visible()
        assert page.locator(target).locator("summary > strong").inner_text() == "=="
        branch.scroll_into_view_if_needed()
        page.screenshot(path=str(output / f"kind-condition-decisions-{width}.png"))
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        checks.append({"width": width, "eightCasesSelected": True, "defaultBranchesVisible": True,
                       "noFabricatedAbsentPayloadReads": True, "threeConsentChanges": True,
                       "kindOperandNavigation": True, "noHorizontalOverflow": True})
    assert not errors, errors
    assert all(url.startswith("file:") for url in requests), requests
    report = {"ok": True, "browser": browser.version, "checks": checks, "scriptErrors": errors, "externalRequests": []}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    browser.close()
