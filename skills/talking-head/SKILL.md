---
name: talking-head
description: Turn a recording of you talking to camera into a finished video with source cards, stat graphics, captions, cleaned audio, music, Shorts and thumbnails, delivered as 16:9 and 9:16. Use when the user says "talking head", "talking head video", "wrap my video", "put a wrapper on this video", "studio style", "news desk", "board style", "list video", "army style", or "split layout", or gives a path to footage of themselves talking plus an outline or sources. NOT faceless-video: here the user is on screen and their own recorded audio is the narration.
---

# Talking Head

Sibling of `faceless-video`. Same folder, same jobs folder, same approval gate.
Run commands from the video studio folder (the one with `scripts/`): `python3 scripts/th.py ...`
on Mac and Linux, `python scripts/th.py ...` on Windows. Each video is a job folder,
`jobs/YYYYMMDD-HHMMSS-<word>/`. The Remotion template lives in `talking-head/` (run `npm install`
there once). ffmpeg and ffprobe must be on the PATH.

## The three gates (nothing skips them)

1. **Preview gate.** Nothing renders until the user has seen the contact sheets and said go.
   `th.py render` refuses without an approval. Changing `job.json` or the b-roll after approval
   voids it, so the user sees a fresh sheet first.
2. **Audio gate.** Every final runs audio QC (level, true peak, loudness range, quiet stretches).
   Fix failures with `th.py level`. Do not upload a final that fails.
3. **Spending gate.** Free media is the default. Paid AI video runs only on the user's go for a priced list.

## What it makes

Layouts alternate: full frame on the speaker for the hook and each question; an evidence layout
(a framed card, with one source at a time in a panel beside it) while the speaker makes a claim;
and full-screen b-roll, used sparingly. Output: 16:9 and 9:16 finals, Shorts, thumbnails and a YouTube kit.

## Styles

Set `"style"` in `job.json`. The pipeline and gates are the same for all five.

- **evidence** (default): white canvas, framed card, source documents with highlights, running
  captions. Best for law, statutes, "here is the proof".
- **studio**: a gradient canvas per section (`theme`: light, blush, lime, periwinkle, dark, crimson,
  midnight), the card swaps sides (`side`), kinetic `phrases` in 16:9, big stats, numbered lists that
  build a line at a time. Best for frameworks. Proper names keep their capitals in lowercase styles.
- **news**: the speaker stays full frame. Movement comes from `typed` lines (max 12 words, 2 lines,
  `hl` colors key words), `stickers` (transparent PNGs from `th_sticker.py`), framed `cutaways`
  (`"fit": "blur"` for portrait photos), `pullquote` cards and `chapters`. Best for a story with a
  timeline. Photos must be yours, official, public domain, screenshots of the real document, or generic
  generated scenes. Never a generated picture of a real person.
- **board**: speaker full frame, a recurring full-screen `board` that lights the current list item,
  real comment screenshots as `receipt` blocks (names blurred), key-word captions, sound effects. Best
  for countdowns. `"layout": "split"` on a beat gives a quiz-style look: speaker on the right third,
  graphics in a light card that pans, a big number wipe before each item.
- **army**: a split-panel graphics style. The speaker sits in a framed panel beside graphics that pan and
  wipe on a dark textured canvas. No sections: `beats` [{from, to, layout}] in source seconds. Layouts:
  `split` (a `graphic`, a screen recording `clip`, or an article `shot`), `full`, `inset` (speaker shrinks
  to a box while a punch line rises) and `graphic` (full screen while audio plays). Set `brand` colors.

Studio blocks (`headline`, `bigstat`, `steps`, `bars`, `screen`) work in any style.

## Inputs

- **Footage.** One continuous take is fine. Several takes: see below.
- **Outline or script**, ideally with a source per point. Write evidence first: claim, source, number,
  takeaway. Write in the user's voice: no em dashes, no stock phrases.

## Workflow

### 1. Create the job
```
python3 scripts/th.py new <video> --title "..." --word <word>
```
`--word` is ONE word for the folder name: the city or topic. `new` makes a 1440p working copy (the original
is untouched), transcribes locally, prints the transcript with timestamps, suggests cuts at long silences and
lists low-confidence words. Verify every flagged number, year and statute by ear: speech-to-text can turn
"three years" into "30 years".

