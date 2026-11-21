---
name: faceless-video
description: Turn an article or outline into a faceless explainer video: generated or drawn stills, Ken Burns or cut motion, narration, captions, and 16:9 and 9:16 mp4 files. Use when the user says "make this article a faceless video", "faceless video", "video for this article", or gives an article or outline and wants a narrated explainer with no one on camera. Renders locally with ffmpeg. Images and voices come from an optional media server or cloud services.
---

# Faceless Video

Turns an article or an outline into a narrated explainer video with no on-camera presenter. You write the script. The tool renders the stills, narrates them, adds captions and motion, and delivers a 16:9 file and a 9:16 file. Nothing renders past the preview until the user approves it.

## Which skill to use instead

- The user on camera, their own recording as the narration: `skills/talking-head/SKILL.md` (`scripts/th.py`).
- A property tour built from listing photos and an MLS PDF: `skills/listing-video/SKILL.md` (`scripts/lv.py`).
- Photoreal "found footage" clips generated with an AI video service: `skills/real-footage/SKILL.md`.

## Setup (once)

1. Install ffmpeg and put it on your PATH. The tool stops with a clear message if it is missing.
2. Copy `config.env.example` to `config.env` and fill in the lines you use. `config.env` holds your keys. Never commit it.
3. Point `TIM_MEDIA_URL` at your media server: `tim/service.py` on any NVIDIA GPU machine (port 8189 by default). It makes the stills and the default voices. Without it, stills cannot render. As an alternative for narration, `--engine fish` uses the cloud voice service (needs `FISH_API_KEY`).
4. Optional: fill in the BunnyCDN keys to upload finished files and get shareable URLs. Leave them blank and everything stays in `jobs/<job>/out/`.
5. Run all commands from this folder as `python3 scripts/fv.py ...`. On Windows, type `python` in place of `python3`.

## Folder layout

- `jobs/<job>/`: one folder per video. The name is a timestamp plus the word you pass with `--word` (a city or a topic).
- `scenes.json`: the script and the shot list. The job's source of truth.
- `work/`: stills, narration files, and the contact sheets you review.
- `out/`: the finished files and the publish kit (below).

Outputs in `out/`:
- `final_16x9.mp4` and `final_9x16.mp4`
- `youtube.md`: title, description with a chapter timeline, and tags
- `transcript.txt` and `transcript.srt`: the narration as text and as timed captions
- `thumbnail.jpg`
- `route.md`: the format decision (see step 4)

## Workflow

### 1. Write the script: `scenes.json`

Write it yourself. A script you write is better than one the media server's model writes. Only use the server's writer when you have no script: `make --article-url`, `--article-file`, or `--outline-file` sends the source to the server's LLM (`TIM_LLM_URL`).

```json
{"title": "...", "theme": "sketch", "voice": "stock",
 "youtube": {"title": "...", "description": "...", "tags": ["..."], "hashtags": ["..."],
             "takeaways": ["..."]},
 "scenes": [{"id": 1, "narration": "...", "image_prompt": "...", "caption": "..."}]}
```

Rules:
- Use 6 to 10 scenes. The tool accepts 3 to 14. Total narration is 150 to 300 words for a 1 to 2 minute video, or 20 to 60 seconds for a short.
- Scene 1 is the hook. Open on the problem or the surprise, never a greeting. The last scene pays it off. Do not end with generic "follow for more" lines.
- `narration`: one to three spoken sentences, one idea per scene.
- `image_prompt`: describe only what the picture shows. Use generic people, no names. Never put text, words, numbers, signs, or logos in a prompt (see PLAYBOOK.md).
- `caption`: eight words or fewer. Captions carry all on-screen text.
- Check every fact, number, date, and legal claim against the primary source before you render. A supplied script renders word for word, so its errors ship.
- Never put a countdown ("11 days left") into narration or a title. Name the deadline instead.
- Run `fv.py script-history` before you write, so the new script does not repeat a recent hook or opening. After `make`, log it: `fv.py log-script <job> --hook <category> --framework <name> --tone <tone> --opening "first words"`.

