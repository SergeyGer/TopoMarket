#!/usr/bin/env python3
"""Scripted production of the TopoMarket one-minute demo video.

Captures the released Streamlit app with Playwright (1920x1080), prepares the
storyboard narration with edge-tts, assembles the 60 s H.264/AAC master with
ffmpeg, normalises loudness and writes English SRT captions.

Run with the project venv for the app and the isolated /tmp/tm-video venv for
Playwright/edge-tts (see tools/video/README.md).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORK = Path("/tmp/tm-build/work")
PYTHON = Path("/tmp/tm-video/venv/bin/python")
EDGE_TTS = Path("/tmp/tm-video/venv/bin/edge-tts")
FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"
PORT = 8631
WIDTH, HEIGHT, FPS = 1920, 1080, 30
OPENING_SECONDS = 6.5
APP_SECONDS = 48.5
END_SECONDS = 5.0
TOTAL = OPENING_SECONDS + APP_SECONDS + END_SECONDS

t0 = 0.0

NARRATION = [
    (
        "opening",
        0.0,
        "TopoMarket explores how market structure changes under stress and tests whether "
        "topology can flag major declines early.",
        15,
    ),
    (
        "structure",
        6.5,
        "Start with twelve industry portfolios. As I move from a quiet window to a stressed "
        "one, more industries begin moving together.",
        0,
    ),
    (
        "mapper",
        16.0,
        "The correlation map shows which industries move together. Mapper groups them by "
        "similar behavior and highlights industries shared between groups.",
        0,
    ),
    (
        "alert",
        27.0,
        "A separate indicator uses the shape of recent S and P five hundred returns to flag "
        "unusual behavior. Here is the alert and the feature behind it.",
        0,
    ),
    (
        "replay",
        39.0,
        "Replay shows when the alert appeared. Revealing the outcome lets us see that the "
        "decline had already begun.",
        0,
    ),
    ("validation", 50.0, "The results show where the signal works and where it misses.", 0),
    ("end", 55.0, "Explore the code and the live demo on GitHub.", 0),
]

SCENES = [
    (
        "structure",
        9.5,
        1.8,
        [
            ("button_regex", r"Quiet period"),
            ("sleep", 4.0),
            ("button_regex", r"Stress transition"),
            ("sleep", 2.0),
        ],
    ),
    (
        "mapper",
        11.0,
        1.0,
        [
            ("text", "Inspectors and advanced controls"),
            ("select_option", ("Industry member", "money")),
            ("radio", "Mapper groups"),
            ("scroll_align", "Mapper groups"),
            ("select_edge", "Highlight Mapper edge"),
            ("sleep", 3.0),
        ],
    ),
    (
        "alert",
        12.0,
        1.0,
        [
            ("button_regex", r"Late warning"),
            ("scroll_align", "Shared timeline"),
            ("sleep", 2.0),
            ("scroll_align", "Score explanation"),
            ("sleep", 3.4),
        ],
    ),
    (
        "replay",
        11.0,
        3.2,
        [
            ("button_regex", r"Late warning"),
            ("select_option", ("Screen", "Replay")),
            ("sleep", 2.2),
            ("button_regex", r"Reveal next 20 sessions"),
            ("sleep", 1.0),
            ("scroll_fraction", 0.10),
            ("sleep", 3.0),
        ],
    ),
    (
        "validation",
        5.0,
        3.4,
        [
            ("select_option", ("Screen", "Validation")),
            ("scroll_fraction", 0.25),
            ("sleep", 2.5),
        ],
    ),
]


def run(cmd, **kwargs):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kwargs)


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
    for name, start, text, rate in NARRATION:
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
        for attempt_rate in (rate, rate + 5, rate + 10, rate + 15):
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
            "text": text,
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


def _act(fn, events, label, attempts=3):
    last_error = None
    for _ in range(attempts):
        try:
            fn()
            events.append({"t": round(time.perf_counter() - t0, 3), "label": label})
            return
        except Exception as error:  # noqa: BLE001 - retry with Escape
            last_error = error
            print("retry action", label, str(error)[:200], file=sys.stderr)
            time.sleep(0.8)
    events.append(
        {"t": round(time.perf_counter() - t0, 3), "label": label, "error": str(last_error)[:300]}
    )


def _scene_setup(page, actions, events, scene_name):
    for kind, payload in actions:
        try:
            if kind == "sleep":
                time.sleep(float(payload))
            elif kind == "button_regex":
                loc = page.get_by_role("button", name=re.compile(payload)).first
                loc.scroll_into_view_if_needed(timeout=8000)
                box = loc.bounding_box()
                loc.click(timeout=8000)
                if box:
                    events.append(
                        {
                            "t": round(time.perf_counter() - t0, 3),
                            "x": round(box["x"] + box["width"] / 2),
                            "y": round(box["y"] + box["height"] / 2),
                            "label": kind,
                        }
                    )
                page.wait_for_timeout(500)
            elif kind == "text":
                box = page.get_by_text(payload, exact=True).first.bounding_box()
                page.get_by_text(payload, exact=True).first.click(timeout=8000)
                page.wait_for_timeout(700)
            elif kind == "radio":
                page.get_by_text(payload, exact=True).first.click(timeout=8000)
                page.wait_for_timeout(900)
            elif kind == "select_option":
                label, option = payload
                page.get_by_role("combobox", name=label, exact=True).click(timeout=8000)
                page.wait_for_timeout(700)
                page.get_by_role("option", name=option, exact=True).click(timeout=8000)
                events.append(
                    {"t": round(time.perf_counter() - t0, 3), "click": True, "label": kind}
                )
                page.wait_for_timeout(900)
            elif kind == "select_edge":
                page.get_by_role("combobox", name=payload, exact=True).click(timeout=8000)
                page.wait_for_timeout(800)
                page.keyboard.press("ArrowDown")
                page.keyboard.press("Enter")
                events.append(
                    {"t": round(time.perf_counter() - t0, 3), "click": True, "label": kind}
                )
                page.wait_for_timeout(900)
            elif kind == "scroll_text":
                page.get_by_text(payload, exact=True).first.scroll_into_view_if_needed(timeout=8000)
                page.wait_for_timeout(900)
            elif kind == "scroll_align":
                locator = page.get_by_text(payload, exact=True).first
                scroll_js = "el => el.scrollIntoView({block: 'start', behavior: 'smooth'})"
                locator.evaluate(scroll_js)
                page.wait_for_timeout(1100)
            elif kind == "scroll_fraction":
                fraction_js = (
                    "(f) => window.scrollTo({top: document.body.scrollHeight * f, "
                    "behavior: 'smooth'})"
                )
                page.evaluate(fraction_js, payload)
                page.wait_for_timeout(1000)
        except Exception as error:  # noqa: BLE001 - report and continue
            events.append(
                {"t": round(time.perf_counter() - t0, 3), "label": kind, "error": str(error)[:240]}
            )


def capture_app(app_url: str | None) -> dict:
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
    if app_url is None:
        proc, log = start_streamlit()
        app_url = f"http://127.0.0.1:{PORT}/"
    result = {"app_url": app_url, "scenes": []}
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(args=["--no-sandbox"])
            for name, scene_seconds, skip_seconds, actions in SCENES:
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
                page.goto(app_url, wait_until="load", timeout=240000)
                page.wait_for_selector("h1:has-text('TopoMarket research')", timeout=240000)
                page.wait_for_timeout(2500)
                page.add_style_tag(
                    content=(
                        'header, [data-testid="stToolbar"], '
                        '[data-testid="stDecoration"], #MainMenu, footer '
                        "{visibility: hidden !important;}"
                    )
                )
                lead = time.perf_counter() - page_created
                t0 = time.perf_counter()
                events: list[dict] = []
                _scene_setup(page, actions, events, name)
                remaining = (scene_seconds + skip_seconds) - (time.perf_counter() - t0)
                if remaining > 0.2:
                    time.sleep(remaining)
                video = page.video
                page.close()
                context.close()
                result["scenes"].append(
                    {
                        "name": name,
                        "webm": str(video.path()),
                        "lead": round(lead, 3),
                        "skip": skip_seconds,
                        "duration": scene_seconds,
                        "events": events,
                    }
                )
                print(
                    "scene",
                    name,
                    "lead",
                    round(lead, 2),
                    "actions",
                    len(events),
                    "errors",
                    sum(1 for event in events if "error" in event),
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


def _drawbox_filters(events, scene_seconds, skip_seconds=0.0):
    filters = [
        f"fps={FPS}",
        f"scale={WIDTH}:{HEIGHT}",
        "format=yuv420p",
        "fade=t=in:st=0:d=0.18",
        f"fade=t=out:st={max(0.0, scene_seconds - 0.22):.2f}:d=0.22",
    ]
    for event in events:
        if "x" not in event:
            continue
        start = max(0.0, event["t"] - float(skip_seconds) - 0.15)
        end = start + 0.6
        x = max(0, event["x"] - 34)
        y = max(0, event["y"] - 34)
        filters.append(
            f"drawbox=x={x}:y={y}:w=68:h=68:color=0xB45309@0.9:t=4:enable='between(t,{start:.2f},{end:.2f})'"
        )
    return filters


def build_segments(capture: dict) -> dict:
    seg = WORK / "segments"
    seg.mkdir(exist_ok=True)
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
            "-t",
            f"{OPENING_SECONDS}",
            "-i",
            str(opening_card),
            "-vf",
            f"scale={WIDTH}:{HEIGHT},fps={FPS},fade=t=in:st=0:d=0.3",
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
            "-t",
            f"{END_SECONDS}",
            "-i",
            str(end_card),
            "-vf",
            f"scale={WIDTH}:{HEIGHT},fps={FPS}",
            *common,
            str(end_mp4),
        ]
    )
    parts = [opening_mp4]
    for scene in capture["scenes"]:
        target = seg / f"{scene['name']}.mp4"
        filters = _drawbox_filters(
            scene.get("events") or (), float(scene["duration"]), float(scene.get("skip", 0.0))
        )
        trim_start = scene["lead"] + float(scene.get("skip", 0.0))
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
            "title=TopoMarket - market structure and early warning research",
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
        return value

    cues = []
    index = 1
    for entry in narration:
        spoken = caption_text(entry["text"])
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


def main(argv=None) -> int:
    global WORK, PYTHON
    parser = argparse.ArgumentParser(description="Build the TopoMarket demo video.")
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
    args = parser.parse_args(argv)
    WORK = args.work_dir
    PYTHON = args.playwright_python
    WORK.mkdir(parents=True, exist_ok=True)
    print("1/5 narration...")
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
    else:
        print("2/5 capture...")
        capture = capture_app(args.app_url)
    for scene in capture.get("scenes", ()):
        for event in scene.get("events", ()):
            print("   action", scene["name"], event)
    print("3/5 segments...")
    segments = build_segments(capture)
    print("4/5 audio...")
    audio = build_audio(list(narration.values()))
    print("5/5 mux + captions...")
    master = mux(Path(segments["base"]), audio)
    srt = build_srt(list(narration.values()))
    report = {
        "master": str(master),
        "srt": str(srt),
        "duration_s": duration(master),
        "fps": FPS,
        "width": WIDTH,
        "height": HEIGHT,
        "opening_s": OPENING_SECONDS,
        "app_s": APP_SECONDS,
        "end_s": END_SECONDS,
        "capture": {key: value for key, value in capture.items() if key != "events"},
        "scene_actions": {
            scene["name"]: scene.get("events", []) for scene in capture.get("scenes", ())
        },
        "narration": list(narration.values()),
        "segments": segments,
    }
    (WORK / "build_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("master:", master, "duration", report["duration_s"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
