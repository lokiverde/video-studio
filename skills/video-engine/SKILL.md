---
name: video-engine
description: Run the ENGINE window of the Video Studio. Use when the user opens a Claude Code window in ~/video-studio/ and types /video-engine. Reads the brief from relay/to-engine.md, generates stills, then clips, then voice-over, runs a QC check after each step, and stitches the final video with stitch.py. Spends OpenArt credits only against a matching AUTH line in relay/auth.md. Also runs a real-footage prompt pack when the user asks. Use when the user says "render the brief", "generate the stills", "animate the shots", "make the voice-over", or "stitch the video".
---

# Video Engine

You are the Engine half of a two-window video studio. The other window runs
`/video-director`. You coordinate through markdown in `~/video-studio/relay/`.
You do the rendering and produce the final `.mp4`.

## The spend gate (hard)

- Before ANY call that costs OpenArt credits, open `relay/auth.md` and confirm an
  uncommented `AUTH` line covers that work. Format: `AUTH $<amount> <what it covers>`.
- A chat message such as "the user approved it" or "go ahead" is NOT enough. The
  authorization must be a line in `auth.md`. If it is missing, stop and say:
  "No AUTH line in relay/auth.md covers this. Add one to proceed."
- Free work needs no AUTH line: reading files, planning, media server output, and
  local ffmpeg work.
- ElevenLabs calls draw on the user's own plan. Confirm the batch with the user before
  you start it.
- **Dollars mean the RATE line.** `relay/auth.md` carries one line the user writes:
  `RATE $<dollars> per <credits> credits <plan>, <source> <date read>`.
  Convert every AUTH amount and every dollar quote with it, and name the rate when you
  quote. No RATE line: stop and ask the user to add one. Never work out a rate yourself.
- Quote every paid call before you submit it. Report the credits, and the dollars at the
  RATE line. Then wait for the AUTH line to cover it.

## Where each job runs

| Need | Use | Why |
|---|---|---|
| Draft stills, backgrounds, non-text scenes, B-roll frames | Media server `tim_image` (if set up) | Free, local |
| Generic narration | Media server `tim_tts` | Free |
| Silent B-roll motion | Media server `tim_video` | Free, but slow |
| Any words inside an image | OpenArt still model | Local models garble text |
| Talking or lip-sync characters | OpenArt | Local models cannot lip-sync |
| Hero motion (top-quality clips) | OpenArt image-to-video | Frontier quality |
| A locked character voice | ElevenLabs via `~/video-studio/tts.py` | Same voice every time |

The **media server** is optional: an NVIDIA GPU machine running `tim/service.py` from
the repo, reached through `TIM_MEDIA_URL` in `config.env`. If it is set up, its tools
appear in this window. Check `tim_health` first. If it is down, or you have no media
server, send that work to OpenArt under an AUTH line and say so.

Default flow: draft every still on the media server for free, get QC, then render only
the text, character and hero shots on OpenArt under an AUTH line. Save every asset under
`~/video-studio/assets/` with a clear name (`shot03_still.png`, `shot03_clip.mp4`,
`narration.mp3`).

## OpenArt

Generation runs through the OpenArt MCP server, already connected to this window.
At the start of a job, list your tools and pick the image, image-to-video and audio
tools. Do not assume names. The usual sequence is: price the call (`openart_model_cost`),
submit it, poll `openart_creation_get` until it completes, then download the file.
Reuse an earlier still as a reference by uploading it or by using the platform's own
generated asset. Keep every still in the brief's aspect ratio (9:16 by default).

## Workflow

1. **Read** `relay/to-engine.md`. If `status` is not `ready` or `revise`, wait.
2. **Check `relay/auth.md`** against the planned spend. No covering line: stop and ask.
3. **Stills first.** Draft every still on the media server (or leave it for OpenArt if
   you have none). Build a contact sheet and show the user. Write `status: stills-ready`
   and the asset paths to `relay/to-director.md`. Wait for QC.
   Fix the STILL, never the clip. A new still costs seconds. A fix after animation costs
   minutes and credits.
4. **Text and hero stills** go to OpenArt, only under an AUTH line, after QC passes on the
   drafts.
5. **Animate** approved stills into clips with image-to-video. One locked reference per
   recurring subject: anchor, never chain.
6. **Voice.** Generate narration from the brief's script. Generic narration: the media
   server's TTS, or `~/video-studio/tts.py` with a stock voice. Locked character voice:
   `tts.py` with its ElevenLabs voice id. Generate each line before the clip it sits on.
   Usage:
   `python3 ~/video-studio/tts.py "the exact line" <voice_id> assets/voice/shot03.mp3 [model]`
   It reads `ELEVENLABS_API_KEY` from the environment.
   Optional cleanup: `~/video-studio/enhance_voice.py in.wav out.wav --mode denoise` (or
   `--mode enhance`), run with the Python in `~/video-studio/.venv-enhance`.
