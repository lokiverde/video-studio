---
name: whip-pan
proves: the camera reacts to a sound like a person turning toward it
needs: "an off-screen sound and a second target to turn to"
not_this: [an edit to another angle, a lens zoom, the camera traveling forward]
failure_modes: [the model cuts instead of rotating, it pans more than once, no motion smear between the targets, the second target is already in frame before the sound, the first subject goes silent once off frame]
---

# Whip pan

> Untested against a live generator. The failure modes are predictions; replace them with
> what the first runs show.

## Camera

```text
Start medium close on [A]. When [SOUND] is heard, the operator makes one rapid horizontal rotation toward [B]. Everything between smears sideways. The frame overshoots [B] slightly, corrects once and settles on [B]. [A]'s reaction stays audible after [A] leaves the frame. The operator swivels on the spot: not an edit to another angle, not a lens zoom, and not the camera traveling forward.
```

## Fill-ins
- `[A]`: who the clip opens on.
- `[SOUND]`: the off-screen sound that turns the camera (a phone ringing, a door slam).
- `[B]`: what the camera turns to and settles on.

## Notes
- Spec Appendix A (the fox cold open) is a full worked clip with this behavior.
- Put [B] out of frame at the start and say so, or the model shows it early.