Write the `youtube` block with the script, while the hook is fresh:
- `title`: under 60 characters. Use a number or a concrete claim. No all-caps, no emoji, no hashtags.
- `description`: two or three plain sentences saying what the viewer learns. Name the data source if there is one. No timestamps (the tool adds the timeline), no "subscribe". Legal and financial topics end with a not-advice line.
- `tags`: 12 to 15, lowercase, a mix of broad and specific phrases.
- `hashtags`: up to three, without the `#`.
- `takeaways`: three to five lines, each one said in the video. The website library entry uses them.
- Optional `"chapter"` on a scene gives its timeline label when the caption is too short to read as a chapter title.

The tool fills in the transcript and the timeline from the real scene lengths. It rewrites the kit when you run `fv.py kit <job>` after an edit.

#### Picture options for a scene

Pick one per scene. A plain `image_prompt` is the default.

- `image_prompt`: a generated still.
- `photo`: a real photograph from `assets/photos/`, or a path or URL. The image model is skipped. Use only photos you have the right to use, and log each source in `assets/photos/SOURCES.md`. `focus` (`auto`, `top`, `center`, `bottom`) sets the crop.
- `clip`: a finished video file, relative to the job folder or absolute. Optional `trim: [start, end]` and `audio: keep | duck | mute`. A clip stands alone: it cannot also carry an image prompt. If the video has AI-generated footage, the kit adds an AI disclosure line to the description. Set the platform's altered-content label yourself.
- `mograph`: an animated stat comparison, a punch line, or a list, drawn by the Remotion template in `talking-head/` (needs Node). Use it where a number, a list, or one line is the point. Not every scene.
- `figure`: a drawn stick figure (see below).
- `motion`: animates the approved still with a video model on the media server. It costs about 70 seconds per scene. Use it for the hook and the payoff, one or two per video. `motion.prompt` describes movement only.
- `shots`: an array of two to four prompts, for quick cuts on a theme with `"pacing": "cuts"`.
- No `narration` key: a silent scene, timed by `duration` in seconds (default 3.5).
- `sfx`: a sound effect name from `assets/sfx/`. Off unless the user asks for it.

#### Figures and staging

- A `figure` block draws the character on top of a generated background, so the figure never breaks anatomy. Example: `"figure": {"pose": "point", "x": 0.34, "ground": 0.92, "height": 0.62, "flip": false}`.
- Write the `image_prompt` for the background only. Do not say "the main character" in a figure shot. Leave open floor where the figure stands, and say "no people".
- `fv.py poses` lists the poses. Set `mood` on each figure to match the beat: `happy`, `neutral`, `worried`, `sad`, `surprised`, `deadpan`, `skeptical`, `smirk`, or `annoyed`. The hook and any "here is the problem" beat are `worried` or `neutral`. Only real good news gets `happy`.
- Stage the picture so it acts out the sentence. Cut every two to three seconds, change the framing between cuts, and keep the figure from standing beside a backdrop for eight seconds. `"shot": "wide|full|medium|closeup"` sets framing. A list of figures makes a two-shot.
- After you edit poses, moods, or framing, run `fv.py restage <job>`. It re-pastes the figures in seconds and uses no image generation.

### 2. Render the stills and the preview: `make`

```bash
python3 scripts/fv.py make --scenes-file path/to/scenes.json --word <topic> --theme sketch --voice stock
```

- Renders every still twice: a landscape still for the 16:9 cut and a native portrait still for the 9:16 cut. The portrait pass is what keeps a figure placed off center from being cut in half. `--no-portrait` skips it, and the 9:16 then becomes a center crop.
- Prints the job id and the paths to both contact sheets.
- Options: `--theme`, `--voice` (`stock`, `tony`, or a Kokoro voice id such as `am_onyx`), `--engine` (`tim` for the media server, `chatterbox`, `kokoro`, or `fish`), `--music`.
- `--no-preview` skips the review gate. Use it only when the user has explicitly waived review for that job.

### 3. Review gate: stop here until the user says go

Nothing renders the final video before the user approves the preview. This is enforced in code.

