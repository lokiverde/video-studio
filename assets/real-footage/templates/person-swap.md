---
name: person-swap
use: "Turns the first frame of a motion take into the start still: same room, framing, phone position, light and pose, a fictional person in place of whoever acted it out."
---

# Person swap

The start still for a motion-reference clip (guide section 16). The frame comes from the
take itself, so the still and the movement agree on the room, the framing and where the
phone sits; a start still that disagrees with the take is what makes the clip warp. On
OpenArt: `nano-banana-pro`, mode `image2image`, with the frame as its one reference.
Grab the frame with
`ffmpeg -i rf/refs/VID1.mp4 -frames:v 1 rf/refs/VID1_frame.png` (keep the person's name
in both file names when the take shows Tony or Partner: `VID1_tony_frame.png`).

```text
@[IMG1] is a frame from a vertical phone video. Keep everything about the frame exactly: the room, the framing, where the phone sits, the angle, the light and the pose. Replace only the person with [the fictional character: age, build, hair and one line of fixed wardrobe]. Same capture quality as @[IMG1]: [two or three artifacts from the style file].
```

Rules:
- The person in the take is replaced, never kept. If the take shows Tony or Partner, the
  job's `likeness` block must approve that person anyway (`rf lint` C12), because a face
  in a reference can leak through.
- One reference only: the frame. Describe the new person in words; do not attach a face
  sheet unless it is a fictional character's own sheet.
- The artifacts come from the shot's style, usually `phone-front-talk`.

Worked example (the frame from Tony's own car take, swapped for a fictional woman):

```text
@IMG1 is a frame from a vertical phone video. Keep everything about the frame exactly: the room, the framing, where the phone sits, the angle, the light and the pose. Replace only the person with a fictional woman in her early thirties with a messy low bun, small gold hoops and an olive utility jacket. Same capture quality as @IMG1: light skin smoothing, compression smear on fast hands and a faint lens smudge haze.
```