Transcription: Parakeet (`~/video-studio/.venv-parakeet`) on Apple Silicon Macs, mlx-whisper in
`~/video-studio/.venv-whisper` as fallback. On Windows, Linux and Intel Macs, faster-whisper in
`~/video-studio/.venv-faster-whisper` (or the main Python). The output is the same.

**Several takes?** `th.py takes plan <script.md> <main.mp4> <other.mp4> ... --out <dir>` picks the best attempt of
each section. Read the plan, then `th.py takes splice <dir>` writes `master.mp4`. Run `new` on it.

### 1b. Voice cleanup (every job, right after `new`)
```
python3 scripts/th.py enhance <job>
```
Runs the local AI voice (Resemble Enhance in `~/video-studio/.venv-enhance` with `studio/enhance_voice.py`):
denoise, treble rebuild, -14 LUFS. It is CPU work, slower than real time, so run it in the background on long
footage. Without the enhancer it falls back to the `studio` EQ preset. Also: `--voice clean|broadcast|studio`,
`--undo`, and `--export` then `--adobe <wav>` for Adobe Podcast Enhance by hand.
Already rendered? `th.py revoice <job> --ai` swaps the voice into both finals.

**Room or class recordings: `--room`, never the AI voice.** The AI voice is generative, so off-mic speakers
come out as confident wrong words. `th.py enhance <job> --room` (before render) or `th.py revoice <job> --room`
(after) denoises the whole track without inventing words. Never splice raw audio into the AI track.

### 2. Cuts
Suggested cuts are hints. Merge a stray "okay" in dead air into one cut. Set `srcEnd` about one second after
the last word; the end card handles the landing.

### 3. Evidence
Fetch the real source for each claim and quote it exactly. Panels are rendered text, not screenshots, so
highlights stay sharp. Trim with "..." but never reword a quote. Check every name, number and code section.

### 4. Write `jobs/<job>/job.json`
All times are SOURCE seconds. Find them with `th.py find <job> "phrase"`.
```
title, source ("footage.mp4"), srcEnd, cuts [[from,to],...]
captionFixes [["misheard phrase","correct text"],...]
hook        {from,to, broll:[files in public/], kicker, title}
lowerThird  {from,to, name, line}, or a list of them
youtube     {title, description, tags[], hashtags[], intro_chapter}
counter     {from,to, count}          numbered dots for "these five questions"
disclaimer  {from, text}
endCard     {seconds, kicker, headline, sub}
brand       color overrides: navy ink paper amber red yellow green mute
framing     {full, card, portraitFull, portraitCard}: each {x, y, zoom}
cutaways    [{from,to,file}]          full-screen b-roll over the audio
sections    [{ tag:{n,topic,from,to}, evidence:[from,to], blocks:[...], chapter? }]
beats       army style only
```
Blocks (2 to 3 per section): `statute` {cite, heading, parts:[text or {hl, at}]}, `quote` {text, at, xAt?},
`stat` {label, value, at}, `strike` {value, note, at, noteAt}, `list` {items:[{name, who, at}]},
`bar` {label, at, dangerAt, noteAt, note}, `formula` {terms, caption, at}, `traffic` {items:[{color, title, body, at}]},
`cta` {kicker, headline, at}, `note` {text, at, color?}.

`tag` runs while the speaker asks the question; `evidence` opens when the answer starts. Put `at` on the first
word of the phrase, aim for a cue every 2 to 5 seconds, and keep every cue inside its window and outside every cut.

Run `python3 scripts/th.py check <job>` after every edit. It enforces windows and cuts and prints a `PACING`
warning for any stretch over 7 seconds with no change. Fix each one: add a cue inside an evidence window, or on
a full-frame speaker add a 3 to 5 second `cutaway` on the phrase it illustrates (never on a question tag, never
overlapping a cut or another cutaway).

### B-roll: free by default, paid only on the user's go
`hook.broll` and `cutaways` take stills or clips from `jobs/<job>/public/`.
- **Free:** 3 to 6 stills from the media server (`TIM_MEDIA_URL` in `config.env`, see `tim/service.py`), or your
  own photos. Ask for photoreal images with no text.
