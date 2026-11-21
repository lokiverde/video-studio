---
name: real-footage
description: Make photoreal "found footage" prompts: stills and short clips that look like a phone, camcorder, disposable flash or skate fisheye caught a real moment. Writes camera-first still prompts and six-block clip prompts, one camera behavior per clip, into a prompt pack for generation on OpenArt through the video-engine skill. Use when the user says "realistic footage", "found footage", "AI footage", "make it look filmed on a phone", "camera style", "prompt pack", "UGC style", or "AI b-roll clip". NOT archive-reel (public-domain silent film), NOT faceless-video stills, NOT talking-head (the user's own footage).
---

# Real footage

Sibling of `faceless-video`, same folder, same jobs folder. Run commands from the Video Studio
folder with `python3 scripts/fv.py rf ...` (on Windows, type `python` instead of `python3`).
Library: `assets/real-footage/` (templates, camera behaviors, camera styles; the file format is in
its `README.md`).

This skill writes prompts. It never calls OpenArt and never spends credits. Generation happens in the
`video-engine` skill.

## Hard rules

- **No real people.** No real person, public figure, lookalike, or "in the style of" a named person.
  Fictional people only.
- **No real brands, logos or readable text** in any prompt. Only the user can allow readable text on a
  shot, by setting `"text_ok": true` on it. Do not set it yourself.
- **No real property, listings, clients or identifiable real locations.**
- **No real money.** Prop money has no printed faces, numbers or words.
- **No weapons in photoreal footage, no injuries.** A stylized, fictional weapon in a cartoon or game look
  is fine, never aimed at the camera, no gore.
- **No fictional testimonials.** A fictional person never claims to have bought, used or been helped by a
  real product or service. They can tell a story, react, or wear the product in a scene.
- **Not a tool promo.** Realistic footage is a cold open or a demonstration inside a topic, never a video
  about the tool itself.
- **Disclose it.** Every finished video with generated footage carries an AI-footage disclosure. The kit
  adds the line to the description. Do not strip it. Also set the platform's altered or synthetic
  content label by hand.
- **Spend only on approval.** Only `video-engine` calls OpenArt, and only against an approval line the
  user writes in `~/video-studio/relay/auth.md`. Prices come live from OpenArt, never from this file.
- No em dashes in prompts, packs or kit files.

## Workflow

1. **Idea.** Get the idea in a line or two and the video it serves. No hook yet? Offer the contrast
   ladder (below) and let the user pick a level.
2. **Check** the idea against the hard rules.
3. **Job and shot list.**
   `python3 scripts/fv.py rf new <word> --idea "..." [--style <name>] [--technique <name>] [--ladder]`
   writes `rf/brief.md` and a starter `rf/shots.json`: S01 still, S02 clip, with `prompt` empty.
   `--style` names a file in `styles/`, `--technique` a file in `behaviors/`. Stills come first, then clips.
   Show the user the list (id, kind, style, technique, duration, one-line action, exact dialogue) before
   you write full prompts.
4. **Write the prompts.** Stills from `templates/ctlt-still.md` (or `templates/llm-helper.md` for a rough
   idea). Clips from `templates/single-take-clip.md`, with the behavior's camera paragraph pasted into
   CAMERA. Several cuts in one generation: `templates/montage.md`. Put each finished prompt in its shot's
   `prompt` field, and set `style` and `technique` to the file names.
   - **Mode** follows the references. A still with no reference: `text2image`. A still with a reference
     image: `image2image`. A clip anchored on an approved still, or with a reference: `element2video`. A
     clip from one still: `image2video`, and add `endFrame` when the clip must land on a look. A clip with
     no references: `text2video`.
   - Each reference is `{"label": "IMG1", "file": "...", "role": "supplies only ..."}`. Write tags as
     `@IMG1`, `@VID1`, `@AUD1` (no brackets). The engine converts them to the model's own syntax.
5. **Lint.** `python3 scripts/fv.py rf lint <job> [--shot <id>]`. Fix every FAIL, and fix or explain
   every WARN. `python3 scripts/fv.py rf status <job>` shows each shot's result. Word lists cannot prove a
   prompt is clean, so the user still looks at the output.
6. **Pack.** `python3 scripts/fv.py rf pack <job>` writes `rf/pack.md` and `rf/prompts/<id>.txt`. It stops
   on a shot with no prompt, model or mode, a price in its settings, an unknown style or technique, a
   repeated id, or `draft_first` set to false. Give the user the path to `pack.md`.
7. **Generate.** The user points `video-engine` at the pack. The engine reads each model's form, quotes
   every call, and stops. The user writes the approval line. Drafts run first (480p), and a final (1080p)
   runs only for a draft the user passes.
8. **Returns.** Each returned file goes through
   `python3 scripts/fv.py rf ingest <job> <file...> --shot <id> [--model <id>] [--creation <id>] [--credits <n>]`.
   `rf status` shows where each shot stands. An ingested clip can drop into a faceless job as a `clip`
   scene, with its sound set to `keep` (its own sound, lowered under narration), `duck` (always low) or `mute`.
9. **Log (optional).** `python3 scripts/fv.py log-script <job> --hook ... --framework ... --tone ... --opening "..." --format ai-footage --technique <behavior> --style <style>`.
10. **New look.** When a still is worth keeping, run `templates/style-extraction.md` on it and its prompt,
    save the result as `styles/<name>.md`, and show the user before you use it on a job.

## Camera first

Describe the photograph before the thing in it. The camera line decides the grain, the flash falloff,
the lens curve, the framing and the compression, so it goes first and the subject second.

A good camera line says: which device, which lens, from where and how far, and one framing flaw that
device would produce in a real person's hands.

- Weak: "A goat at a party, photorealistic, highly detailed."
- Strong: "Candid disposable-camera snapshot with the built-in flash, wide fixed lens, close and slightly
  off-level at chest height, the crop slicing through the top of the frame." Then the goat.

Rules that make it look found:
- **Absurd subject, honest camera.** The more ridiculous the subject, the more ordinary and flawed the camera.
- **One device per shot,** committed to its own flaws. A flash gives hard falloff and red-eye. A camcorder
  gives compression and interlacing. A phone gives HDR halos and smeared texture. Mixing devices reads wrong.
- **Resolution is a style choice.** A camcorder look wants low resolution on purpose. Follow each style's
  resolution note.
- **Sound sells it.** Describe the room's sound in the SOUND block: a tiled bathroom gives a slap echo, a
  closed car a close, dry voice, outdoors gives wind on the mic. A clean studio voice in a bathroom is a tell.
- **Words that hurt:** masterpiece, 8K, hyper-detailed, award-winning, cinematic, ultra-realistic, studio
  lighting. They pull the model toward polished stock imagery.

## Stills: CTLT

Four sentences, one per slot, in this order. Send them as one paragraph, camera sentence first.

- **Camera:** device and how it was held, lens, angle and distance, one framing flaw.
- **Tone:** the feeling of the moment in one clause, then who or what is in frame, doing what, and where.
- **Lighting:** the light as the device recorded it, and what falls to black or blows out.
- **Texture:** three to five physical surface details, plus capture artifacts that match the device.

The styles in `assets/real-footage/styles/` give the camera and texture wording. Pick the style first.
Local FLUX (through the media server, free) ignores negations, so describe what is in the frame, not what is absent.

## Clips: one camera behavior, six blocks

Every single-take clip prompt has six blocks, in this order. Keep all six headings even when a block is one line.

1. **GOAL:** length, device, who is filming, the one camera behavior, and the clean-frame guard.
2. **REFERENCES:** what each reference supplies, and what to ignore. A voice reference is for new lines in
   that voice, never music.
3. **CAST:** the exact on-screen count, who owns each prop, whose wardrobe is exclusive, and where the
   operator stands.
4. **ACTION:** the setting in one sentence, three to five short visible beats, and a clear final image.
5. **CAMERA and SOUND:** the behavior as a physical sequence, then any dialogue (speaker, exact quoted line,
   voice, lip sync), room tone and action sounds, usually no music.
6. **CONTINUITY:** cast, faces, wardrobe, props, room and direction of action stay fixed. The camera
   behavior happens once. The clip starts when the action starts and ends on the stated result.

**Clean-frame guard, every clip:** no overlay, timestamp, REC indicator, battery icon, focus box, grid,
border or subtitles. Without it, models draw a fake camera screen.

**Operator:** say where the person filming stands and that they are never seen. Otherwise a hand or a
phone edge gets painted in.

**Camera behaviors** (`assets/real-footage/behaviors/`, one per clip, performed once):
`handheld`, `crash-zoom`, `voyeuristic`, `whip-pan`, `walking-backward`, `frame-block`, `exposure-shift`,
`focus-fail`, `handover`, `talk-to-lens`. Each file says what the scene needs. Write the move as
trigger, reaction, correction, settle, plus a "not this" clause that rules out the nearest wrong reading.
Models default to the smooth version of every move. Never put two behaviors in one clip: the model blends them.

**Dialogue:** write the line the way a person tells a friend what just happened. Start mid-story, one concrete
detail, no feature list and no call to action. About 2.5 words a second, so 10 seconds holds about 22 to 25
words. Trim the line rather than speeding the voice. Tie an action to a phrase in ACTION, not a single word.

## Montage

One generation with several hard cuts, for example seven shots of about 1.5 seconds. Use
`templates/montage.md`. Timestamp every shot (`SHOT 3 | 3.0-4.5s`), nothing under 1.0 second, one action per
shot from start to impact, then a hard cut. Wordless reactions only, with raw device sound that cuts on every
shot. Close with an exclusions line and a consistency line.

## Motion takes (optional)

A motion take is a short phone video that supplies movement only. Use a faceless take (hands, or just the
camera move) that you own, with its sound stripped before the pack is built:
`ffmpeg -i take.mov -an -t <seconds> rf/refs/VID1.mp4`. Build the start still from the take's first frame
with `templates/person-swap.md`, so the still and the movement agree. A take of a real person's face is not
allowed.

## Lint checks

`rf lint` records a result per shot. Its main checks:

- **FAIL:** the clean-frame guard is missing (C1); cast count missing, or a reference with no "supplies only"
  role (C4); a real person, brand, property or money (C9); text or logos without `text_ok` (I4).
- **WARN:** more than one camera behavior in a clip (C2); a camera paragraph with no trigger, reaction,
  settle or "not this" (C3); no operator position (C5); dialogue with no speaker, exact line, voice or lip
  sync (C6); more than five beats in a clip of 10 seconds or less (C7); no final image (C8); a reference
  tag not in house form (C10); stills with a missing device sentence, filler words or artifacts that do
  not match the device (I1 to I3).

Thresholds and word lists live in `assets/real-footage/lint.json`. Tune them there.

## Styles and models

Starter styles in `assets/real-footage/styles/`: `night-fisheye-flash`, `skate-fisheye`, `disposable-flash`,
`low-bitrate-camcorder`, `phone-selfie-2015`, `phone-snapshot`, `documentary-handheld`, `phone-front-talk`.
Each style file holds the device, lens, viewpoint, framing flaws, light, artifacts, resolution note and
sentence patterns. Pick one device per shot.

The engine lists the models OpenArt offers when it runs and quotes each call before anything is spent.
Model choice is taste. Run one prompt through two or three models and pick by eye.

## Contrast ladder (finding the idea)

Start from the expected scene and add one unexpected layer at a time. Each level keeps the one before it.

- Level 0: the expected scene (a man at a laptop deletes junk mail).
- Level 1: a small human problem (his inbox overflows and he is tempted to answer an obvious scam).
- Level 2: give something personality (the scammer is a fox in a headset, standing in his hallway).
- Level 3: change the emotional register (the fox slowly shakes its head as his finger hovers over Send).

## Troubleshooting

- **The camera came back as a rotated photo on a black canvas.** Use the style's own flaw ("crooked
  horizon") instead of "the frame tilted".
- **The room changed when you said keep it.** Change the reference still, not the words.
- **Fake interface or a timestamp appeared.** Check the clean-frame guard is in GOAL, and re-run lint.
- **A clip shows a lighting stripe, a stray hand or a phone edge.** Add the operator position to CAST.
- **`rf pack` stops.** Read the stop message: a missing prompt, a price in settings, or an unknown style name.
