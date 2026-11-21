---
name: storyboard-reel
description: Make a "storyboard reel", a 9:16 product ad for a shirt or merch line, built from the user's hand-drawn storyboard and a low poly character. Camera-first image-to-video clips filmed like a game cutscene, a VHS tape look, a white flash, the design fading onto a blank tee, a product card, and every cut with and without music. Use when the user hands over a drawn storyboard for a product ad, or says "storyboard ad", "storyboard reel", "low poly ad", or "ad from my storyboard". NOT a silent-film found-footage ad, NOT an ad cut from the user's own beach or event footage, NOT a narrated explainer (use the faceless-video skill).
---

# Storyboard Reel

Turns a hand-drawn storyboard, a few renders of a low poly character and the product
into a 9:16 ad of about 28 seconds with music and sound effects. No narration, no captions
over the action.

Engine: `python3 scripts/storyboard_reel.py <command> <job>`, run from the repo root
(the folder that contains `scripts/`). `--help` lists every command. Logic is in
`scripts/sr_lib.py` (shot kinds, defaults, timing, checks), `sr_shots.py` (drawing),
`sr_matte.py` (cutouts), `sr_media.py` (ffmpeg, rembg, media server). On Windows use
`python` in place of `python3`.

Starting point: `skills/storyboard-reel/job_template.json`. `new` copies it into the job.
Its sample is a figure-and-glow reel. A camera-first reel is built from `clip` shots.

## The format

- 9:16, about 28 seconds. The music bed sets the length.
- Shot kinds the engine draws: `logo` (on black), `black`, `dolly` (push in on a figure),
  `pose` (hold), `clip` (one image-to-video move), `glow` (a prop's light gathers and
  blows out), `white`, `shirt` (blank tee on white, design fades in, title under it),
  `card` (title, mockup, price, sizes, colours, site), `still` (full-frame key image) and
  `scan` (a search through a scope).
- Reorder, repeat or drop kinds to follow the board. A panel that no kind can draw needs a
  new draw function in `sr_shots.py` plus a test. Say so before you build around it.
- VHS look: `"vhs": 0.5` in job.json (0 off, 1 full). It sits on the character section and
  fades out across the white flash, so the shirt and card come back clean. With `vhs` on,
  the main deliverable is `final_9x16_vhs.mp4`.

## Inputs

- A folder with the storyboard pages and your renders of the figure (one per pose). Name
  files with `logo`, `mockup` or `board` in the name and they are picked up. Add the logo
  on white and a product mockup if you have them.
- The product page URL. `new` reads the page's Shopify `.json` for the title, price, sizes
  and colours.
- For the reveal, a back-print photo on a plain light background. If none is set, the first
  shop image is used. It is often a busy mockup, so swap in a clean one.

## Workflow

1. **New job.**
   `python3 scripts/storyboard_reel.py new <product-url> <images-folder> [--word <topic>] [--title "<title>"]`
   Copies the images into `src/`, the shop images into `product/`, and fills the card copy.
   `--word` ends the job folder name with a topic word.
2. **Author job.json from the storyboard.** Map each panel to a shot, set `panel` to match
   the board, assign each render to a figure, and write the plate prompt. Done when
   `python3 scripts/storyboard_reel.py check <job>` prints the timeline with no problems.
3. **Cutouts** (figure reels): `cutouts <job>`, then open `work/cut/feet_check.jpg`. rembg can
   drop pale bone on a pale floor and keep the cast shadow. Fix each foot with
   `figures.<name>.feet` boxes in source pixels (`add` restores pale pixels, `drop` clears
   dark floor shadow, `rebuild` re-derives the box). Rerun until every foot is whole.
4. **Plate.** `plate <job> --n 3` makes candidate backgrounds on the media server (free).
   View `work/bg/plates.jpg` and set `plate.src` to the one that fits. Keep "wide empty
   flat floor in the foreground" in the prompt, because figures stand at `look.feet_y`.
   You can also set `plate.src` to your own image.
5. **Contact sheet, the first gate.** `stills <job>` writes `work/contact_sheet_9x16.jpg`.
   Check the feet sit on the floor, the figure clears the bottom UI strip, and the card copy
   is right. Show the user the sheet and the quoted cost of the clips. **Stop and wait.**
6. **Clips, only after the user's go.** `kling-frames <job>` writes
   `work/kling/<shot>_start.jpg` (plus `_end.jpg` where the clip has an end frame) and
   prints each prompt. Upload the frames to your image-to-video service (OpenArt: upload,
   quote with `openart_model_cost`, then generate), under an AUTH line in
   `~/video-studio/relay/auth.md`. Save the download, then
   `prep-clip <job> <download.mp4> --shot <id>`. The clip's length sets its shot length.