- **Paid video, only on the user's go:** (1) list each shot with where it goes, seconds and a prompt; (2) price the
  exact model and settings and check the balance; (3) show the list and the TOTAL, then STOP; (4) generate only
  after a clear go for that list. Image-to-video from an approved still works best. Prompt motion only: generated
  video garbles people talking and readable text.

### Framing (before the sheet)
Pull 3 frames from `public/footage.mp4`. `x`, `y` are the focal point (fraction of the frame), `zoom` scales around it.
A centered webcam needs no `framing`. A wide camera angled up: zoom 1.0 to 1.15, y about 0.55 to 0.62. Check both cuts.
`punch: false` turns off the punch-ins at cuts; `punchZoom` (1.15) and `punches` tune them.

### 5. Contact sheets, then STOP for the user (hard gate)
```
python3 scripts/th.py sheet <job>
```
Writes `work/contact_sheet.jpg` (16:9) and `work/contact_sheet_9x16.jpg`, and runs caption QC. Read both yourself
and fix what you see: overflow, highlights on the wrong words, caption fixes not applied, framing, anything under the
9:16 platform UI zones. Then send the user BOTH sheets and the caption QC result, and end your turn. Do not start a
render while they look.

**Caption QC** (also alone: `th.py capqc <job>`) flags captions over the mouth or chin (Apple Vision on a Mac;
elsewhere check by eye) and captions under 3:1 contrast. Flagged frames go to `work/capqc_<cut>/`.

On change requests: edit `job.json`, run `sheet` again, send the new sheets, and wait. On the user's go:
`python3 scripts/th.py approve <job>`, then render. `approve` refuses a sheet older than the job.
`--no-preview` skips the gate, only on the user's explicit waiver for that job.

### 6. Render and QC
```
python3 scripts/th.py render <job> [--only 16x9|9x16]
```
Blocked until approved. Writes `out/final_16x9.mp4` and `out/final_9x16.mp4` (about 4 minutes each for a 2.5 minute
video). For long renders: `python3 scripts/bg_run.py --name <label> -- python3 scripts/th.py render <job>`. Render QC
catches black frames, silence over 2 s outside the end card, and audio drift.

Then check each final with ffprobe and pull 4 to 6 frames around the cuts and the end card.
- **Word check** runs automatically (or `th.py words <job>`). It lists `LISTEN at these times` for words lost at a cut,
  stutters and swapped words. It is not a gate: listen to each time before you report.
- **Audio QC** runs automatically (or `python3 scripts/audio_qc.py out/final_16x9.mp4 --target -14`). It checks level
  within 1 LU of target, true peak under -1 dBTP, loudness range under 8 LU, and 10 s stretches of speech 6 LU under
  the typical level. It is a gate.
- **Fix quiet stretches without re-rendering:** `python3 scripts/th.py level <job> [--switch S]`. It lifts speech more
  than 3 dB under the typical level, re-applies -14 LUFS and re-mixes music. Old finals are kept as `work/final_*_prevoice.mp4`.
  Then re-cut the Shorts.

### 6b. Music and sound effects (optional, after render)
```
python3 scripts/th.py music <job> <track> [--level -30] [--hook-track <track>] [--switch S] [--no-sfx]
```
Loops a bed from `assets/music/`, ducked under the voice, into `out/final_16x9_music.mp4` and `final_9x16_music.mp4`.
The video is copied, so this takes seconds with no re-render. `--level` is bed loudness in LUFS (-30 default).
`--hook-track` plays a second track under the hook and crosses into the bed at `--switch` (army jobs need `--switch`).
Sound effects from `assets/sfx/` mix in per cue; `--no-sfx` leaves them out. Use only tracks you made or licensed.

### 6c. Shorts and thumbnails (after every render)
**Shorts.** Pick 2 to 3 self-contained sections of 20 to 55 seconds, each opening on a claim. Start and end are spoken
phrases matched to the captions:
```
"shorts": [{"start": "Under state law, a no-fault move-out", "end": "belongs in your offer",
            "hook": "$2,500 RENT, $10,500 TO LEAVE", "title": "...",
            "description": "Two or three sentences in the user's voice."}]
```
- An `opener` is a payoff first frame (about 1.2 s): `{"type": "number", "text": "...", "sub": "..."}`, or `photo`,
  `broll`, `archive`, `receipt`, `prop`, `location`. Rotate types so two Shorts in a row never open the same way.
