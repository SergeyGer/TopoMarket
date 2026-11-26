#!/usr/bin/env python3
"""Regenerate the browser-player captions, Markdown transcript and inline transcript.

The reviewed film SRT in ``docs/video/`` is the single source of narration text and
timings (audit v1.2.0 remediation).  Run after the final film cut/SRT is frozen:

    python scripts/build_watch_assets.py
"""

from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRT = ROOT / "docs" / "video" / "TopoMarket_demo_60s.srt"
WATCH = ROOT / "docs" / "watch"
VTT = WATCH / "captions.vtt"
TRANSCRIPT = WATCH / "transcript.md"
INDEX = WATCH / "index.html"

SCENES = {
    0: "Opening card",
    1: "Two-window comparison",
    2: "Two-window comparison",
    3: "Two-window comparison",
    4: "Finance selection",
    5: "Mapper",
    6: "Alert explanation",
    7: "Alert explanation",
    8: "Blind Replay",
    9: "Reveal",
    10: "Late alert",
    11: "Results",
    12: "End card",
}


def parse_srt(text: str) -> list[dict[str, str]]:
    cues: list[dict[str, str]] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line for line in block.splitlines() if line.strip()]
        if len(lines) < 3:
            continue
        times = lines[1]
        match = re.match(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", times)
        if not match:
            continue
        cues.append(
            {
                "start": match.group(1).replace(",", "."),
                "end": match.group(2).replace(",", "."),
                "text": " ".join(lines[2:]),
                "scene": SCENES.get(len(cues), "Film"),
            }
        )
    return cues


def build_vtt(cues: list[dict[str, str]]) -> str:
    blocks = ["WEBVTT", ""]
    for cue in cues:
        blocks.extend(
            [
                f"{cue['start']} --> {cue['end']}",
                html.escape(cue["text"], quote=False),
                "",
            ]
        )
    return "\n".join(blocks).rstrip() + "\n"


def build_transcript(cues: list[dict[str, str]]) -> str:
    lines = [
        "# TopoMarket 60-second film — transcript",
        "",
        "English narration for the 60-second TopoMarket film. The footage and figures use the",
        "committed synthetic showcase only; genuine market data is not published.",
        "",
        "- Watch page: [index.html](index.html)",
        "- Captions used by the player: [captions.vtt](captions.vtt) "
        "(generated from the reviewed SRT)",
        "- Reviewed source: [docs/video/TopoMarket_demo_60s.srt](../video/TopoMarket_demo_60s.srt)",
        "- Scene boundaries: [docs/video/storyboard.json](../video/storyboard.json)",
        "",
        "## Caption cues",
        "",
        "| # | In | Out | Scene | Narration |",
        "| --- | --- | --- | --- | --- |",
    ]
    for index, cue in enumerate(cues, start=1):
        narration = cue["text"].replace("|", "\\|")
        lines.append(f"| {index} | {cue['start']} | {cue['end']} | {cue['scene']} | {narration} |")
    lines.extend(
        [
            "",
            "The timings match the reviewed 60-second cut; regenerate this file and the "
            "WebVTT track",
            "with `python scripts/build_watch_assets.py` after any film edit.",
            "",
        ]
    )
    return "\n".join(lines)


def rebuild_inline(cues: list[dict[str, str]]) -> str:
    rows = []
    for cue in cues:
        text = html.escape(cue["text"], quote=False)
        start_end = f"{cue['start']}&ndash;{cue['end']}"
        rows.append(
            f'          <tr><td class="time">{start_end}</td>'
            f'<td class="scene">{cue["scene"]}</td><td>{text}</td></tr>'
        )
    return "\n".join(rows)


def main() -> int:
    cues = parse_srt(SRT.read_text(encoding="utf-8"))
    if not cues:
        raise SystemExit(f"no cues parsed from {SRT}")
    VTT.write_text(build_vtt(cues), encoding="utf-8")
    TRANSCRIPT.write_text(build_transcript(cues), encoding="utf-8")
    index = INDEX.read_text(encoding="utf-8")
    pattern = re.compile(r"(<tbody>\n)(.*?)(\n        </tbody>)", re.DOTALL)
    replacement = r"\1" + rebuild_inline(cues) + r"\3"
    if not pattern.search(index):
        raise SystemExit("inline transcript tbody not found in docs/watch/index.html")
    INDEX.write_text(pattern.sub(replacement, index, count=1), encoding="utf-8")
    print(f"regenerated {VTT.name}, {TRANSCRIPT.name} and inline transcript ({len(cues)} cues)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
