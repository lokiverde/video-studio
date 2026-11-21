---
name: surf-reel
description: Make a beat-synced 9:16 product ad cut from your own action footage (surf, skate or any sport) to a punk or surf-rock track. A calm discovery intro, the band drops on the product reveal, beat-matched punch-ins, shakes and caption slams, and a product card on the final drum hit. Use when the user says "surfer video", "surf product ad", "skate product ad", "beat-synced product ad", or gives their own action footage plus a product page for a short shirt or merch ad. NOT archive-reel (public-domain silent film) and NOT faceless-video (narrated explainer).
---

# Surfer product ad

Sibling of `faceless-video`, `talking-head` and `archive-reel`, same folder, same jobs folder.
Run commands from the Video Studio folder with `python3 scripts/surfer_reel.py ...`
(on Windows, type `python` instead of `python3`). The look lives in
`skills/surf-reel/style.json`: set `card_url`, and set `font` to a bold font file on your machine.
Needs `ffmpeg` and `ffprobe` on PATH, plus numpy and opencv for the beat and face steps.

## What it makes

A 9:16 video of 25 to 30 seconds, no narration, no added sound effects. The music carries it.
Two cuts per render: one with the music, and a silent twin of the same picture so the user can
add a trending sound in the app.

## The formula

1. **Discovery intro (about 6.5 s, 2 to 3 cuts).** Muted, desaturated grade, slow drift,
   captions fade in. Short deadpan lines ("Low tide.", "Peel it back."). Approach shots run at
   2x. The music is a quiet guitar lead-in.
2. **The drop lands on the reveal.** `music_offset` trims the track so the band kicks in on the
   first frame of the product reveal. That cut gets `"flash": true`: white flash, big punch-in,
   shake, caption slam.
3. **Wearer section, on the beat.** Every cut is a whole number of beats (0.4 s at 150 BPM, so
   1.2 to 2.4 s each). Each cut punches in, shakes, pulses on every beat and whips into the next
   with horizontal blur. Captions slam in: one word or two to four words, heavy sans-serif, white
   with a thick black stroke. Mix the shots: back print wide, sleeve detail, chest close-up, a 2x
   walk-around, and a 0.75x slow-motion closer. Flash on the 2 or 3 strongest beats only.
4. **Product card on the final hit.** Title, product image, price, sizes, colour count and the
   URL. It slams in, pulses, and flashes again on the song's last drum hit (`card.final_hit`).
   The music rings out and fades.

## Inputs

- **Action footage:** one or more clips, shot on a phone or action camera. Vertical footage works
  best. A clip can be cropped to 9:16 with a clip alias: `{"path": "...", "crop": [x, y, w, h]}`
  (fractions of the frame, with w = h).
- **Product photo:** a clean front shot.
- **Product page URL (optional):** a Shopify-style page fills the title, price, sizes and colour
  count. Anything else: type them into the `card` block by hand.
- **Music bed:** 30 to 35 seconds at about 150 BPM. The kit's default bed is
  `assets/music/surf-reel-tide.mp3`. For a new look, see Music.

## Music

For a new theme, generate a 32-second instrumental with any music tool (ElevenLabs music works
with `instrumental` on). Prompt pattern: a single guitar sting or quiet lead-in, the full band
drops hard about 6 seconds in, a hard stop at the end, and the BPM. Save it as
`assets/music/<slug>.mp3` and run `beats` on it.

## Workflow

1. **New job.** Creates the job folder, one footage sheet per clip, and the card fields.
   ```bash
   python3 scripts/surfer_reel.py new --clips A.MP4 B.MP4 --product shirt.jpg --url https://your-store.example/products/<slug>
   ```
   Each sheet is `work/footage_<a|b>.jpg`: one frame per second, left to right, row by row. Read
   the sheets to find the discovery beats, the reveal, the back print, the sleeves and the front.
2. **Beat grid.** `python3 scripts/surfer_reel.py beats <music>` prints `music_offset`, the drop,
   the final hit and the beats between them. Add `--bpm <n>` if the track is not 150 BPM.
