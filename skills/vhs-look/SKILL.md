---
name: vhs-look
description: Put a VHS tape overlay on a finished vertical product ad (scanlines, RGB split, color bleed, grain, vignette, flicker, a rolling tracking band, head-switch tearing and a PLAY readout) at 50% by default, with the product reveal kept clean. Use when the user says "vhs overlay", "VHS look", "add the VHS look", "retro overlay", "tape look", or names a strength ("VHS at 30%") on a finished ad. NOT for real estate listing videos or talking-head footage.
---

# VHS Look Overlay

Tapes a finished 9:16 product ad. The recipe lives in `scripts/sr_vhs.py` (`VHSPass`), and
`scripts/vhs_look.py` drives it over a file. Run from the video studio folder: `python3 scripts/vhs_look.py ...`
(use `python` on Windows).

## Defaults and rules

- **Strength 0.5** unless the user names one. Users often say percent: "30%" means `--strength 0.3`.
  0 is off, 1 is full.
- **The product comes back clean.** The overlay runs at full strength over the world and characters,
  then eases out over `--fade` seconds (0.7 by default), ending exactly at `--clean-from`. The product
  reveal and the product card never carry it.
- **PLAY readout** top left over the opening (first 4.2 s). `--osd ""` turns it off. `--osd-end` sets how long it shows.
- **Audio is copied untouched**, so the loudness the source was mastered to is kept.
- The encode is capped at 14 Mbps, because grain alone would push about 35 Mbps. A 28 second reel lands near 40 MB.

## Run

```bash
python3 scripts/vhs_look.py jobs/<job>/out/final_9x16.mp4 jobs/<job>/out/final_9x16_vhs.mp4 --clean-from <seconds>
```
Optional flags: `--strength 0.5`, `--fade 0.7`, `--osd "PLAY ▶"`, `--osd-end 4.2`, `--duration N` (first N seconds only, for tests).

- `--clean-from` is the second the clean product reveal begins (the blank shirt or the product's first frame).
  If unsure, pull a frame every 0.5 s across the back half with ffmpeg and look at each one.
- Test first: run a 6 second slice with `--duration 6` and try the strength on it before the full file.
- It is slow, about 12 seconds of work per second of video on a Mac. Run it in the background:
  `python3 scripts/bg_run.py --name vhs -- python3 scripts/vhs_look.py <in> <out> --clean-from <s>`.

## Gate and delivery

1. Send the user the `_vhs` file (or the slice) and wait for a go. Do not upload before that.
2. Save the taped version as a NEW file beside the clean final, for example `final_9x16_vhs.mp4`. Never
   overwrite the clean final. When you upload, use a new file name too: many CDNs keep serving the old file
   under a reused path. Check the size after upload.
3. If the post needs a new cover, export a frame from the `_vhs` file.

## Troubleshooting

- The overlay is still on the product: `--clean-from` is too late. Move it earlier and re-run.
- The overlay drops off abruptly: the fade is `--fade`. A longer fade still has to end at `--clean-from`.
- The readout covers something: shorten it with `--osd-end`, or turn it off with `--osd ""`.
- Too slow or too big: run it in the background. The 14 Mbps cap is deliberate, so do not raise it for the file size.