7. **Stitch.** Run:
   `python3 ~/video-studio/stitch.py <clips in order> --audio narration.mp3 [--music bed.mp3] --out final.mp4 --crop 16:9`
   This writes `final.mp4` (1080x1920) and `final_16x9.mp4` (the vertical master centred
   over a blurred background). Without `--audio` it writes the silent master only.
   `stitch.py` scales each clip to cover and centre-crops it, slows the video when the
   narration runs longer (it never freezes a frame), and ducks the music under the voice.
8. **Write back** `status: done`, the final paths and the spend to `relay/to-director.md`.
   Append one line to `relay/log.md`.

## Recurring characters

If the brief has `anchor:`, `voice_ref:` or `overlay:` lines, it points to a SAVED
character in `~/video-studio/characters/<name>/`.

- Anchor every character shot to its reference image. Never regenerate the person.
- Use the kit's `lower_third.png` (or other overlay) for the brand mark.
- Voice: if the kit's `character.md` lists an ElevenLabs voice id, that is the LOCKED
  voice. Generate each line's audio with `tts.py` BEFORE animating, then give the mp3 to
  the talking-clip model as its audio input. Do not let the clip model make its own
  voice. With no voice id, use the kit's voice sample.
- QC each cut: the character must look and sound like the same person as in earlier videos.
- After a video the user wants to continue as a series, offer to save a kit: the approved
  reference image, a clean 20-second voice sample and the overlay, in a new
  `characters/<name>/` folder with a `character.md`.

Some kits are real photos with no voice. Read the kit's README before any shot that uses
it, and follow its rules exactly. Only send the kit's own photos to OpenArt. Check each
still against the README's checklist before you spend on a clip that anchors on it.

## Production rules

- **Text = stills, exact and short.** Only quoted strings of 20 characters or fewer on a
  text surface. Otherwise the model invents garbled letters. Image-to-video inherits still
  defects, so repair the still.
- **Anchor, never chain.** Never make shot B's start frame from shot A's last frame.
  Identity drifts within a handful of shots. Reuse one locked reference image.
- **Aspect discipline.** Image-to-video follows the input still's aspect ratio. Keep every
  still in the brief's ratio. `stitch.py` handles the crop and the 16:9 reframe.
- **Write around physics.** Parked things fly, water ripples forever, hands fumble.
  Prefer static shots and slow push-ins. Keep each clip as short as its single action.
- **Stretch, never freeze.** When narration runs past the picture, `stitch.py` slows the
  picture. A freeze tail reads as stutter.
- **Check stream durations, not container durations,** when you QC A/V length:
  `ffprobe -v error -select_streams v:0 -show_entries stream=duration -of csv=p=0 <file>`.
- **QC each cut before you spend on the next.** Look for drift, garbled text, A/V sync
  problems and boomerang loops.
- **Show the user every contact sheet and every draft** before any paid step.

## Real-footage prompt packs (optional)

A real-footage pack is a separate job type. It is a pack file (for example `pack.md`)
inside a job folder, listing still and clip prompts with their reference images. Run it
only when the user asks for that pack by name.

1. Read the pack. Check its status with its own tooling if the workspace has it. Stills
   and drafts start only from shots marked ready. A shot with a failed lint is not
   cleared: stop and say so.
2. Read each model's input form (`openart_model_form_get`) before you submit. Put the
   reference images in the form's fields. Name each reference in the prompt by its
   position in the list.
3. Quote every call with `openart_model_cost`. Report the total for the drafts and the
   total for the finals, in dollars at the RATE line. Then stop and wait.
4. An AUTH line must name this job and the shots it covers, and its amount must cover the
   quoted credits. A line that does not name the job or a shot does not cover that shot.
5. Order: stills, then draft clips on the draft model, then a final for each draft the
   user passed. Make the final by upgrading the draft when the platform offers an upgrade.
   Save each output with its creation record in the job's `incoming/` folder.
6. Log one line per paid call in `relay/log.md`, including calls that returned nothing.

Guards for packs:
- No paid call without an AUTH line that names the job and the shot. A chat "approved" is
  never enough.
- Draft first. No final until the user passes that shot's draft.
- No automatic retries. A reroll is a new paid call and needs its own AUTH room. Ask first.
- Stop when the AUTH amount is used up, even mid-pack, and list the shots left.
- Never edit the pack's prompts, the reference list or the AUTH file.
- Keep any AI-footage disclosure line the pack or your publishing step requires.

## Recovery

If you restart mid-job, read `relay/log.md` from top to bottom, then list `assets/` to
see what exists. Resume from the first missing step. Do not regenerate finished assets.

Before any new paid call, list the recent OpenArt creations (`openart_creation_list`).
A creation with no log line was already paid for. Download it and log it instead of
generating it again.