3. **Cuts.** Edit `jobs/<job>/job.json`. Rename the clips under `clips` to something readable
   (`find`, `wear`). A cut looks like this:
   ```json
   {"clip": "find", "a": 21.0, "b": 24.2, "speed": 1.0, "cap": "Low tide.", "mode": "hit", "flash": true}
   ```
   - `"mode": "intro"` cuts must add up to the drop time from `beats`.
   - `"mode": "hit"` cuts must each be a whole number of beats: `(b - a) / speed`.
   - Set `music_offset` and `card.final_hit` (final hit time in the video, minus the card's start).
     Size the hit section so the card starts about 3.2 s before the final hit.
4. **Check.** `python3 scripts/surfer_reel.py check <job>` validates the beat grid, the clip names,
   the product image and `final_hit`. Fix every PROBLEM line.
5. **Sheet.** `python3 scripts/surfer_reel.py sheet <job>` writes `work/contact_sheet_9x16.jpg`,
   one graded frame per cut with its caption, plus the end card. Look at it yourself first.
6. **Preview gate.** Send the user the contact sheet and the music. END YOUR TURN. Render only
   after they say go. Any later change to the cuts needs a new sheet and a new go.
7. **Render.** `python3 scripts/surfer_reel.py render <job>` (about 9 minutes). It writes
   `out/final_9x16.mp4` (music) and `out/final_9x16_nomusic.mp4` (silent), plus `_social` copies
   sized for posting. The masters are the archive copies, and some platforms reject them for size.
8. **Upload (optional).** `python3 scripts/surfer_reel.py upload <job>` sends the social copies,
   the masters and `posts.md` to your CDN. It needs the CDN keys in `config.env`. Skip it to keep
   files local.
9. **Post copy.** Write `out/posts.md` with a section each for Instagram Reels, TikTok, YouTube
   Shorts (title and description) and Facebook Reels: a deadpan hook, one follow-up line, price,
   sizes, colours and the URL, a pinned comment that asks a real question, and a few hashtags.
   Say which cut to post on each platform. Plain captions, no emoji.

## Options

- **Stills as shots:** a clip can be a photo, `{"path": "photo.png", "crop": [x, y, w, h]}`. It is
  held and drifted; `a` and `b` are 0 and the duration.
- **Variants:** save `job.<name>.json` and render with `--variant <name>` (for example, a shorter
  paid cut). `--clean` drops the captions and writes `*_clean.mp4`. `stills <job> --at t1 t2 t3`
  pulls frames for a carousel (add `--clean` for no captions).
- **Clip sound:** `"audio": 1.0` keeps the clip's own sound under the music at that level.
- **Blur a region:** `"masks": [[x, y, w, h]]` on a cut adds a feathered blur for the whole cut.
- **Face cover:** `scripts/sr_skull.py` draws a graphic over every visible face. Set the skull block's
  `image` to a transparent PNG of your own. Run `track`, then `check` (it writes
  `work/skull_check.jpg`, with frames from every cut), then `apply`, all with `<job>`. Pose tracking
  uses Apple Vision on a Mac (`bin/bodytrack`). On Windows or Linux it uses MediaPipe
  (`pip install mediapipe`). Read every `skull_check.jpg` frame: the tracker can find faces in
  prints and miss a face in profile.
- **Waist slim:** `"slim": [{"clip": "wear", "a": 33.2, "b": 35.0, "amount": 0.12}]` in job.json.
  Run `sr_skull.py apply <job>` after it.

## Craft rules

- Shoot the action yourself, or use footage you have rights to. Real hands and real places are
  the look. Do not add generated people unless the user asks.
- Keep captions short. They shrink to fit, but short reads better.
- Check prices, sizes and colours against the live product page, never from memory.
- Every visible face gets the cover, or the cut is trimmed past it. Check every cut that shows
  other people, not only the middle frame.
- A face that shows for a moment reads as a flicker. Trim the cut past the turn and keep the length
  a whole number of beats.

## Troubleshooting

- `check` says a hit cut is off the beat: change `b` or `speed` so the length is a whole number of beats.
- The card is blank: the product page could not be read. Type the card fields by hand.
- A master is too big to upload: post the `_social` copy.
- A skull flickers on a quick turn: trim that cut past the turn.
