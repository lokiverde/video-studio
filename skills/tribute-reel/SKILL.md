---
name: tribute-reel
description: Make a narrated 9:16 tribute or memorial short from the user's own event footage (phone or drone clips), with a cloned or recorded voice-over, a quiet generated music bed, plain white captions, and every face automatically blurred. Solemn style: straight cuts, short dissolves, slow push-ins. Use when the user says "tribute video", "tribute reel", "memorial video", "blur the faces", or hands over a script plus their own clips for a respectful short (a service, a memorial run, a community event). NOT a shirt or product ad (storyboard-reel), NOT a narrated explainer built from generated stills (faceless-video), NOT an on-camera talking-head video.
---

# Tribute Reel

Builds a short from the user's own footage with a narration track. Every cut goes through
the face blur before anything else, and nothing renders until the user approves the preview.

Engine: `python3 scripts/tribute_reel.py <command> <job>`, run from the repo root.
Face pass: `scripts/tribute_blur.py`. On Windows use `python` in place of `python3`.

## Inputs

- Clips: phone or drone video. Portrait, 3:4 phone video and 4K landscape both work (see Framing).
- A script: one voice-over line per beat. Put only names, ranks, dates and numbers you have
  checked from a reliable source on screen.
- Optional: your own recording of a line, saved as `work/vo/line<n>.wav` in the job folder.
  A real recording always beats a generated voice.
- Music: a solemn instrumental. Generate one (ElevenLabs music works) or use your own licensed track.

## Job folder

Make `jobs/<job>/job.json` and put the media under the job folder. There is no `new`
command, so write job.json by hand. Keys the tool reads:

- `clips`: name to relative path, for example `{"hangar": "footage/IMG_0412.MOV"}`.
- `lines`: one voice-over string per line. `voice`: a voice your media server offers.
- `beats`: one per voice-over line, with `line` (its number), `cuts`, `captions`, `lead`,
  `tail`, `min_dur`, and `music_db` (null = hard stop under that beat).
- Each cut: `clip`, `a` (start second in the source), `dur`, optional `fill: true` (takes the
  leftover time), `speed`, `cx` / `cy` (crop centre, 0 to 1, or `cx` keyframes
  `[[t, cx], ...]` to follow a subject), `zoom`, `push`, `faces` (`false` for shots with no
  people), `masks`, `audio_db` (real sound from the clip). The clip name `black` is a plain black frame.
- Captions: `lines`, `at`, `to`, `y`, `size`, `fade_in` (0 = on screen from the first frame).
- `music`: `{"file": "<path>", "offset": <seconds>, "lowpass": <hz>}`.
- Timing and title: `title`, `title_at` (`"start"` or `"end"`), `title_dur`, `max_len`
  (default 45 seconds), `dissolve` (default 0.2), `vo_pause` (default 0.35), `vo_tempo`
  (default 1.0), `vo_db`, `caption_y` (default 0.40).

## Workflow

```
python3 scripts/tribute_reel.py vo <job>      # voice-over from the media server voice (skip if you recorded the lines)
python3 scripts/tribute_reel.py plan <job>    # timeline from the real voice-over lengths, length check
python3 scripts/tribute_reel.py blur <job>    # face pass on every cut, writes work/faces_qa.jpg
python3 scripts/tribute_reel.py sheet <job>   # writes work/contact_sheet_9x16.jpg
```

`vo` also takes `--only <n> ...` (redo some lines) and `--reshape` (keep the takes, redo
pauses and tempo). `vo` overwrites `work/vo/line<n>.wav`, so run it only for lines you have
not recorded yourself. `blur` takes `--jobs <n>` for parallel cuts.

**Review gate (required).** Send the user the contact sheet, the faces QA sheet, the
voice-over lines and the music choice, with the total length. Then END YOUR TURN.
Render only after the user says go. If a cut, mask or line changes after approval, show
the change again before you render.

```
python3 scripts/tribute_reel.py render <job>  # out/final_9x16.mp4, out/final_9x16_clean.mp4, out/voiceover.srt
python3 scripts/tribute_reel.py upload <job>  # sends them to your CDN storage (keys in config.env)
```

The clean cut has no on-screen captions. Write `out/posts.md` (caption, pinned comment)
yourself and paste it in your reply. Keep the copy plain: no emoji, no hype.

## Faces (non-negotiable)

Every cut goes through the face pass before any output is made. The pass finds faces, and
heads from upper-body boxes, with tiling for small faces in crowds. It blurs them and holds
each box for six frames either side, so a missed frame never flashes a face. The blur is
baked into each cut, so every output is blurred.

- **Detection is automatic and imperfect.** On a Mac it uses Apple Vision through a small
  Swift helper that the tool compiles on first run (needs the Xcode command line tools).
  On Windows and Linux it uses OpenCV. Its small face model downloads on first use.
- After `blur`, read `work/faces_qa.jpg` (eight frames per cut). Zoom in on crowds.
- For any face the detector missed, add a manual mask to that cut:
  `"masks": [[x, y, w, h]]` or `[[x, y, w, h, t0, t1]]`. Values are fractions of the 9:16
  frame, and times are seconds into the cut. Then rerun `blur`.
- Shots with no people: `"faces": false`.
- Automatic blur is not a guarantee. At the review gate, check every blurred cut frame
  by frame, not only the QA thumbnails. Small, turned or hidden faces are the usual misses.

## Voice

- `voice` must name a voice your media server offers. A cloned voice needs a clean
  reference recording loaded on that server. Otherwise use a stock voice.
- Keep the script near 60 words for 35 seconds, so `vo_tempo` stays at 1.0. Speeding a
  voice up sounds robotic.
- Use `vo_pause` (0.35 to 0.6 works) to cap long pauses in the clone.
- Optional treatment: `vo_eq`, `vo_pitch` and `vo_db` in job.json. Leave them off unless a
  take needs it.

## Framing and look

- Phone video is 3:4. The tool crops it to 9:16 around `cx`. Wide 4K landscape crops to a
  narrow window, so set `cx` to where the subject is, use keyframes to follow a moving
  subject, and use `zoom` (about 1.3 to 1.6) to fill the frame with people.
- Hook: put a caption on screen from the first frame (`fade_in: 0`).
- Keep captions in the sky band (`caption_y` about 0.22) so they sit off people's heads.
- Captions are facts, not subtitles: white, bold sans-serif, soft shadow, kept out of the
  bottom fifth and the right edge.
- The grade is slightly desaturated and warm, built in.
- **Story over black:** a `black` cut with voice-over and white text tells a hard part
  without footage. A beat with `"line": null` and a `min_dur` is a moment with no voice.
  Let it carry real sound on a cut with `audio_db`, and set `music_db: null`.
- Music: set the level per beat with `music_db`. Generated music often ignores your timing,
  so check its loudness per second and set `music.offset` to skip leading silence.
- `plan` warns if the total runs past `max_len`. Trim leads and tails, or tighten the voice.

## Gotchas

- Media server unreachable: check the network path to it (a VPN or tailnet that has
  stopped is the usual cause), then rerun.
- The font path in the script points to a macOS font. On Windows or Linux, point it at an
  installed bold sans-serif font before you render captions.
- Names, ranks and numbers on screen come only from your checked source.
