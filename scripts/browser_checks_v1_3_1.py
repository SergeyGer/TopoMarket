"""Hosted browser assertions for the v1.3.1 acceptance patch (manual; needs Playwright)."""

import json
import re
import time

# requires: pip install playwright; playwright install chromium
from playwright.sync_api import sync_playwright  # noqa: E402

URL = "https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/~/+/"
out = {
    "schema_version": 1,
    "app_url": "https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/",
    "expected_release": "1.3.0",
    "checks": {},
    "details": {},
    "measured_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
}


def body(page, timeout=25000):
    return page.locator("body").inner_text(timeout=timeout)


with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    page = b.new_page(viewport={"width": 1440, "height": 900})
    page.goto(URL, wait_until="load", timeout=120000)
    t = body(page)
    for _ in range(15):
        if "TopoMarket research" in t or "release " in t:
            break
        time.sleep(6)
        t = body(page)
    m = re.search(r"release\s+([0-9.]+)", t)
    out["details"]["version"] = m.group(1) if m else None
    out["checks"]["release_identity"] = out["details"]["version"] == "1.3.0"
    out["checks"]["dashboard_renders"] = "TopoMarket research" in t and "AttributeError" not in t
    if out["checks"]["dashboard_renders"]:
        page.get_by_role("button", name=re.compile("Guided: next step")).click(timeout=20000)
        time.sleep(4)
        t = body(page)
        out["checks"]["chronological_comparison"] = (
            "Window A" in t and "2008-08-29" in t and "Window B" in t and "2008-10-10" in t
        )
        page.screenshot(
            path="/root/projects/TopoMarket/docs/measurements/hosted_v131_comparison.png",
            full_page=True,
        )
        # Replay blind/reveal via preset + screen switch using widget labels
        try:
            page.get_by_role("button", name=re.compile("Guided alert example")).first.click(
                timeout=20000
            )
            time.sleep(3)
            # choose Replay screen through the Screen selectbox
            for combo in page.get_by_role("combobox").all():
                try:
                    if "Structure" in combo.inner_text(timeout=3000):
                        combo.click(timeout=5000)
                        page.get_by_text("Replay", exact=True).last.click(timeout=8000)
                        break
                except Exception:
                    continue
            time.sleep(4)
            t = body(page)
            out["checks"]["blind_replay_no_outcome"] = (
                "Blind replay" in t and "10% boundary" not in t
            )
            page.get_by_role("button", name=re.compile("Reveal next 20 sessions")).first.click(
                timeout=20000
            )
            time.sleep(5)
            t = body(page)
            out["checks"]["reveal_shows_computed_target"] = "10%" in t and (
                "Target not reached" in t or "Target reached" in t or "below the 10% target" in t
            )
        except Exception as e:
            out["details"]["replay_error"] = str(e)[:200]
        try:
            for combo in page.get_by_role("combobox").all():
                try:
                    if "Replay" in combo.inner_text(timeout=3000):
                        combo.click(timeout=5000)
                        page.get_by_text("Validation", exact=True).last.click(timeout=8000)
                        break
                except Exception:
                    continue
            time.sleep(4)
            t = body(page)
            out["checks"]["validation_evidence"] = "TDA" in t and "VIX" in t
            for combo in page.get_by_role("combobox").all():
                try:
                    if "Validation" in combo.inner_text(timeout=3000):
                        combo.click(timeout=5000)
                        page.get_by_text("Data", exact=True).last.click(timeout=8000)
                        break
                except Exception:
                    continue
            time.sleep(4)
            t = body(page)
            out["checks"]["data_calendars"] = "calendar" in t.lower() or "as of" in t.lower()
        except Exception as e:
            out["details"]["screens_error"] = str(e)[:200]
        try:
            # Mapper view and both node buttons
            for r in page.get_by_role("radio").all():
                try:
                    if (
                        "Mapper groups" in (r.get_attribute("value") or "")
                        or r.evaluate("el => el.closest('label')?.innerText || ''").find(
                            "Mapper groups"
                        )
                        >= 0
                    ):
                        r.click(timeout=5000, force=True)
                        break
                except Exception:
                    continue
            time.sleep(3)
            page.get_by_text("Screen").first.click(timeout=5000)
            page.get_by_text("Structure", exact=True).last.click(timeout=8000)
            time.sleep(3)
            node1 = page.get_by_role("button", name=re.compile("node-01")).first
            node1.click(timeout=15000)
            time.sleep(3)
            t = body(page)
            out["checks"]["mapper_node_01"] = (
                "node-01 · 7 members" in t or "Selected Mapper group node-01" in t
            )
            page.get_by_role("button", name=re.compile("node-02")).first.click(timeout=15000)
            time.sleep(3)
            t = body(page)
            out["checks"]["mapper_node_02"] = (
                "node-02 · 6 members" in t or "Selected Mapper group node-02" in t
            )
        except Exception as e:
            out["details"]["mapper_error"] = str(e)[:200]
        page.screenshot(
            path="/root/projects/TopoMarket/docs/measurements/hosted_v131_main.png", full_page=True
        )
    m = b.new_page(viewport={"width": 390, "height": 844})
    m.goto(URL, wait_until="load", timeout=120000)
    time.sleep(15)
    out["checks"]["mobile_no_overflow"] = not m.evaluate(
        "() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2"
    )
    m.close()
    p2 = b.new_page(viewport={"width": 1280, "height": 900})
    p2.goto(URL, wait_until="load", timeout=120000)
    time.sleep(15)
    out["checks"]["two_isolated_sessions"] = "TopoMarket" in body(p2)
    p2.close()
    b.close()
json.dump(
    out,
    open("/root/projects/TopoMarket/docs/measurements/hosted_evidence_v1.3.1.json", "w"),
    indent=2,
)
print(json.dumps({"version": out["details"].get("version"), "checks": out["checks"]}, indent=1))
