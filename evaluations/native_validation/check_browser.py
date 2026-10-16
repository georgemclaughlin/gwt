"""Exercise generated validation views using a locally installed Chromium."""
import argparse
import hashlib
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("fixtures", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
checks, errors, requests = [], [], []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(args=["--no-sandbox"])
    context = browser.new_context(viewport={"width": 1280, "height": 960}, offline=True, accept_downloads=True)
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url))
    def open_report(name):
        page.goto((args.fixtures / name / "review.html").resolve().as_uri())
        page.locator("#outcome").wait_for()
        assert page.locator("#outcome").inner_text()
    open_report("mixed")
    assert page.locator("#outcome").inner_text() == "Validation did not pass"
    assert page.locator("#scenario-list button").count() == 6
    assert page.locator("#warnings li").count() == 3
    assert page.locator("#scenario-totals").inner_text() == "4 passed · 2 failed · 1 without recorded outcome"
    assert page.locator("img").count() == 0
    assert "9007199254740993" in page.locator("#scenario-detail").inner_text()
    page.screenshot(path=str(args.output / "desktop.png"), full_page=True)
    checks.append("gate statuses, exact expectation totals, evidence warnings, and escaped source/name markup")
    page.locator("#filter").select_option("failed")
    assert page.locator("#scenario-list button").count() == 2
    page.locator("#search").fill("nothing matches")
    assert page.locator("#scenario-list button").count() == 0
    assert "No scenarios match" in page.locator("#scenario-detail").inner_text()
    page.locator("#search").fill("")
    page.locator("#filter").select_option("gaps")
    assert page.locator("#scenario-list button").count() == 2
    page.locator("#scenario-list button").filter(has_text="action only").click()
    assert "No scenario or background THEN expectations" in page.locator("#scenario-detail").inner_text()
    page.locator("#scenario-list button").filter(has_text="failing expectation").click()
    assert "No recorded outcome" in page.locator("#scenario-detail").inner_text()
    checks.append("failed/evidence-gap filters, no-match empty state, and missing expectation versus missing outcome")
    page.locator("#filter").select_option("all")
    page.locator("#scenario-list button").filter(has_text="exact receipt").click()
    page.locator("#scenario-detail .source-link").first.click()
    assert page.locator("#source-dialog").is_visible()
    assert page.locator("#source-code mark").inner_text() == "THEN prints [9007199254740993]"
    page.locator("#full-source").click()
    assert "café 😀 </script><img" in page.locator("#source-code").inner_text()
    assert "9007199254740993" in page.locator("#source-code").inner_text()
    page.keyboard.press("Escape")
    assert not page.locator("#source-dialog").is_visible()
    assert page.locator("#scenario-detail .source-link").first.evaluate("el => document.activeElement === el")
    page.locator("#search").fill("café rows example 2")
    page.locator("#scenario-detail .expectation .source-link").click()
    assert page.locator("#source-code mark").inner_text() == "THEN amount == <expected>"
    page.locator("#close-source").click()
    checks.append("UTF-8/CRLF source highlights, exact large integers, example template spans, full-source view, Escape and focus restoration")
    page.locator("#calls-filter").select_option("unobserved")
    assert page.locator("#calls tr").count() == 1
    assert "unused" in page.locator("#calls").inner_text()
    page.locator("#calls .source-link").click()
    assert "helpers.gwt" in page.locator("#source-location").inner_text()
    assert page.locator("#source-code mark").inner_text() == "WHEN unused <amount>"
    page.screenshot(path=str(args.output / "source.png"))
    page.locator("#close-source").click()
    checks.append("uncalled declaration filter and imported definition source")
    for button, name in [("#download-report", "report.json"), ("#download-source", "source.json")]:
        with page.expect_download() as download:
            page.locator(button).click()
        download.value.save_as(args.output / name)
    assert json.loads((args.output / "report.json").read_text()) == json.loads((args.fixtures / "mixed/report.json").read_text())
    frozen = json.loads((args.output / "source.json").read_text())
    assert frozen["modules"]["main.gwt"] == (args.fixtures / "mixed/main.gwt").read_bytes().decode()
    assert "9007199254740993" in frozen["modules"]["main.gwt"] and "\r\n" in frozen["modules"]["main.gwt"]
    checks.append("report and source JSON downloads preserve exact contents including CRLF and large integer source")
    page.set_viewport_size({"width": 390, "height": 844})
    page.locator("#search").fill("")
    page.locator("#scenario-list button").filter(has_text="action only").click()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    source_cell = page.locator("#calls td").last.bounding_box()
    assert source_cell["x"] + source_cell["width"] <= 390
    page.screenshot(path=str(args.output / "mobile.png"), full_page=True)
    page.locator("#calls .source-link").click()
    assert page.locator("#source-dialog").bounding_box()["width"] <= 390
    page.locator("#close-source").click()
    checks.append("390px responsive layout and usable source dialog without page overflow")
    page.set_viewport_size({"width": 1280, "height": 960})
    open_report("many")
    assert page.locator("#calls tr").count() == 100
    assert "Evidence gaps remain" in page.locator("#outcome").inner_text()
    page.locator("#more-calls").click()
    assert page.locator("#calls tr").count() == 105
    assert not page.locator("#more-calls").is_visible()
    checks.append("passing report keeps evidence gaps visible and declaration pagination reveals every item")
    open_report("clean")
    assert page.locator("#outcome").inner_text() == "Required checks passed"
    assert not page.locator("#gaps").is_visible()
    open_report("declarations")
    assert "No scenarios exercised" in page.locator("#outcome").inner_text()
    assert "no executable scenarios" in page.locator("#scenario-detail").inner_text()
    open_report("check-failure")
    assert "unknown_name" in page.locator("#gates").inner_text()
    page.locator("#gates .source-link").click()
    assert page.locator("#source-code mark").inner_text() == "unknown"
    page.locator("#close-source").click()
    open_report("load-failure")
    assert page.locator("#download-source").is_disabled()
    assert page.locator("#gates .source-link").is_disabled()
    assert "No scenarios were executed" in page.locator("#scenario-detail").inner_text()
    open_report("format-failure")
    assert "Needs formatting" in page.locator("#formats").inner_text()
    assert "Passed" in page.locator("#scenario-detail").inner_text()
    checks.append("clean, allowed no-scenario, check failure with source, load failure without source, and format-only failure views")
    assert not errors, errors
    assert all(url.startswith("file:") for url in requests), requests
    checks.append("no browser script errors or network requests; all reports work offline")
    report = {"browser": browser.version, "checks": checks, "assertionsPassed": True, "networkRequests": [], "fixtureHashes": {str(path.relative_to(args.fixtures)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(args.fixtures.glob("*/review.html"))}}
    (args.output / "browser.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    browser.close()
