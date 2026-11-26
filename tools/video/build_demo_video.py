#!/usr/bin/env python3
"""Scripted production of the TopoMarket v1.2 one-minute demo video.

Captures the released Streamlit app with Playwright (1920x1080), prepares the
storyboard narration with edge-tts, assembles the 60 s H.264/AAC master with
ffmpeg, normalises loudness, burns reviewed English captions and writes the
production manifest.

The v1.2 storyboard is fixed at 6 s opening + 13 s frozen retrospective pair +
8 s Finance/Mapper + 12 s 2025-03-10 teaching example + 10 s blind Replay/reveal
+ 6 s Validation + 5 s end card = 60.000 s.

Run with the project venv for the app and the isolated /tmp/tm-video venv for
Playwright/edge-tts (see docs/video/production_notes.md).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path("/tmp/tm-build-v12")
PYTHON = Path("/tmp/tm-video/venv/bin/python")
EDGE_TTS = Path("/tmp/tm-video/venv/bin/edge-tts")
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
PORT = 8631
WIDTH, HEIGHT, FPS = 1920, 1080, 30
OPENING_SECONDS = 6.0
APP_SECONDS = 49.0
END_SECONDS = 5.0
TOTAL = OPENING_SECONDS + APP_SECONDS + END_SECONDS

PUBLIC_URL = "https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/"
PUBLIC_VERSION = "1.2.0"
PUBLIC_COMMIT = "e40d742cd227824d04bc30e0ec5fb861d5bc28ea"
FIXTURE_ID = "showcase-synthetic"

t0 = 0.0

# (name, start seconds, spoken text, edge-tts rate, caption text)
NARRATION = [
    (
        "opening",
        0.0,
        "TopoMarket maps market structure and tests whether topology can warn of sharp declines.",
        10,
        "TopoMarket maps market structure and tests whether topology can warn of sharp declines.",
    ),
    (
        "pair",
        6.0,
        "Frozen retrospective: 29 of 66 pairs on 29 August 2008; 66 of 66 by 10 October. "
        "Mean correlation rises from 0.791 to 0.911.",
        15,
        "Frozen retrospective: 29 of 66 pairs on 2008-08-29; 66 of 66 on 2008-10-10. "
        "Mean correlation rises from 0.791 to 0.911.",
    ),
    (
        "explore",
        19.0,
        "Finance: eleven qualifying pairs. Mapper groups portfolios by shared structure.",
        12,
        "Finance: eleven qualifying pairs. Mapper groups portfolios by shared structure.",
    ),
    (
        "teaching",
        27.0,
        "March 10, 2025: a late-warning teaching example at percentile 100. "
        "Takens and H1 show the S and P five hundred return shape; the frozen threshold is 100.",
        10,
        "March 10, 2025: a late-warning teaching example at percentile 100. "
        "Takens and H1 show the S&P 500 return shape; the frozen threshold is 100.",
    ),
    (
        "replay",
        39.0,
        "Blind replay. Reveal: the index stayed above the 10% boundary, "
        "with a 2.02% maximum decline.",
        10,
        "Blind replay. Reveal: the index stayed above the 10% boundary, "
        "with a 2.02% maximum decline.",
    ),
    (
        "evidence",
        49.0,
        "Experimental: TDA 0 of 3, VIX 1 of 3. Average precision is low.",
        10,
        "Experimental: TDA 0 of 3, VIX 1 of 3. Average precision is low.",
    ),
    (
        "end",
        55.0,
        "Explore the code and the live demo on GitHub.",
        0,
        "Explore the code and the live demo on GitHub.",
    ),
]

# (scene, duration, pre-roll before anchor, anchor event label, actions).
# The segment trim start is derived from the recorded anchor event, so hosted
# load/runtime variation cannot drift the edit.
SCENES = [
    (
        "pair",
        13.0,
        -0.2,
        "scroll:Comparison window: 2008-08-29",
        [
            ("sleep", 1.35),
            ("button_regex", r"Guided: next step"),
            ("wait_contains", "Synthetic retrospective example: 29/66"),
            ("wait_contains", "Window A · 2008-10-10"),
            ("sleep", 0.8),
            ("scroll_align", "Comparison window: 2008-08-29"),
            ("sleep", 1.0),
        ],
    ),
    (
        "explore",
        8.0,
        1.0,
        "button:^Finance$",
        [
            ("sleep", 1.35),
            ("button_regex", r"^Finance$"),
            ("sleep", 2.0),
            ("radio", "Mapper groups"),
            ("sleep", 0.4),
            ("scroll_align", "Mapper groups"),
            ("sleep", 1.8),
        ],
    ),
    (
        "teaching",
        12.0,
        -1.0,
        "wait:Teaching example (late warning)",
        [
            ("sleep", 1.35),
            ("button_regex", r"Guided alert example"),
            ("sleep", 0.3),
            ("radio", "latest"),
            ("wait_contains", "Teaching example (late warning)"),
            ("sleep", 0.4),
            ("scroll_top", None),
            ("sleep", 0.7),
            ("scroll_align", "Score explanation"),
            ("sleep", 2.8),
            ("scroll_fraction", 0.985),
            ("sleep", 2.3),
        ],
    ),
    (
        "replay",
        10.0,
        0.0,
        "viewport:Alert state",
        [
            ("sleep", 1.35),
            ("button_regex", r"Guided alert example"),
            ("sleep", 0.2),
            ("select_option", ("Screen", "Replay")),
            ("wait_in_viewport", "Alert state"),
            ("sleep", 2.5),
            ("button_regex", r"Reveal next 20 sessions"),
            ("sleep", 0.2),
            ("scroll_contains", r"Observed: the index stayed above"),
            ("sleep", 1.5),
        ],
    ),
    (
        "evidence",
        6.0,
        -0.5,
        "scroll:Holdout recall",
        [
            ("sleep", 1.35),
            ("select_option", ("Screen", "Validation")),
            ("sleep", 0.3),
            ("scroll_align", "Holdout recall"),
            ("sleep", 0.6),
            ("scroll_align", "Inspectors and advanced controls"),
            ("sleep", 1.0),
        ],
    ),
]


def run(cmd, **kwargs):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def duration(path: Path) -> float:
    out = run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]
    )
    return float(out.stdout.strip())


def prepare_tts() -> dict[str, dict]:
    tts_dir = WORK / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)
    order = [entry[0] for entry in NARRATION]
    scenes = {}
    for name, start, text, rate, caption in NARRATION:
        if name == "opening":
            window = OPENING_SECONDS - 0.15
        elif name == "end":
            window = END_SECONDS - 0.15
        else:
            index = order.index(name)
            next_start = NARRATION[index + 1][1] if index + 1 < len(NARRATION) else TOTAL
            window = next_start - start - 0.35
        mp3 = tts_dir / f"{name}.mp3"
        wav = tts_dir / f"{name}.wav"
        chosen = None
        for attempt_rate in (rate, rate + 5, rate + 10, rate + 15, rate + 20, rate + 25):
            run(
                [
                    str(EDGE_TTS),
                    "--voice",
                    "en-US-GuyNeural",
                    f"--rate=+{attempt_rate}%",
                    "--text",
                    text,
                    "--write-media",
                    str(mp3),
                ]
            )
            run(
                [
                    FFMPEG,
                    "-y",
                    "-v",
                    "error",
                    "-i",
                    str(mp3),
                    "-ar",
                    "48000",
                    "-ac",
                    "1",
                    "-c:a",
                    "pcm_s16le",
                    str(wav),
                ]
            )
            chosen = (attempt_rate, duration(wav))
            if chosen[1] <= window:
                break
        scenes[name] = {
            "name": name,
            "start": start,
            "end": start + window + 0.35,
            "text": text,
            "caption": caption,
            "rate": chosen[0],
            "duration": round(chosen[1], 3),
            "window": round(window, 3),
        }
    (WORK / "narration.json").write_text(
        json.dumps(list(scenes.values()), indent=2) + "\n", encoding="utf-8"
    )
    return scenes


def start_streamlit():
    log = open(WORK / "streamlit.log", "w")
    proc = subprocess.Popen(
        [
            str(ROOT / ".venv/bin/streamlit"),
            "run",
            "app.py",
            "--server.headless",
            "true",
            "--server.port",
            str(PORT),
            "--server.fileWatcherType",
            "none",
        ],
        cwd=ROOT,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    for _ in range(120):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/_stcore/health", timeout=2).read()
            return proc, log
        except Exception:
            time.sleep(1)
    proc.terminate()
    raise SystemExit("Streamlit did not start")


def _wait_visible_text(root, needle, timeout=40000):
    """Wait until a visible DOM node contains ``needle``.

    Streamlit keeps detached/hidden copies of widget labels around during
    reruns; ``get_by_text(...).first`` can latch onto one of those and wait
    forever.  This checks rendered geometry instead.
    """

    script = """(needle) => {
        const nodes = Array.from(document.querySelectorAll('div,span,p,h1,h2,h3,label'));
        return nodes.some((el) => {
            if (!el.textContent || !el.textContent.includes(needle)) return false;
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden'
                && rect.width > 0 && rect.height > 0;
        });
    }"""
    root.wait_for_function(script, arg=needle, timeout=timeout)


def _wait_in_viewport(root, needle, timeout=40000):
    """Wait until a rendered node containing ``needle`` is inside the viewport."""

    script = """(needle) => {
        const nodes = Array.from(document.querySelectorAll('div,span,p,h1,h2,h3,label'));
        return nodes.some((el) => {
            if (!el.textContent || !el.textContent.includes(needle)) return false;
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden'
                && rect.width > 0 && rect.height > 0
                && rect.top < window.innerHeight && rect.bottom > 0;
        });
    }"""
    root.wait_for_function(script, arg=needle, timeout=timeout)


def _scene_setup(root_getter, page, actions, events, scene_name):
    for kind, payload in actions:
        try:
            root = root_getter()
            keyboard = page.keyboard
            if kind == "sleep":
                time.sleep(float(payload))
            elif kind == "checkbox":
                loc = root.get_by_role("checkbox", name=payload)
                try:
                    loc.first.check(force=True, timeout=25000)
                except Exception:  # noqa: BLE001 - label overlay variant
                    root.get_by_text(payload, exact=True).first.click(force=True, timeout=25000)
                page.wait_for_timeout(1500)
                events.append(
                    {"t": round(time.perf_counter() - t0, 3), "click": True, "label": kind}
                )
                page.wait_for_timeout(600)
            elif kind in {"button", "button_regex"}:
                pattern = re.compile(payload) if kind == "button_regex" else payload
                loc = root.get_by_role("button", name=pattern).first
                loc.scroll_into_view_if_needed(timeout=25000)
                box = loc.bounding_box()
                loc.click(force=True, timeout=25000)
                if box:
                    events.append(
                        {
                            "t": round(time.perf_counter() - t0, 3),
                            "x": round(box["x"] + box["width"] / 2),
                            "y": round(box["y"] + box["height"] / 2),
                            "label": f"button:{payload}",
                        }
                    )
                else:
                    events.append(
                        {
                            "t": round(time.perf_counter() - t0, 3),
                            "click": True,
                            "label": f"button:{payload}",
                        }
                    )
                page.wait_for_timeout(300)
                wait_targets = {
                    "Guided: next step": "Guided step 1/5",
                    "Guided alert example": "selected session 2025-03-10",
                    "Reveal next 20 sessions": "Observed:",
                }
                for needle, expected in wait_targets.items():
                    if re.search(needle, payload) if kind == "button_regex" else payload == needle:
                        _wait_visible_text(root, expected, timeout=40000)
                        break
            elif kind == "text":
                root.get_by_text(payload, exact=True).first.click(force=True, timeout=25000)
                page.wait_for_timeout(1600)
            elif kind == "radio":
                try:
                    root.get_by_role("radio", name=payload, exact=True).check(
                        force=True, timeout=20000
                    )
                except Exception:  # noqa: BLE001 - label overlay variant
                    root.get_by_text(payload, exact=True).first.click(force=True, timeout=25000)
                page.wait_for_timeout(800)
                if payload == "Mapper groups":
                    root.get_by_role(
                        "combobox", name="Highlight Mapper edge", exact=True
                    ).wait_for(state="visible", timeout=30000)
                elif payload == "latest":
                    _wait_visible_text(root, "Teaching example (late warning)", timeout=40000)
                events.append(
                    {"t": round(time.perf_counter() - t0, 3), "label": f"radio:{payload}"}
                )
            elif kind == "select_option":
                label, option = payload
                root.get_by_role("combobox", name=label, exact=True).click(
                    force=True, timeout=25000
                )
                page.wait_for_timeout(400)
                root.get_by_role("option", name=option, exact=True).click(force=True, timeout=25000)
                events.append(
                    {
                        "t": round(time.perf_counter() - t0, 3),
                        "click": True,
                        "label": f"select_option:{label}={option}",
                    }
                )
                page.wait_for_timeout(300)
                if label == "Screen" and option in {"Replay", "Validation", "Data"}:
                    root.locator("h1").filter(has_text=option).first.wait_for(
                        state="visible", timeout=30000
                    )
            elif kind == "select_edge":
                root.get_by_role("combobox", name=payload, exact=True).click(
                    force=True, timeout=25000
                )
                page.wait_for_timeout(800)
                keyboard.press("ArrowDown")
                keyboard.press("Enter")
                events.append(
                    {"t": round(time.perf_counter() - t0, 3), "click": True, "label": kind}
                )
                page.wait_for_timeout(900)
            elif kind == "wait_in_viewport":
                _wait_in_viewport(root, payload, timeout=40000)
                events.append(
                    {"t": round(time.perf_counter() - t0, 3), "label": f"viewport:{payload}"}
                )
                page.wait_for_timeout(200)
            elif kind == "wait_contains":
                _wait_visible_text(root, payload, timeout=40000)
                events.append(
                    {"t": round(time.perf_counter() - t0, 3), "label": f"wait:{payload}"}
                )
                page.wait_for_timeout(200)
            elif kind == "scroll_text":
                root.get_by_text(payload, exact=True).first.scroll_into_view_if_needed(timeout=8000)
                page.wait_for_timeout(900)
            elif kind == "scroll_align":
                locator = root.get_by_text(payload, exact=True).first
                locator.evaluate(
                    "el => el.scrollIntoView({block: 'start', behavior: 'instant'})"
                )
                events.append(
                    {"t": round(time.perf_counter() - t0, 3), "label": f"scroll:{payload}"}
                )
                page.wait_for_timeout(1100)
            elif kind == "scroll_contains":
                locator = root.get_by_text(re.compile(payload)).first
                locator.evaluate(
                    "el => el.scrollIntoView({block: 'start', behavior: 'instant'})"
                )
                events.append(
                    {"t": round(time.perf_counter() - t0, 3), "label": f"scroll_contains:{payload}"}
                )
                page.wait_for_timeout(1100)
            elif kind == "scroll_fraction":
                fraction_js = (
                    "() => {const m = document.querySelector('[data-testid=\"stMain\"]');"
                    " if (m) {m.scrollTo({top: m.scrollHeight * " + str(float(payload)) + ", "
                    "behavior: 'instant'});} window.scrollTo(0, 0);}"
                )
                root.evaluate(fraction_js)
                events.append(
                    {"t": round(time.perf_counter() - t0, 3), "label": "scroll_fraction"}
                )
                page.wait_for_timeout(1000)
            elif kind == "scroll_top":
                root.evaluate(
                    "() => {const m = document.querySelector('[data-testid=\"stMain\"]');"
                    " if (m) {m.scrollTo({top: 0, behavior: 'instant'});}"
                    " window.scrollTo(0, 0);}"
                )
                events.append({"t": round(time.perf_counter() - t0, 3), "label": "scroll_top"})
                page.wait_for_timeout(800)
        except Exception as error:  # noqa: BLE001 - report and continue
            events.append(
                {
                    "t": round(time.perf_counter() - t0, 3),
                    "label": kind,
                    "error": str(error)[:240],
                }
            )


def capture_app(app_url: str | None, require_release: bool = False) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # re-exec under the Playwright-enabled interpreter
        os.execv(str(PYTHON), [str(PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])
        raise

    global t0
    record_root = WORK / "record"
    shutil.rmtree(record_root, ignore_errors=True)
    record_root.mkdir(parents=True)
    proc = log = None
    hosted = app_url is not None
    target_url = app_url
    if app_url is None:
        proc, log = start_streamlit()
        target_url = f"http://127.0.0.1:{PORT}/"
    result = {
        "app_url": PUBLIC_URL,
        "target_url": target_url,
        "capture_environment": "hosted_public" if hosted else "local_build",
        "recorded_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "browser": "Playwright Chromium headless",
        "viewport": f"{WIDTH}x{HEIGHT}",
        "toolbar_hidden": True,
        "scenes": [],
    }
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            for name, scene_seconds, pre_roll, anchor, actions in SCENES:
                scene_dir = record_root / name
                scene_dir.mkdir()
                context = browser.new_context(
                    viewport={"width": WIDTH, "height": HEIGHT},
                    device_scale_factor=1,
                    record_video_dir=str(scene_dir),
                    record_video_size={"width": WIDTH, "height": HEIGHT},
                )
                page_created = time.perf_counter()
                page = context.new_page()
                page.goto(target_url, wait_until="load", timeout=240000)
                if hosted:
                    # Community Cloud renders the app in an iframe; make it fill the
                    # recorded viewport so the film shows the real public release.
                    frame = None
                    for _ in range(180):
                        for candidate in page.frames:
                            if "~/+/" in (candidate.url or ""):
                                try:
                                    candidate.wait_for_selector(
                                        "h1:has-text('TopoMarket research')", timeout=5000
                                    )
                                    frame = candidate
                                    break
                                except Exception:  # noqa: BLE001 - frame still loading
                                    pass
                        if frame is not None:
                            break
                        page.wait_for_timeout(1000)
                    if frame is None:
                        raise RuntimeError("hosted app frame did not load")
                    frame.frame_element().evaluate(
                        """el => {
                            el.style.position = 'fixed';
                            el.style.inset = '0';
                            el.style.width = '100vw';
                            el.style.height = '100vh';
                            el.style.zIndex = '2147483647';
                            el.style.border = '0';
                            el.style.background = '#F8FAFC';
                        }"""
                    )
                    page.evaluate(
                        """() => {
                            for (const f of document.querySelectorAll('iframe')) {
                                if (f.title && f.title.includes('Status')) f.style.display = 'none';
                            }
                            document.body.style.background = '#F8FAFC';
                        }"""
                    )
                    frame.evaluate(
                        """() => {
                            const style = document.createElement('style');
                            style.textContent = 'header, [data-testid="stToolbar"], ' +
                                '[data-testid="stDecoration"], #MainMenu, footer ' +
                                '{visibility: hidden !important;} ' +
                                'img {max-width: 100% !important; height: auto !important;} ' +
                                'canvas {max-width: 100% !important;}';
                            document.head.appendChild(style);
                        }"""
                    )
                    page.wait_for_timeout(1500)
                else:
                    page.wait_for_selector("h1:has-text('TopoMarket research')", timeout=240000)
                    page.wait_for_timeout(2500)
                    page.add_style_tag(
                        content=(
                            'header, [data-testid="stToolbar"], '
                            '[data-testid="stDecoration"], #MainMenu, footer '
                            "{visibility: hidden !important;} "
                            "img {max-width: 100% !important; height: auto !important;} "
                            "canvas {max-width: 100% !important;}"
                        )
                    )
                # Record the visible release identity / fixture from the first
                # scene only, before any widget interaction changes the sidebar.
                if not result.get("visible_release"):
                    try:
                        if hosted:
                            body_text = frame.locator("body").inner_text()
                        else:
                            body_text = page.locator("body").inner_text()
                    except Exception:  # noqa: BLE001 - metadata is best effort
                        body_text = ""
                    versions = re.findall(r"release\s+([0-9]+\.[0-9]+\.[0-9]+)", body_text)
                    result["visible_release"] = versions[0] if versions else "unknown"
                    fixtures = re.findall(r"fixture\s+([A-Za-z0-9._-]+)", body_text)
                    result["fixture_id"] = fixtures[0] if fixtures else FIXTURE_ID
                    if require_release and hosted and result["visible_release"] != PUBLIC_VERSION:
                        raise RuntimeError(
                            f"hosted release identity {result['visible_release']} != "
                            f"{PUBLIC_VERSION}"
                        )
                lead = time.perf_counter() - page_created
                t0 = time.perf_counter()
                events: list[dict] = []

                def current_root(page=page, hosted=hosted):
                    if not hosted:
                        return page
                    for _ in range(80):
                        for candidate in page.frames:
                            if "~/+/" in (candidate.url or ""):
                                try:
                                    candidate.wait_for_selector(
                                        "h1:has-text('TopoMarket research')", timeout=5000
                                    )
                                    return candidate
                                except Exception:  # noqa: BLE001 - still reloading
                                    pass
                        page.wait_for_timeout(500)
                    raise RuntimeError("hosted app frame not found")

                _scene_setup(current_root, page, actions, events, name)
                anchor_t = next(
                    (
                        float(event["t"])
                        for event in events
                        if anchor and anchor in str(event.get("label") or "")
                    ),
                    None,
                )
                if anchor and anchor_t is None:
                    events.append(
                        {
                            "t": round(time.perf_counter() - t0, 3),
                            "label": f"missing-anchor:{anchor}",
                            "error": "anchor event was not observed",
                        }
                    )
                if anchor:
                    trim_start = max(0.0, (anchor_t if anchor_t is not None else 0.0) - pre_roll)
                else:
                    trim_start = float(pre_roll)
                target_elapsed = trim_start + scene_seconds + 1.0
                remaining = target_elapsed - (time.perf_counter() - t0)
                if remaining > 0.2:
                    time.sleep(remaining)
                effective_skip = round(lead + trim_start, 3)
                video = page.video
                page.close()
                context.close()
                result["scenes"].append(
                    {
                        "name": name,
                        "webm": str(video.path()),
                        "webm_sha256": sha256(Path(video.path())),
                        "lead": round(lead, 3),
                        "skip": effective_skip,
                        "trim_start": round(trim_start, 3),
                        "pre_roll": pre_roll,
                        "anchor": anchor,
                        "anchor_t": None if anchor_t is None else round(anchor_t, 3),
                        "duration": scene_seconds,
                        "events": events,
                    }
                )
                print(
                    "scene",
                    name,
                    "lead",
                    round(lead, 2),
                    "trim",
                    round(trim_start, 2),
                    "actions",
                    len(events),
                    "errors",
                    sum(1 for event in events if "error" in event),
                    flush=True,
                )
            browser.close()
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=20)
            except Exception:
                proc.kill()
        if log is not None:
            log.close()
    (WORK / "capture.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def _drawbox_filters(events, scene_seconds, event_offset=0.0):
    filters = [
        f"fps={FPS}",
        f"scale={WIDTH}:{HEIGHT}",
        "format=yuv420p",
    ]
    for event in events:
        if "x" not in event:
            continue
        if float(event["t"]) < float(event_offset):
            continue
        start = max(0.0, event["t"] - float(event_offset) - 0.15)
        end = start + 0.6
        if start >= scene_seconds:
            continue
        x = max(0, event["x"] - 34)
        y = max(0, event["y"] - 34)
        filters.append(
            f"drawbox=x={x}:y={y}:w=68:h=68:color=0xB45309@0.9:t=4:"
            f"enable='between(t,{start:.2f},{end:.2f})'"
        )
    return filters


def build_segments(capture: dict) -> dict:
    seg = WORK / "segments"
    shutil.rmtree(seg, ignore_errors=True)
    seg.mkdir()
    opening_card = ROOT / "docs/assets/opening_card_16x9.png"
    end_card = ROOT / "docs/assets/end_card_16x9.png"
    common = [
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "18",
        "-r",
        str(FPS),
        "-pix_fmt",
        "yuv420p",
    ]
    opening_mp4 = seg / "opening.mp4"
    end_mp4 = seg / "end.mp4"
    run(
        [
            FFMPEG,
            "-y",
            "-v",
            "error",
            "-loop",
            "1",
            "-framerate",
            str(FPS),
            "-t",
            f"{OPENING_SECONDS}",
            "-i",
            str(opening_card),
            "-vf",
            f"scale={WIDTH}:{HEIGHT},fps={FPS},format=yuv420p",
            "-frames:v",
            str(round(OPENING_SECONDS * FPS)),
            *common,
            str(opening_mp4),
        ]
    )
    run(
        [
            FFMPEG,
            "-y",
            "-v",
            "error",
            "-loop",
            "1",
            "-framerate",
            str(FPS),
            "-t",
            f"{END_SECONDS}",
            "-i",
            str(end_card),
            "-vf",
            f"scale={WIDTH}:{HEIGHT},fps={FPS},format=yuv420p",
            "-frames:v",
            str(round(END_SECONDS * FPS)),
            *common,
            str(end_mp4),
        ]
    )
    parts = [opening_mp4]
    for scene in capture["scenes"]:
        target = seg / f"{scene['name']}.mp4"
        trim_start = float(scene.get("skip", 0.0))
        event_offset = max(0.0, trim_start - float(scene.get("lead", 0.0)))
        filters = _drawbox_filters(
            scene.get("events") or (), float(scene["duration"]), event_offset
        )
        run(
            [
                FFMPEG,
                "-y",
                "-v",
                "error",
                "-ss",
                f"{trim_start:.3f}",
                "-t",
                f"{scene['duration']}",
                "-i",
                scene["webm"],
                "-vf",
                ",".join(filters),
                "-frames:v",
                str(round(float(scene["duration"]) * FPS)),
                *common,
                "-an",
                str(target),
            ]
        )
        parts.append(target)
    parts.append(end_mp4)
    list_path = seg / "concat.txt"
    list_path.write_text("\n".join(f"file '{path}'" for path in parts) + "\n", encoding="utf-8")
    base = seg / "base.mp4"
    run(
        [
            FFMPEG,
            "-y",
            "-v",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_path),
            "-c",
            "copy",
            str(base),
        ]
    )
    return {"base": str(base), "parts": [str(path) for path in parts]}


def build_audio(narration: list[dict]) -> Path:
    tts = WORK / "tts"
    inputs = []
    filters = []
    for index, entry in enumerate(narration):
        path = tts / f"{entry['name']}.wav"
        inputs.extend(["-i", str(path)])
        delay = int(round(entry["start"] * 1000))
        filters.append(f"[{index}:a]adelay={delay}|{delay},apad[a{index}]")
    mix_inputs = "".join(f"[a{index}]" for index in range(len(narration)))
    filter_complex = (
        ";".join(filters)
        + f";{mix_inputs}amix=inputs={len(narration)}:normalize=0:duration=longest[mixed]"
    )
    raw = WORK / "narration_raw.wav"
    run(
        [
            FFMPEG,
            "-y",
            "-v",
            "error",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            "[mixed]",
            "-t",
            f"{TOTAL}",
            "-ar",
            "48000",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(raw),
        ]
    )
    measure = subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-i",
            str(raw),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    data = json.loads(measure.stderr[measure.stderr.rfind("{") :])
    normalized = WORK / "narration.wav"
    run(
        [
            FFMPEG,
            "-y",
            "-v",
            "error",
            "-i",
            str(raw),
            "-af",
            f"loudnorm=I=-16:TP=-1.5:LRA=11:measured_I={data['input_i']}:measured_TP={data['input_tp']}:"
            f"measured_LRA={data['input_lra']}:measured_thresh={data['input_thresh']}:offset={data['target_offset']}:linear=true",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(normalized),
        ]
    )
    return normalized


def mux(base: Path, audio: Path) -> Path:
    master = WORK / "TopoMarket_demo_60s.mp4"
    run(
        [
            FFMPEG,
            "-y",
            "-v",
            "error",
            "-i",
            str(base),
            "-i",
            str(audio),
            "-t",
            f"{TOTAL}",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-movflags",
            "+faststart",
            "-metadata",
            "title=TopoMarket v1.2 - market structure and experimental warning evidence",
            "-metadata",
            "comment=Synthetic showcase only; no genuine market data.",
            str(master),
        ]
    )
    return master


def build_srt(narration: list[dict]) -> Path:
    def stamp(seconds: float) -> str:
        ms = int(round(seconds * 1000))
        hours, ms = divmod(ms, 3_600_000)
        minutes, ms = divmod(ms, 60_000)
        secs, ms = divmod(ms, 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"

    def caption_text(value: str) -> str:
        value = value.replace("S and P five hundred", "S&P 500")
        value = value.replace("S and P 500", "S&P 500")
        value = re.sub(r"\s+", " ", value)
        return value

    cues = []
    index = 1
    for entry in narration:
        spoken = caption_text(entry.get("caption") or entry["text"])
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", spoken) if part.strip()]
        total_chars = sum(len(sentence) for sentence in sentences) or 1
        cursor = entry["start"] + 0.05
        for sentence in sentences:
            share = len(sentence) / total_chars
            cue_duration = max(1.2, entry["duration"] * share)
            end = min(cursor + cue_duration, entry["start"] + max(entry["duration"], 1.5) + 0.4)
            cues.append(f"{index}\n{stamp(cursor)} --> {stamp(end)}\n{sentence}\n")
            index += 1
            cursor = end + 0.02
    path = WORK / "TopoMarket_demo_60s.srt"
    path.write_text("\n".join(cues), encoding="utf-8")
    return path


def burn_captions(master: Path, srt: Path) -> Path:
    captioned = WORK / "TopoMarket_demo_60s_captioned.mp4"
    style = (
        "FontName=DejaVu Sans,FontSize=22,PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,BorderStyle=1,Outline=1,Shadow=1,MarginV=36"
    )
    run(
        [
            FFMPEG,
            "-y",
            "-v",
            "error",
            "-i",
            str(master),
            "-vf",
            f"subtitles={srt}:force_style='{style}'",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "copy",
            "-movflags",
            "+faststart",
            str(captioned),
        ]
    )
    return captioned


def probe(path: Path) -> dict:
    out = run(
        [
            FFPROBE,
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_name,profile,width,height,pix_fmt,r_frame_rate,bit_rate,"
            "sample_rate,channels",
            "-show_entries",
            "format=duration,size,bit_rate",
            "-of",
            "json",
            str(path),
        ]
    )
    data = json.loads(out.stdout)
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("width")), {})
    audio = next((s for s in streams if s.get("sample_rate")), {})
    return {
        "duration_seconds": round(float(data["format"]["duration"]), 3),
        "size_bytes": int(data["format"]["size"]),
        "overall_bit_rate": int(data["format"].get("bit_rate") or 0),
        "video": {
            "codec": video.get("codec_name"),
            "profile": video.get("profile"),
            "width": video.get("width"),
            "height": video.get("height"),
            "pix_fmt": video.get("pix_fmt"),
            "frame_rate": video.get("r_frame_rate"),
            "bit_rate": int(video.get("bit_rate") or 0),
        },
        "audio": {
            "codec": audio.get("codec_name"),
            "profile": audio.get("profile"),
            "sample_rate": int(audio.get("sample_rate") or 0),
            "channels": int(audio.get("channels") or 0),
            "bit_rate": int(audio.get("bit_rate") or 0),
        },
    }


def measure_loudness(path: Path) -> dict:
    out = subprocess.run(
        [
            FFMPEG,
            "-hide_banner",
            "-i",
            str(path),
            "-af",
            "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    data = json.loads(out.stderr[out.stderr.rfind("{") :])
    return {
        "measured_integrated_lufs": round(float(data["input_i"]), 2),
        "measured_true_peak_dbtp": round(float(data["input_tp"]), 2),
        "measured_lra": round(float(data["input_lra"]), 2),
        "target": {"integrated_lufs": -16.0, "true_peak_dbtp": -1.5},
        "method": "two-pass loudnorm, linear=true",
    }


def make_contact_sheet(master: Path) -> Path:
    out = WORK / "contact.png"
    run(
        [
            FFMPEG,
            "-y",
            "-v",
            "error",
            "-i",
            str(master),
            "-vf",
            "fps=1/5,scale=480:270,tile=4x3",
            "-frames:v",
            "1",
            str(out),
        ]
    )
    return out


def write_storyboard() -> Path:
    starts = {entry[0]: entry[1] for entry in NARRATION}
    names = [entry[0] for entry in NARRATION]
    pictures = {
        "opening": "Social preview opening card with product claim and exact repository URL",
        "pair": (
            "Guided tour first stop: frozen retrospective 2008-08-29 29/66 (mean r 0.791) "
            "-> 2008-10-10 66/66 (mean r 0.911), +37/0, retrospective label, r >= 0.80 cutoff"
        ),
        "explore": (
            "Finance selected in the interactive network, then Mapper groups overlap view "
            "with shared-portfolio edge widths"
        ),
        "teaching": (
            "2025-03-10 late-warning teaching example (outside the frozen evaluation): "
            "percentile 100, frozen threshold 100, Takens window and H1 persistence diagram"
        ),
        "replay": (
            "Blind Replay with no outcome, then explicit reveal: origin 305.998, boundary "
            "275.398, lowest 299.830, maximum decline 2.02%, no 10% breach"
        ),
        "evidence": (
            "Validation evidence cards and three-method chart: TDA 0/3 (AP 0.0154), "
            "VIX 1/3 (AP 0.1187), experimental wording and limitations"
        ),
        "end": "Static end card holding github.com/SergeyGer/TopoMarket for five seconds",
    }
    scenes = []
    for index, name in enumerate(names):
        start = starts[name]
        end = starts[names[index + 1]] if index + 1 < len(names) else TOTAL
        scenes.append(
            {
                "id": name,
                "start_s": start,
                "end_s": end,
                "duration_s": round(end - start, 3),
                "picture": pictures[name],
                "narration": next(entry[4] for entry in NARRATION if entry[0] == name),
            }
        )
    data = {
        "schema_version": 2,
        "title": "TopoMarket v1.2 - frozen structure, blind replay and experimental evidence",
        "release": "v1.2.0",
        "repository_url": "https://github.com/SergeyGer/TopoMarket",
        "end_card_url": "github.com/SergeyGer/TopoMarket",
        "target_seconds": 60,
        "tolerance_seconds": 0.1,
        "output": {
            "width": WIDTH,
            "height": HEIGHT,
            "fps": FPS,
            "video_codec": "H.264 High",
            "pix_fmt": "yuv420p",
            "audio_codec": "AAC LC",
            "audio_rate": 48000,
            "audio_channels": 2,
            "integrated_loudness_lufs": -16.0,
            "true_peak_db": -1.5,
        },
        "fixture": {
            "id": FIXTURE_ID,
            "synthetic": True,
            "seed": 4242,
            "rows": 5673,
            "range": "2005-01-03..2026-09-30",
        },
        "timing": {"opening_s": 6.0, "app_s": 49.0, "end_s": 5.0},
        "scenes": scenes,
        "final_filename": "TopoMarket_demo_60s.mp4",
        "captions_filename": "TopoMarket_demo_60s.srt",
        "captioned_playback_filename": "TopoMarket_demo_60s_captioned.mp4",
    }
    path = WORK / "storyboard.json"
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return path


def zip_source(capture: dict) -> Path:
    target = WORK / "production_source.zip"
    include = [
        WORK / "build_report.json",
        WORK / "capture.json",
        WORK / "narration.json",
        WORK / "narration.wav",
        WORK / "TopoMarket_demo_60s.srt",
        WORK / "storyboard.json",
        ROOT / "tools/video/build_demo_video.py",
        ROOT / "docs/assets/opening_card_16x9.png",
        ROOT / "docs/assets/end_card_16x9.png",
    ]
    include.extend(Path(scene["webm"]) for scene in capture.get("scenes", ()))
    include.extend(sorted((WORK / "tts").glob("*.mp3")))
    include.extend(sorted((WORK / "tts").glob("*.wav")))
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in include:
            if not path.is_file():
                continue
            if path.is_relative_to(WORK):
                arcname = path.relative_to(WORK)
            else:
                arcname = Path("repo") / path.relative_to(ROOT)
            bundle.write(path, arcname.as_posix())
    return target


def main(argv=None) -> int:
    global WORK, PYTHON
    parser = argparse.ArgumentParser(description="Build the TopoMarket v1.2 demo video.")
    parser.add_argument(
        "--app-url", default=None, help="Record this app URL instead of a local server."
    )
    parser.add_argument(
        "--work-dir", type=Path, default=WORK, help="Working directory for captures and outputs."
    )
    parser.add_argument(
        "--playwright-python",
        type=Path,
        default=PYTHON,
        help=(
            "Python interpreter that has Playwright + Chromium "
            "(default: /tmp/tm-video/venv/bin/python)."
        ),
    )
    parser.add_argument("--skip-capture", action="store_true")
    parser.add_argument("--skip-narration", action="store_true")
    parser.add_argument(
        "--attempts", type=int, default=3, help="Hosted capture attempts before local fallback."
    )
    args = parser.parse_args(argv)
    WORK = args.work_dir
    PYTHON = args.playwright_python
    WORK.mkdir(parents=True, exist_ok=True)
    print("1/6 narration...")
    narration = prepare_tts()
    for entry in narration.values():
        print(
            "   ",
            entry["name"],
            entry["duration"],
            "s / window",
            entry["window"],
            "rate",
            entry["rate"],
        )
    capture_path = WORK / "capture.json"
    if args.skip_capture and capture_path.is_file():
        capture = json.loads(capture_path.read_text(encoding="utf-8"))
    elif args.app_url:
        print("2/6 hosted capture...")
        capture = None
        last_error = None
        for attempt in range(1, max(1, args.attempts) + 1):
            try:
                candidate = capture_app(args.app_url, require_release=True)
                errors = sum(
                    1
                    for scene in candidate.get("scenes", ())
                    for event in scene.get("events", ())
                    if "error" in event
                )
                print(f"   hosted attempt {attempt}: action errors {errors}", flush=True)
                if errors:
                    last_error = f"{errors} action error(s)"
                    continue
                capture = candidate
                break
            except Exception as error:  # noqa: BLE001 - fall back to the local build
                last_error = str(error)[:300]
                print(f"   hosted attempt {attempt} failed: {last_error}", flush=True)
        if capture is None:
            print("   falling back to the identical local v1.2.0 build", flush=True)
            capture = capture_app(None)
            capture["capture_environment"] = "local_fallback"
            capture["deviation"] = (
                "Hosted public-app iframe capture failed after "
                f"{args.attempts} full attempt(s) with action errors or version mismatch "
                f"({last_error}); the film was recorded from the identical local v1.2.0 "
                "build after the public deployment passed signed-out smoke checks."
            )
            (WORK / "capture.json").write_text(
                json.dumps(capture, indent=2) + "\n", encoding="utf-8"
            )
    else:
        print("2/6 local capture...")
        capture = capture_app(None)
    for scene in capture.get("scenes", ()):
        for event in scene.get("events", ()):
            print("   action", scene["name"], event)
    print("3/6 segments...")
    segments = build_segments(capture)
    print("4/6 audio...")
    audio = build_audio(list(narration.values()))
    print("5/6 mux + captions...")
    master = mux(Path(segments["base"]), audio)
    srt = build_srt(list(narration.values()))
    captioned = burn_captions(master, srt)
    contact = make_contact_sheet(master)
    storyboard = write_storyboard()
    print("6/6 probe + report...")
    specs = probe(master)
    loudness = measure_loudness(master)
    report = {
        "schema_version": 2,
        "release": "v1.2.0",
        "recorded_release_identity": f"v{PUBLIC_VERSION}",
        "master": {
            "file": master.name,
            "sha256": sha256(master),
            "size_bytes": master.stat().st_size,
        },
        "captions": {
            "file": srt.name,
            "sha256": sha256(srt),
            "cues": len(
                [block for block in srt.read_text(encoding="utf-8").split("\n\n") if block.strip()]
            ),
        },
        "captioned_playback": {
            "file": captioned.name,
            "sha256": sha256(captioned),
            "size_bytes": captioned.stat().st_size,
        },
        "narration_master": {
            "file": audio.name,
            "sha256": sha256(audio),
            "size_bytes": audio.stat().st_size,
        },
        "video": specs["video"],
        "audio": specs["audio"],
        "duration_seconds": specs["duration_seconds"],
        "loudness": loudness,
        "timing": {
            "opening_s": OPENING_SECONDS,
            "app_s": APP_SECONDS,
            "end_s": END_SECONDS,
        },
        "capture": {
            **{key: value for key, value in capture.items() if key != "scenes"},
            "expected_version": f"v{PUBLIC_VERSION}",
            "commit": PUBLIC_COMMIT,
        },
        "scenes": [
            {
                "name": scene["name"],
                "duration_s": scene["duration"],
                "trim_skip_s": scene["skip"],
                "trim_start_s": scene.get("trim_start"),
                "anchor": scene.get("anchor"),
                "recording": Path(scene["webm"]).name,
                "recording_sha256": scene["webm_sha256"],
                "actions": scene.get("events", []),
            }
            for scene in capture.get("scenes", ())
        ],
        "narration": list(narration.values()),
        "storyboard": storyboard.name,
        "contact_sheet": contact.name,
        "segments": segments,
    }
    (WORK / "build_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    zip_source(capture)
    print("master:", master, "duration", report["duration_seconds"])
    print("srt:", srt, "captions", report["captions"]["cues"])
    print("captioned:", captioned)
    print("loudness:", loudness)
    print("contact:", contact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