1. Show the user both sheets: `jobs/<job>/work/contact_sheet.jpg` (16:9) and `jobs/<job>/work/contact_sheet_9x16.jpg` (9:16, with the caption band and the phone UI shaded so they can see what a phone viewer loses). Offer the single stills too.
2. End your turn. Do not start `finish` while the user is looking.
3. For changes, reroll and show the new sheets:
   - `fv.py regen-scene <job> <n>` rerolls both cuts of scene n with a new seed.
   - `--shot k` picks one shot, `--prompt "..."` replaces the idea, `--portrait` or `--landscape-only` rerolls one cut.
   - For pose, mood, or framing changes on figures, use `fv.py restage <job>` instead.
4. When the user says go: `python3 scripts/fv.py approve <job>`, then `finish`.

Approval is tied to the exact contents of the job. Editing `scenes.json`, or rerolling a still, after approval voids it. `approve` refuses if the sheets are older than the inputs. Regenerate the sheets, show them again, and approve again.

Apply the same gate to `python3 scripts/fv.py verticalize <job>`, which makes new portrait stills for jobs made before the portrait pass existed. It stops at the 9:16 sheet for approval.

### 4. Render the finals: `finish`

```bash
python3 scripts/fv.py finish <job> [--voice tony] [--music assets/music/<track>.mp3] [--music-volume 0.12]
```

`finish` narrates each scene, renders any motion and graphic scenes, assembles both cuts with captions, sets the loudness, runs the audio check, writes the publish kit, and uploads if Bunny is configured. Then:
- Give the user both video paths and the paths to `out/transcript.txt` and `out/transcript.srt`.
- Show the contents of `out/youtube.md`.
- Read the `ROUTE:` line the tool prints, and tell the user what it means. Under 120 seconds: publish as a Short (vertical). 120 to 180 seconds: the user decides. Over 180 seconds: publish the 16:9 as a long video. Use the route as advice, not a rule.
- If narration printed `NARRATION scene N ... LISTEN`, say so, and name the scene. Listen to `work/scene_NN.wav` before calling it broken (see Voices and audio).

### 5. Thumbnail

`finish` writes a quick `out/thumbnail.jpg`. For a three-way test in YouTube Studio's Test & compare, write `thumbnail.json` in the job folder and run:

```bash
python3 scripts/yt_thumb.py --job <job>
```

It writes `out/thumb_variants/thumbnail_A.jpg` (with a face), `_B.jpg` (the same without the face), `_C.jpg` (plain), and `phone_sizes.jpg`. The block holds `lines` (two to four words each, one of them the banner), `accent` (the index of the banner line), `bg` (a still from the job), and optionally `face` and `layers`. Face cutouts need macOS (Vision). Elsewhere the face is drawn as a framed card. Check the face on `phone_sizes.jpg`. Test & compare is done by hand in Studio, because it has no API.

### 6. After publishing

- `python3 scripts/fv.py links <job> --youtube <id or URL> [--blog <url>] [--shorts <id> ...] [--uploaded YYYY-MM-DD]` records the links. It fills `out/linkedin_comment.txt` and the library entry. Post-publication facts go in `links.json`, not `scenes.json`, so they do not void the approval.
- `python3 scripts/fv.py bloglink <job> <url>` adds an article link to the description.
- Optional: `python3 scripts/fv.py publish <job>` schedules Shorts through Blotato with your own accounts. It prints a table first. Posting needs `--go`, which you run only after the user approves that table. Set your account ids in `assets/publish/channels.json` first (`fv.py blotato-accounts` lists them).

### 7. Your own voice instead of TTS

Use this when the user would rather read the narration than use a clone.

1. Turn the narration into a prompter script: one phrase per line, numbers spelled out, a cue for each scene. The tool does not write this file for you.
2. The user records one take of the whole script, with about a second of pause at each scene. A flub needs no edit: pause and read the line again. The last read of a repeated line is kept.
3. `python3 scripts/fv.py voiceover <job> <take-file>` needs an approved job (same gate as `finish`). It transcribes the take, lines it up with each scene, cuts it at the pauses, and runs the rest of `finish`. Flags: `--music`, `--music-volume`, `--clean` (echo cleanup, for a roomy recording only), `--max-pause` (default 0.30 s; trims longer pauses inside a scene), `--no-eq` (skip the microphone EQ for a phone or other mic).
4. Do not speed the user's voice up to fit. Trim the pauses instead.

