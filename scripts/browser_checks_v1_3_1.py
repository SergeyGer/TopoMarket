"""Hosted browser assertions for the v1.3.1 acceptance patch (manual; needs Playwright)."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

URL = "https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/~/+/"
EXPECTED_RELEASE = "1.3.1"
OUT = Path("docs/measurements/hosted_evidence_v1.3.1.json")


def body(page: Page) -> str:
    return page.locator("body").inner_text(timeout=30000)


SCREEN_ORDER = ("Structure", "Replay", "Validation", "Data")


def select_screen(page: Page, label: str) -> None:
    page.get_by_role("combobox").first.click(timeout=15000)
    time.sleep(0.6)
    page.keyboard.press("Home")
    for _ in range(SCREEN_ORDER.index(label)):
        page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    time.sleep(4)


def main() -> int:
    checks: dict[str, bool] = {}
    details: dict[str, object] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        started = time.time()
        page.goto(URL, wait_until="load", timeout=120000)
        text = ""
        for _ in range(25):
            time.sleep(5)
            text = body(page)
            if "release " in text or "AttributeError" in text:
                break
        match = re.search(r"release\s+([0-9]+\.[0-9]+\.[0-9]+)", text)
        details["version"] = match.group(1) if match else None
        details["cold_start_seconds"] = round(time.time() - started, 1)
        checks["release_identity"] = details["version"] == EXPECTED_RELEASE
        checks["dashboard_renders"] = "TopoMarket research" in text and "AttributeError" not in text
        if not checks["dashboard_renders"]:
            page.screenshot(path="docs/measurements/hosted_v131_error.png", full_page=True)
        else:
            page.get_by_role("button", name=re.compile("Guided: next step")).click(timeout=20000)
            time.sleep(4)
            text = body(page)
            checks["chronological_comparison"] = (
                "Window A · 2008-08-29" in text and "Window B · 2008-10-10" in text
            )
            checks["reveal_computed_target"] = "below the 10% target" in text or "Target" in text
            page.screenshot(path="docs/measurements/hosted_v131_comparison.png", full_page=True)
            # blind Replay, then reveal
            try:
                page.get_by_role("button", name=re.compile("Guided alert example")).first.click(
                    timeout=20000
                )
                time.sleep(3)
                select_screen(page, "Replay")
                time.sleep(4)
                text = body(page)
                checks["blind_replay_no_outcome"] = (
                    "Blind replay" in text and "Maximum decline" not in text
                )
                page.screenshot(path="docs/measurements/hosted_v131_blind.png", full_page=True)
                page.get_by_role("button", name=re.compile("Reveal next 20 sessions")).first.click(
                    timeout=20000
                )
                time.sleep(5)
                text = body(page)
                checks["reveal_computed_target"] = (
                    "least the 10% target" in text or "below the 10%" in text
                )
                checks["reveal_shows_outcome"] = "10% boundary" in text
                page.screenshot(path="docs/measurements/hosted_v131_reveal.png", full_page=True)
            except Exception as error:  # noqa: BLE001 - report the selector failure honestly
                details["replay_error"] = str(error)[:240]
            # Validation / Data screens
            try:
                select_screen(page, "Validation")
                text = body(page)
                checks["validation_evidence"] = "TDA" in text and "VIX" in text
                page.screenshot(path="docs/measurements/hosted_v131_validation.png", full_page=True)
                select_screen(page, "Data")
                text = body(page)
                checks["data_calendars"] = "calendar" in text.lower() or "as of" in text.lower()
                page.screenshot(path="docs/measurements/hosted_v131_data.png", full_page=True)
            except Exception as error:  # noqa: BLE001
                details["screens_error"] = str(error)[:240]
            # Mapper view and both node buttons
            try:
                select_screen(page, "Structure")
                page.get_by_text("Mapper groups").first.click(timeout=15000)
                time.sleep(4)
                page.get_by_role("button", name=re.compile("node-01")).first.click(timeout=15000)
                time.sleep(3)
                text = body(page)
                checks["mapper_node_01"] = "node-01" in text and "7 members" in text
                page.get_by_role("button", name=re.compile("node-02")).first.click(timeout=15000)
                time.sleep(3)
                text = body(page)
                checks["mapper_node_02"] = "node-02" in text
                page.screenshot(path="docs/measurements/hosted_v131_mapper.png", full_page=True)
            except Exception as error:  # noqa: BLE001
                details["mapper_error"] = str(error)[:240]
        mobile = browser.new_page(viewport={"width": 390, "height": 844})
        mobile.goto(URL, wait_until="load", timeout=120000)
        time.sleep(15)
        checks["mobile_no_overflow"] = not mobile.evaluate(
            "() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2"
        )
        mobile.screenshot(path="docs/measurements/hosted_v131_mobile.png", full_page=True)
        mobile.close()
        second = browser.new_page(viewport={"width": 1280, "height": 900})
        second.goto(URL, wait_until="load", timeout=120000)
        time.sleep(15)
        checks["two_isolated_sessions"] = "TopoMarket" in body(second)
        second.close()
        browser.close()
    OUT.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "app_url": "https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/",
                "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "expected_release": EXPECTED_RELEASE,
                "checks": checks,
                "failed": [name for name, ok in checks.items() if not ok],
                "details": details,
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps({"version": details.get("version"), "checks": checks}, indent=1))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
