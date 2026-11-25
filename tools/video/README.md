# Demo video production toolchain

Scripted production of the TopoMarket one-minute demo video: a headless capture of the
released Streamlit app, English narration generated locally with edge-tts, an H.264/AAC master
assembled with ffmpeg, and reviewed English SRT captions.

The released output, production notes, storyline and captions live in
[`docs/video/`](../../docs/video/). The video is published as a GitHub release asset and
linked from the README.

## Prerequisites

- Project `.venv` with the `[ui]` extra (Streamlit + matplotlib) and a built synthetic showcase.
- An isolated Python environment with Playwright + Chromium and edge-tts:
  ```bash
  python3 -m venv /tmp/tm-video/venv
  /tmp/tm-video/venv/bin/pip install --upgrade pip
  /tmp/tm-video/venv/bin/pip install playwright edge-tts
  /tmp/tm-video/venv/bin/playwright install chromium --with-deps
  ```
- `ffmpeg`/`ffprobe` with libx264 and AAC (for example `apt-get install -y ffmpeg`).

## Build

```bash
# record from a local app server started by the script (default)
/tmp/tm-video/venv/bin/python tools/video/build_demo_video.py

# record from the hosted Streamlit Community Cloud app once it is publicly viewable
/tmp/tm-video/venv/bin/python tools/video/build_demo_video.py \
  --app-url https://topomarket-juhbvrgk2k67pnr6qbpfmc.streamlit.app/
```

Outputs in `/tmp/tm-build/work` (or `--work-dir`):

- `TopoMarket_demo_60s.mp4` - 1920x1080, 30 fps, H.264 High, AAC 48 kHz stereo, 60 s;
- `TopoMarket_demo_60s.srt` - English captions;
- `narration.wav` - loudness-normalised narration master;
- `record/` - source webm recordings per scene;
- `build_report.json` / `capture.json` - timings, actions, hashes and technical measurements.

## How it works

1. **Narration** - each storyboard line is synthesised with `en-US-GuyNeural` at a rate that
   fits its scene window (the opening line uses `+15%`), converted to 48 kHz mono WAV and
   placed on a 60 s timeline with `adelay`; a two-pass `loudnorm` normalises the mix to about
   -16 LUFS with a true peak below -1 dBTP.
2. **Capture** - the app is recorded per scene in a fresh 1920x1080 Chromium context with the
   Streamlit toolbar hidden. Scene actions are scripted (preset clicks, industry selection,
   Mapper view/edge highlight, alert jump, blind Replay -> Reveal, Validation). Only the released
   synthetic showcase is used.
3. **Assembly** - each scene is trimmed to its storyboard window, click locations are highlighted
   with a short amber marker, scenes are concatenated with the 16:9 opening/end cards, and the
   narration is muxed into the final master.

The scene plan, narration text and timings are edited in
[`docs/video/storyboard.json`](../../docs/video/storyboard.json) and
[`docs/video/narration.md`](../../docs/video/narration.md).

## Known limitations

- Playwright records at 25 fps; the deliverable is frame-converted to 30 fps.
- The headless browser does not capture a mouse cursor; click locations are highlighted in
  post-production.
- Re-records are live captures, so a few frames can differ run to run.