7. **Preview, the second gate.** `preview <job>` renders the clip stretch with sound to
   `work/preview_clip.mp4`. Check the motion frame by frame, rerun `stills`, then show the
   user the preview and the new sheet. **Stop and wait.**
8. **Post copy.** Write job.json `post`: a short `caption`, then `instagram`, `tiktok`,
   `youtube` (title and description), `facebook`, `hooks`, `order` and a `cover` note. The
   engine appends the fixed signature block from `sr_post.py` to every caption. Edit that
   block for your brand. Done when `kit <job>` prints no "post copy not ready" lines.
9. **Approve and render.** After the user's go: `approve <job>`, then `render <job>`.
   This writes `out/final_9x16_vhs.mp4` (the tape cut, slower), `out/cover.jpg`,
   `out/post.txt` and `out/posts.md`. Then `render <job> --clean` writes the clean
   `out/final_9x16.mp4`. Every render also writes a `_nomusic` twin (sound effects, no music
   bed). Check the logged `1080x1920 30/1 <length>s, audio` line, then pull frames at the cuts.
   `--out <path>` makes a side render that leaves `out/` and the job status alone.
10. **Upload.** `upload <job>` sends the finals, twins, cover and post kit to your CDN
    storage (BunnyCDN, keys in `config.env`). It refuses while the post copy has empty
    captions or leftover `<placeholders>`. A re-upload goes to a new name (`_v2`) because
    CDNs keep serving the old file at a reused path. Give the user the new URLs and paste
    the per-platform captions from `posts.md`. Posting is the user's step.

## The preview gate (enforced in code)

`render` is blocked until `approve`, and `approve` works only on a sheet made from the
current job. Any change to the picture voids the approval: shots, figures, plate, look,
cutouts, a new clip, or any path in the visual part of job.json. Audio and post-copy edits
do not void it. After a picture change, make a fresh sheet and show it again.
`render --no-preview` is only for the user's explicit waiver on that one job.

## Camera-first motion

Motion shots are camera-first image-to-video clips, written like real-footage shots: a
camera rig and lens, one camera move with "not a zoom, not a cut", then the action. Start
with the low-resolution tier. Held stills with slow zooms look like a slideshow.

- **Start frame only:** the camera is free (dolly, arc, advance).
- **A push that must land on a pose:** add an end frame, a crop of the end pose at about
  1.12x. The push then lands exactly there. A start-only close-up can snap the head.
- **A still clip** (`clip` with `start` and `end` image paths) must follow a still whose
  `src` is its start frame.
- `"in": 1.0` skips a clip's first second. `dur: "clip"` takes the clip's real length, and
  the `fill` shot absorbs the difference.
- `"gain"` darkens a clip. `"lights_out": {"at": 2.8, "flicker": 0.7, "floor": 0.04}`
  stutters the light and drops to near black, done in the edit at no cost. Pair it with a
  matching sound effect.
- Keep the threat off screen. Dark and unseen reads scarier than a creature on screen.
- Keep gunfire unseen: cut to black and let the sound carry it. Models fire weapons even
  when told not to, so check weapon clips frame by frame and end the shot before any shot.
- Prompt wording for the video model:
  - One slow, continuous move. Name what stays still (body, feet, background).
  - Say how props behave ("the staff stays upright and never swings"). Avoid "swing".
  - Describe what should appear. Negations ("no mist") are often ignored, so show less.
  - When the prop moves, the whole body moves with it: weight, torso, head. Feet planted.
  - A close-up needs slow breathing and a small tilt for most of the clip, then one quick
    move. Without that it looks frozen.
- Clip length: 3 to 5 seconds. Longer clips give the model room to wander.

## Edit-side knobs (free, drawn in the edit)

- `"fade_in"` fades a clip up from black. `"flash"` adds a white flash cut into it.
- `"handheld"` (0 to 1) sways held stills. Use 0 on camera clips, which carry their own camera.
- `scan` is a search through a scope, as its own shot, on a wide still. Never use a video
  model pan for it, because a pan glides like a slider:
  `{"kind": "scan", "dur": 4.4, "src": "<wide still>", "span": 0.236, "scope": {"radius": 0.445, "sway": 16, "steady": 2.4}, "path": [[0.0, 0.13, 0.24], [3.2, 0.645, 0.345]]}`
  Each path point is `[seconds, x, y]` on the still. The aim chases the path on a spring,
  so it overshoots, corrects and lands on the last point. Tell the video model "no circle,
  no crosshair" if a clip is shown through a scope. The edit draws the ring.
