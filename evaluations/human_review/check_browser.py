"""Synthetic offline browser rehearsal. Produces no participant evidence."""
import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


def download(page, path):
    with page.expect_download() as pending:
        page.locator("#download").click()
    pending.value.save_as(path)
    return json.loads(path.read_text())


def set_hidden_for_test(page, hidden):
    # Test the visibility event handler, not the browser/OS's tab scheduling.
    page.evaluate("""hidden => {
      Object.defineProperty(document, 'hidden', {configurable: true, get: () => hidden});
      document.dispatchEvent(new Event('visibilitychange'));
    }""", hidden)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkpoint", type=Path)
    args = parser.parse_args()
    root = args.checkpoint.resolve()
    output = root / "browser"
    output.mkdir(exist_ok=False)
    errors, requests, checks = [], [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(args=["--no-sandbox"])
        for width, session in ((1440, "desktop"), (390, "mobile")):
            page = browser.new_page(viewport={"width": width, "height": 1000}, accept_downloads=True)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append(request.url))
            directory = root / session
            key = json.loads((directory / "facilitator-key.json").read_text())
            assert key["packet"]["purpose"] == "rehearsal"
            page.goto((directory / "session.html").as_uri())
            assert "Rehearsal" in page.locator("#purpose").inner_text()
            # A profile cannot silently default to familiar developer responses.
            page.get_by_role("button", name="Begin review").click()
            assert page.locator("#setup").is_visible()
            for name, value in {"role": "developer", "priorExposure": "yes",
                                "gwtFamiliarity": "3", "pythonFamiliarity": "3"}.items():
                page.locator(f'[name="{name}"]').select_option(value)
            page.get_by_role("button", name="Begin review").click()
            assert page.locator("#task-panel").is_visible()
            # Required answers prevent an accidental blank submission.
            page.get_by_role("button", name="Save and continue").click()
            assert "Task 1 of 4" == page.locator("#progress").inner_text()
            page.locator("#task-title").scroll_into_view_if_needed()
            page.screenshot(path=str(output / f"task-{width}.png"))
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            assert page.locator("#proposed").text_content() == key["packet"]["tasks"][0]["sources"]["proposed"]
            partial = download(page, output / f"initial-{width}.json")
            assert [r["status"] for r in partial["tasks"]] == ["draft", "unseen", "unseen", "unseen"]
            assert all(r["wallMs"] is None for r in partial["tasks"][1:])
            page.locator("#pause").click()
            assert not page.locator("#task-panel").is_visible()
            paused = download(page, output / f"paused-{width}.json")
            page.wait_for_timeout(180)
            later = download(page, output / f"paused-later-{width}.json")
            assert later["tasks"][0]["activeMs"] == paused["tasks"][0]["activeMs"]
            assert later["tasks"][0]["wallMs"] - paused["tasks"][0]["wallMs"] >= 150
            # Overlapping explicit and tab-hidden pauses must not double count,
            # or start counting when just one pause reason is removed.
            set_hidden_for_test(page, True)
            page.locator("#pause").click()
            page.wait_for_timeout(180)
            hidden = download(page, output / f"hidden-{width}.json")
            assert hidden["tasks"][0]["activeMs"] == paused["tasks"][0]["activeMs"]
            set_hidden_for_test(page, False)
            page.wait_for_timeout(180)
            resumed = download(page, output / f"resumed-{width}.json")
            assert resumed["tasks"][0]["activeMs"] - hidden["tasks"][0]["activeMs"] >= 150
            for index, (task, answer) in enumerate(zip(key["packet"]["tasks"], key["answers"])):
                assert page.locator("#proposed").text_content() == task["sources"]["proposed"]
                if session == "mobile" and index == 1:
                    page.locator("#skip").click()
                    continue
                for question, value in answer["predictions"].items():
                    page.locator(f'input[name="{question}"][value="{value}"]').check()
                page.locator('[name="recommendation"]').select_option(answer["recommendation"])
                page.locator('[name="confidence"]').select_option("5")
                page.locator('[name="rationale"]').fill("Synthetic browser rehearsal; answers supplied by the test key.")
                if index == 0:
                    filled = download(page, output / f"filled-partial-{width}.json")
                    assert filled["tasks"][0]["predictions"] == answer["predictions"]
                    assert not filled["finished"]
                page.get_by_role("button", name="Save and continue").click()
            assert page.locator("#complete").is_visible()
            final = download(page, output / f"complete-{width}.json")
            assert final["finished"]
            assert final["purpose"] == "rehearsal"
            assert sum(r["status"] == "submitted" for r in final["tasks"]) == (4 if session == "desktop" else 3)
            assert final["tasks"][0]["predictions"] == key["answers"][0]["predictions"]
            assert all(0 <= r["activeMs"] <= r["wallMs"] for r in final["tasks"])
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(output / f"complete-{width}.png"))
            checks.append({"width": width, "session": session, "profileRequired": True, "answersRequired": True,
                           "sourceMatchesPacket": True, "partialExport": True, "pauseHidesTask": True,
                           "pauseTiming": True, "simulatedVisibilityOverlap": True, "finalExport": True,
                           "skippedTasks": sum(r["status"] == "skipped" for r in final["tasks"]),
                           "noHorizontalOverflow": True})
            page.close()
        assert not errors, errors
        assert all(url.startswith(("file:", "blob:")) for url in requests), requests
        report = {"kind": "synthetic-browser-rehearsal", "humanParticipants": 0, "browser": browser.version,
                  "checks": checks, "scriptErrors": errors, "externalRequests": []}
        (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))
        browser.close()


if __name__ == "__main__":
    main()