## Voices and audio

- `stock` (default): Kokoro on the media server. Fast and clean. Pass a Kokoro voice id with `--voice`.
- `tony`: a Chatterbox clone of a voice on the media server. Set up the clone there first. The preset in `scripts/tts.py` (`TONY_VOICE`) was tuned for one speaker. Tune it for your voice or remove it. This voice is slow, about two minutes per scene, so a full video takes 15 to 25 minutes. Tell the user before you start.
- Never speed a cloned voice up after it is read. Speed-ups above about 1.05x make it sound robotic.
- `--engine chatterbox` gives the stock voice a clone. `--engine fish` uses the cloud voice service and needs `FISH_API_KEY` with credit.
- Echo cleanup (Resemble Enhance, in `~/video-studio/.venv-enhance`) removes room echo from a clone when it is installed. It is slow. Machines without it skip the step.
- Word check: after narration, each read is transcribed and compared with the script. A skipped, added, or repeated phrase gets one fresh take. A line that is still off prints `NARRATION scene N ... LISTEN`. Transcription uses Parakeet (`~/video-studio/.venv-parakeet`) on Apple Silicon, with mlx-whisper as the fallback. On Windows, Linux, and Intel Macs it uses faster-whisper (`~/video-studio/.venv-faster-whisper`, or the main Python). Machines with no transcriber skip the check and say so. Check a job by hand with `python3 scripts/wordcheck.py narration <job> [--scenes 3,7]`.
- Loudness: every final is mixed to -16 LUFS with a straight gain and a peak limiter. Do not add dynamic loudness normalization to the voice. It lifts room echo.
- Audio check: `scripts/audio_qc.py` runs on each final and prints PROBLEMS with timestamps for level, true peak, loudness range, and long quiet stretches under speech. Fix the problems before showing the video.
- Music: `--music` takes a name from `assets/music/` or any mp3 or wav path. The bed loops for the length of the video and ducks under narration (`--music-volume` from 0 to 1, default 0.18). Themes can set a default bed.
- Sound effects are off by default. Add `"sfx"` to a scene only when the user asks. A hit between every scene reads as cheap. `fv.py sfx` lists the library.
- The last frame holds briefly while the music fades out, so the video lands. Automatic.

## Themes, characters, and pacing

- `fv.py themes` lists the looks. Start with `sketch` (whiteboard line art), `photo` (photographic), or `toon-explainer` (flat cartoon with a stick figure, quick cuts). A theme sets the style, pacing, caption look, default voice, and optional character and music.
- `"pacing": "kenburns"` (default) gives each still a slow zoom. `"cuts"` gives hard cuts and uses the scene's `shots` array.
- `fv.py characters` lists the characters. A theme with `"character": "<name>"` adds the character's description to every prompt that names it.
- New character: `fv.py save-character <name> --desc "who they are" --look "visual description"`.
- Keep a look you like: `fv.py save-theme <name> --from-job <job>`.
- Photo blocks, clip blocks, and mograph blocks skip the image model, so themes that use only these do not need the media server for those scenes.

## Troubleshooting

- The tool says ffmpeg is missing: install it and check that `ffmpeg -version` works in the same terminal.
- No stills render, or `make` fails right away: check the media server with `curl <TIM_MEDIA_URL>/health`. If it fails, start the server or check the network path to it. Stills have no local fallback.
- `BLOCKED: ... has not been approved`: show the user both sheets and wait for the go, then run `approve`.
- `the job changed since it was approved`: make fresh sheets, show the user, and approve again.
- Upload fails: the finals stay on disk in `jobs/<job>/out/`. Share the local paths.
- Re-uploading a file to the same CDN path can serve the old copy. Upload the new version under a new name, such as `_v2`, and check the file size.
- Garbled words in a picture: reroll the shot, or change the prop to one with no writing surface. Captions are the only place for on-screen text.
- A figure cut in half on the 9:16 cut: add a `"portrait"` key inside that figure block to set its position for the vertical frame.
- Job state: `python3 scripts/fv.py status <job>`.
- A long render stops when the computer sleeps or the session drops: run long commands through `python3 scripts/bg_run.py --name <label> -- <command>`. See PLAYBOOK.md for render safety.
