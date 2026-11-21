---
name: rephotograph
use: "Re-shoots a still that works in a different capture style, image to image, in two sentences."
---

# Re-photograph

Short on purpose. The scene image carries the composition; the sheet carries the
character's design; the prompt only names the new capture style and which source wins.
On OpenArt: `nano-banana-pro`, mode `image2image`. How closely it matches the source's own
results is unverified.

```text
Rephotograph the scene and pose in @[SCENE IMAGE] as [the target capture style, in one phrase].
Treat @[SHEET] as the definitive design of [character], specifically [which view or pose on the sheet].
```

Rules:
- The capture style phrase comes from a style file's `camera_sentence`, compressed to one
  phrase (for example "a paused frame from a cheap early-2000s camcorder").
- Name exactly one definitive reference, and the exact view on it.
- Drop the second sentence when there is no recurring character.
- Resolution follows the target style's `resolution_note`, not the source still.
