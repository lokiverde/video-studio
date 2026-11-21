---
name: ctlt-still
use: "A photoreal still in four sentences: Camera, Tone, Lighting, Texture. Camera line first."
---

# CTLT still

One sentence per slot, in this order. Take the camera and texture wording from the chosen
style file (`styles/<name>.md`): its `camera_sentence` pattern, one of its
`framing_flaws`, its `artifacts`.

```text
CAMERA: [capture device and how it was held], [lens], [angle and distance], [one framing flaw that device would produce].
TONE: [the feeling of the moment in one clause]. [Who or what is in frame, doing what, where.]
LIGHTING: [the light as the device recorded it], [what falls into darkness or blows out].
TEXTURE: [three to five physical surface details], [capture artifacts that match the device].
```

Rules:
- Camera line first, always. One sentence per slot.
- No filler quality words (masterpiece, 8K, hyper-detailed, award-winning, cinematic).
- Every artifact comes from the same device as the camera line.
- Texture is what a camera can see: surfaces, materials, wear, then the capture artifacts.
- Reference labels only when references are attached, each with the one thing it supplies.
- No logos, brand names or readable text, unless Tony approves readable text for that shot.
- On Tim's FLUX, describe what is there. FLUX ignores negations such as "no people".
- The slot labels are for writing and review. Send the four sentences as one paragraph,
  camera sentence first, unless a test on that model shows the labeled form does better.

Example, sent as one paragraph (style `phone-snapshot`, a reference frame for the fox cold
open in spec Appendix A):

> Quick phone snapshot from the main rear lens, taken standing in a dark hallway at eye
> height, with a crooked horizon and the doorway cut off on the left. Something is wrong and
> nobody is saying it: a red fox in a call-center headset stands upright in a home office
> doorway, holding a desk phone receiver to its ear on an absurdly long coiled cord. The
> only light is a desk lamp and a laptop screen out of frame, so the fox is lit warm from
> one side and the hallway behind it sinks into murky black. Matted fur on the fox's chest,
> a blank plastic badge on a lanyard, scuffed baseboards, a beige coiled cord, and phone
> noise reduction smearing the fur into soft patches with an HDR halo along the doorframe.