- Start mid-thought (not on "so", "okay", "and" or "um"). Hooks run 2 to 6 words. Banners: default, red, orange,
  green, none (`shorts_banner` per job, `banner` per Short). Title and description edits do not void approval.

```
python3 scripts/th_shorts.py sheet <job>    # work/shorts_sheet.jpg: hook frame and last frame
python3 scripts/th_shorts.py approve <job>  # after the user's go
python3 scripts/th_shorts.py cut <job>      # out/short_<n>.mp4, short_<n>_cover.jpg, shorts.md
```
Title or description edits later: `python3 scripts/th_shorts.py kit <job>` (no re-cut).
Fix every `FIRST FRAME:` warning. `sheet` and `cut` warn past about 70 to 95 s, where some upload tools' file limits
bite. The cover still is the custom Shorts thumbnail.

**Thumbnails.** Add a `thumbnail` block, then `python3 scripts/yt_thumb.py --job <job>`. It writes `out/thumb_variants/`:
A (with face), B (A without the face, one variable changed), C (plain), `phone_sizes.jpg`, and copies A to
`out/thumbnail.jpg`. Read `phone_sizes.jpg` (a word that turns to mush at 168 px gets cut).
```
"thumbnail": {"lines": ["WORD ONE", "WORD TWO"], "accent": 1, "mark": "YOUR MARK",
              "bg": "work/thumb_bg.jpg", "face": 2.6, "face_height": 660, "text_y": 40,
              "layers": [{"type": "stamp", "text": "EVIDENCE", "x": 250, "y": 470}],
              "plain": {"lines": ["PLAIN", "VERSION"]}}
```
- `face`: seconds into `public/footage.mp4`, or a PNG. On a Mac, Apple Vision cuts the head out with a white outline and
  shadow; elsewhere the face becomes a framed portrait card. Check the cutout edges.
- `"style": "alert"` makes a dark headline bar for an official warning, using only the source's exact wording.
  Never add a network or agency label the source does not carry.
- Words: 3 to 4 at most, words that ADD to the title. Face: closed mouth, eyes on the lens. Test A, B and C if your platform allows.

### 7. Publish kit (every video)
Everything to publish lives in `jobs/<job>/out/`. Render and `th.py kit` write `transcript.txt`, `transcript.srt` and
`youtube.md`. Always author the `youtube` block: title under 60 characters, a 3 to 5 sentence description, 12 to 15
lowercase tags (at least 5 plain-English search phrases), up to 3 hashtags. Title shape: `[what changed]. [the question
the viewer already asks]`. Keep bill numbers and acronyms out of the title and thumbnail; put them in the description.

In the same turn as the finals, also write `out/script.md`, `out/blog.md` (a companion article with sourced figures) and
`out/linkedin.md` (no URLs in the body, ending with a `## First comment` section). After publishing,
`python3 scripts/fv.py links <job> --youtube <id> --blog <url>` fills the comment, and `fv.py bloglink <job> <url>` adds the
article link to the YouTube text and every Short. `out/route.md` gives the length call: under 120 s a Short, 120 to 180 s
the user's call, over 180 s long-form.

Optional: `python3 scripts/fv.py publish <job> --youtube <id>` shows a Blotato go table (the user's own accounts).
`--go` posts it, only on the user's go.

## Filming tips to give the user
- Center the face with some headroom. Turn OFF webcam background blur. Audio matters more than picture.
- One take. Pause a beat between sections and keep going after a flub. Dead air is cut.
- End every take with a 10 second silent pose into the lens. Its second is the `face` value.

## Troubleshooting
- `check` says a cue is outside its window: widen `evidence` or move `at`. A highlight fires early or late: change that `at`, re-run `sheet`.
- A caption is wrong: add a `captionFixes` pair, written against the glued form of split tokens ("1120-8").
- Captions over the mouth or chin: move `framing`, or use a `phrases` line.
- A render times out: the computer probably slept. Keep it awake and on power during renders.
- Template type errors: `cd talking-head && npx tsc --noEmit -p .` must be clean. Missing modules: `npm install` there.
