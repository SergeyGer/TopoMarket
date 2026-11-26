# Narration script (v1.3 film)

Voice: `en-US-GuyNeural`, 48 kHz mono, normalised into the final mix at about -16 LUFS
with a true peak at or below -1.5 dBTP. Silence is trimmed; rate is adjusted per scene
to fit the storyboard window.

| Window | Scene | Narration |
| --- | --- | --- |
| 00:00:00-00:00:06 | Opening card | TopoMarket maps market structure and tests whether topology can warn of sharp declines. |
| 00:00:06-00:00:10 | Two-window comparison | Window A, 29 August 2008: 29 of 66 qualifying pairs. |
| 00:00:10-00:00:16 | Two-window comparison | Window B, 10 October 2008: 66 of 66; 37 added, none removed. |
| 00:00:16-00:00:19 | Two-window comparison label | Retrospective synthetic example. |
| 00:00:19-00:00:21 | Finance selection | Finance has eleven qualifying pairings. |
| 00:00:21-00:00:27 | Mapper groups | Mapper places Finance with Manufacturing and Chemicals; Consumer durables is shared across groups. |
| 00:00:27-00:00:32 | Alert explanation | 10 March 2025: a recorded alert at percentile 100, versus a frozen threshold of 100. |
| 00:00:32-00:00:39 | Alert explanation | The 56-point Takens embedding and the highlighted H1 interval show the shape of recent S&P 500 returns. |
| 00:00:39-00:00:40 | Blind Replay | Blind replay. |
| 00:00:40-00:00:45 | Reveal | Reveal: the index stayed above the 10% boundary; maximum decline, 2.02%. |
| 00:00:45-00:00:49 | Reveal classification | Recorded late alert, included in the evaluation, zero early-warning credit. |
| 00:00:49-00:00:55 | Synthetic holdout results | Three episodes: TDA 0 of 3; VIX 1 of 3. Average precision is low. |
| 00:00:55-00:01:00 | End card | Explore the code and the live demo on GitHub. |

The reviewed SRT in `docs/video/TopoMarket_demo_60s.srt` is the single source for
`docs/watch/captions.vtt`, `docs/watch/transcript.md` and the inline watch-page
transcript; regenerate them with `python scripts/build_watch_assets.py` after an edit.