- `"live"` on a scan plays a wide clip inside the still from a given second, so a subject
  moves at real speed when the lens finds him. Use it to remove a pause.
- A small mechanical move the model will not make (a trigger, a switch): rig it in the edit
  from the key frame. Cut the moving part as a polygon, fill behind it, turn it on its joint
  under one slow push. Crop in so the move fills the phone.
- `shirt` `"from_black": 1.0, "from_white": 0` fades the reveal in from black when the board
  has no white-out.

## Full-frame stills and key frames

Use these when there are no figure renders, or the board has close-ups and point-of-view
shots.

- A `still` shot takes a full-frame image `src`, with `push`, `anchor` [x, y], `fade_in`,
  `fade_out` and `flash`.
- Key frames come from an image-edit model, 9:16. Give it the character sheet and the scene
  as references, sheet first. In one tested setup only the first two references reached the
  model, so keep the important ones first.
- The end frame of a clip is an edit of its start frame ("the same image, only ..."), so
  the two line up. A small change is faster as a local edit in code than as a model edit.
- A close-up matches the sheet's own view: a side shot is the sheet's true profile.
- A skull in profile keeps real proportions (a round cranium over a short face). A hood
  follows the cranium and covers the top and back. Say so in the prompt.
- Judge headgear by its side outline. Describe the outline ("short, round, ends at the
  back of the head"). Words like "tall" or "pointed" make image models grow a wizard cap.
- A hand is about as long as the skull is tall. For skeletal hands, name the separate
  finger bones. "Thick chunky" alone gives a fist.
- An opening shot starts high and wide on the whole set, then comes down to the figure.
  Make the wide frame first and take the close end frame as a crop of it. An edit that says
  "the camera has moved" tends to scale the figure in place instead.

## Free draft board first

Before any paid call, rough every panel on the media server (FLUX, about 8 seconds each)
into `work/keys/`, then run `stills`. The user sees the whole cut for free. A rough does not
hold a character, so say that when you show it. Paid key frames replace the roughs.
On a new character, the character sheet is the first paid call. Every key frame then takes
that sheet as its first reference.

Keep one screen direction per character (mirror a rough if it faces the wrong way).
Returning characters are cut from their real key frames, never from a rough.

Keep each recurring character in `assets/characters/<name>/` with a README: the sheet, the
costume rules, the sets they use. Read the README before any key frame.

## Music and sound

- Music bed: instrumental, about 30 seconds, written against the timeline `check` prints.
  A typical arc: a hit on the logo, a brooding bed under the dolly, a rising build through
  the clip and glow, the drop on the white-out, a final hit on the card. Generate it with
  ElevenLabs music, or use your own licensed track. Save it to `assets/music/<name>.mp3` and
  put the prompt in `audio.prompt`.
- Sound effects live in `assets/sfx/` (impact, whoosh, riser). Add `audio.sfx` entries
  anchored to a shot. Make a new one when the prop changes.
- `audio.mute: [<shot ids>]` cuts the music hard across those shots and leaves the sound
  effects playing. Use it for "cut to black, then gunfire".
- Generated gunfire bursts smear into one wall of noise. Generate one clean shot and layer
  the burst locally: a low shelf, a pitch-dropping sub thump under each hit, small pitch and
  level changes per hit, then a limiter.

## Costs

Plates, cutouts and the local render are free. Paid key frames, clips (OpenArt or similar)
and ElevenLabs music and sound effects cost credits. Quote each call first, and keep the
AUTH line in `~/video-studio/relay/auth.md` covering it.

## job.json, in brief

`length` (the music's cut point), `product` (url, title, price, sizes, colours), `plate`
(`src`, `prompt`), `figures` (name to `src`, optional `feet`, `centre_on`), `shots` (a list
of `id`, `kind`, `dur`, `panel` and kind-specific keys), `vhs`, `handheld`,
`audio` (`music`, `prompt`, `music_gain`, `fade_out`, `mute`, `sfx`), `post` (copy for each
platform), and an optional `look`. Defaults per kind live in `SHOT_DEFAULTS` in `sr_lib.py`.
On-screen copy accepts `{title}`, `{details}` and `{site}`.

## Gotchas

- rembg is needed for cutouts: `pip install rembg`. The `cutouts` command says what is
  missing and how to set it up.
- The glow finds a magenta orb by colour. For another prop, set `light.at` ([x, y, r],
  fractions of the figure box) and `light.rgb`. Check price and sizes against the live page.
- ffmpeg must be on your PATH. All on-screen text is drawn with Pillow, so ffmpeg does not
  need the drawtext filter.
