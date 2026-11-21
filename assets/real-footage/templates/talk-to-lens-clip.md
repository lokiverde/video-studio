---
name: talk-to-lens-clip
use: "A fictional person telling a story into their own phone, driven by a motion take: the start still sets the frame, the take sets the movement, the prompt is mostly the line."
---

# Talk-to-lens clip

The six blocks of `single-take-clip`, shaped for the front-camera talking video (guide
section 16). Paste the `talk-to-lens` behavior's camera paragraph into CAMERA. @[IMG1] is
the person-swap start still (`templates/person-swap.md`), @[VID1] the motion take, @[IMG2]
an optional prop. Drop the lines you do not use.

```text
GOAL: One continuous [N]-second vertical clip that looks like an unedited front-camera video [who] filmed of themselves [where], the kind people post to short-video apps when [why they are talking]. It exists to show one camera behavior: talk to lens. Clean full frame: no overlay, timestamp, REC indicator, battery icon, focus box, grid, border, subtitles, captions, app interface, username, like or comment icons, or logo.

REFERENCES:
@[IMG1] supplies only the exact first frame and setting for the whole clip: [speaker]'s face and wardrobe, the room, the framing and the light.
@[VID1] supplies only body movement, hand gestures, timing and where the phone sits. Ignore its person, face, voice, words, room and sound.
@[IMG2] supplies only the [prop]'s shape, color and material. Ignore its background.

CAST: Exactly [count] on screen: [speaker, with one line of fixed wardrobe]. [Speaker] is also the operator: the phone filming [them] [how it sits] and is never seen.

ACTION: [The setting in one sentence.] [Speaker] is already mid-story when the clip starts. [Speaker] talks straight into the lens with natural, expressive hand gestures, both hands, leaning in and sitting back, moving the way the person in @[VID1] moves. On the word [a word from the line], [the prop beat]. End on [the final face or gesture].

CAMERA: [The talk-to-lens camera paragraph, fill-ins replaced.]

SOUND: [Speaker] speaks in [the voice in words: warmth, energy, accent], the same voice and the same level from start to finish, never shouting: "[exact line]". The words are clear and intelligible, and lip movement stays in sync with them. The phone's own microphone in [the room]: [what that room does to a voice], [one or two room sounds]. No music.

CONTINUITY: Keep the cast count, face, wardrobe, props and room fixed. [Speaker] keeps looking into the lens while talking. Perform the camera behavior once. Start mid-sentence and end on the stated result.
```

Rules:
- Build @[IMG1] from the take's own first frame (`templates/person-swap.md`), never from a
  separate text still: the frame and the movement must agree.
- The take comes only from footage Tony owns (guide section 16): Tony or Partner acting it
  out on their own phone, a faceless take, or an earlier approved generation of a fictional
  character. Never a creator's video saved from a social app.
- A take showing Tony or Partner carries their name in its file name
  (`rf/refs/VID1_tony.mp4`), so `rf lint` C12 holds the job to their likeness approval.
- Strip the take's sound and trim it to the clip length before `rf pack`, so its voice and
  words cannot carry over: `ffmpeg -i take.mov -an -t [N] rf/refs/VID1.mp4`. The engine
  stops on a take that still has sound.
- Only the spoken words sit inside the quotes. Tie an action to a word in ACTION, never as
  a stage direction inside the line, or the model may say it out loud. On the first run
  Seedance said the tied word twice; if that repeats, tie the beat to a phrase instead.
- Write the line the way a person tells a friend what just happened (guide section 16):
  mid-story, first person, one concrete detail, one aside. About 25 words fill 10 seconds;
  keep it near 22 when the clip ends on a stare or gesture after the line.
- Never name the app. A brand name fails `rf lint`, and naming it invites its interface.
- No fictional testimonial: the speaker never claims to have bought, used or been helped by
  a real product or service.
- A prop with a printed label is readable text: it needs Tony's `"text_ok": true` on the
  shot.
- Generate the 480p draft first. The 1080p final runs only after Tony passes the draft.

Worked example (10 seconds, a TechTony scam cold open; the take is Tony's own, filmed in
his parked car, saved as `rf/refs/VID1_tony.mp4` with the sound stripped, his likeness
approved for the job):

```text
GOAL: One continuous 10-second vertical clip that looks like an unedited front-camera video a woman filmed of herself in her parked car, the kind people post to short-video apps when they need to tell someone what just happened. It exists to show one camera behavior: talk to lens. Clean full frame: no overlay, timestamp, REC indicator, battery icon, focus box, grid, border, subtitles, captions, app interface, username, like or comment icons, or logo.

REFERENCES:
@IMG1 supplies only the exact first frame and setting for the whole clip: her face and wardrobe, the car interior, the framing and the light.
@VID1 supplies only body movement, hand gestures, timing and where the phone sits. Ignore its person, face, voice, words, room and sound.

CAST: Exactly one on screen: a fictional woman in her early thirties with a messy low bun, small gold hoops and an olive utility jacket, in the driver's seat. She is also the operator: the phone filming her sits in a dash mount and is never seen.

ACTION: A parked car at dusk, the street soft through the side window. She is already mid-story when the clip starts. She talks straight into the lens with natural, expressive hand gestures, both hands, leaning in and sitting back, moving the way the person in @VID1 moves. On the word except, she lifts a second phone from her lap with its screen turned toward her and taps it once. End on her flat, unimpressed stare into the lens.

CAMERA: The phone is clipped in a dash mount, front camera on, filming her talking straight into the lens. A faint constant wobble from the car idling. When she leans in on the part about the bank, her face grows large in the frame and goes slightly soft at the close focus, then she sits back and the frame settles where it started and holds. Her eyes stay on the lens while she speaks, with one quick glance down at the second phone and straight back. The framing changes only because her body moves: not a lens zoom, not a push-in and not an edit to a closer angle.

SOUND: She speaks in a warm, conversational voice with a light American accent, the same voice and the same level from start to finish, never shouting: "Okay, so I almost fell for it. A text from my bank, right? Except my bank doesn't text me at two in the morning." The words are clear and intelligible, and lip movement stays in sync with them. The phone's own microphone in a closed car: her voice close and dry, a faint muffled street hum, the jacket rustling when she moves. No music.

CONTINUITY: Keep the cast count, her face, jacket, bun and hoops, the car interior and the side window fixed. She keeps looking into the lens while talking. Perform the camera behavior once. Start mid-sentence and end on her stare.
```
