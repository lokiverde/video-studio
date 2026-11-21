---
name: montage
use: "Several hard-cut shots inside one generation, each about 1.5 seconds, one action per shot."
---

# Multi-shot montage

One generation, several hard cuts. Example shape: seven shots of about 1.5 seconds in a
10-second clip. Write one SHOT line per shot with its time range; no shot under 1.0 second.

```text
GOAL: [N] hard-cut shots, about [t] seconds each, [total] seconds total. [Genre energy in a few words]. Filmed badly by bystanders on [devices].
CAST: [Each named recurring character with fixed wardrobe, one line each.] [Any fixed prop or vehicle.]
RHYTHM: One action per shot, from its start to its impact, then a hard cut. No build-up, no aftermath, no shot longer than its range.
SHOT 1 | 0-[t]s: [location], [who], [action]. HARD CUT.
SHOT 2 | [t]-[2t]s: [location], [who], [action]. HARD CUT.
SHOT [N] | [start]-[total]s: [location], [who], [action]. END.
LOOK: [device mix], [imperfection list]. [Lens behavior.]
CAMERA: [Camera behavior per shot, for example "SHOT 2 whip pan, SHOT 5 frame block".]
AUDIO: Raw device-microphone sound in every shot, cut at every hard cut. Wordless reactions only. No dialogue. No music.
EXCLUSIONS: Clean full frame: no overlay, timestamp, REC indicator, battery icon, focus box, grid, border or subtitles. No on-screen interface, text, watermark, logos or brand names. No real people. No injuries shown. No weapons. No real money.
CONTINUITY: Same characters and wardrobe in every shot. Exactly one action per shot. The same raw look across all shots.
```

Rules:
- Timestamp every shot. Ranges add up to the total.
- One action per shot. The cut lands on the impact, not after it.
- Freeze each recurring character's wardrobe in the CAST block and do not restate it
  differently in a SHOT line.
- No logos, brand names or readable text, unless Tony approves readable text for that shot
  (then take "text" out of EXCLUSIONS for it). No real money or injuries. No weapons in
  photoreal footage; a stylized game or cartoon weapon is fine (take "No weapons." out of
  EXCLUSIONS for it).
- Animals keep animal faces; nobody is sexualized.
- Draft first at 480p, like any clip.
