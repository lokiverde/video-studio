---
name: handheld
proves: a person is holding the camera
needs: "one event the operator flinches at"
not_this: [a floating stabilizer, a locked-off frame on a support]
failure_modes: [the shot comes out smooth or stabilized, the flinch never happens, the flinch repeats, the subject drops out of frame during the flinch, a hand or phone edge gets painted into frame]
---

# Handheld

> Untested against a live generator. The failure modes are predictions; replace them with
> what the first runs show.

## Camera

```text
The camera is held by hand the whole time, with a constant small irregular tremor. When [TRIGGER] happens, the operator flinches backward and the frame rolls a few degrees, then the operator corrects and re-centers [SUBJECT] and holds there. [SUBJECT] stays visible through the flinch. The wobble lasts from the first frame to the last; the picture is not floating on a stabilizer and not resting on a support.
```

## Fill-ins
- `[TRIGGER]`: the visible or audible event that makes the operator flinch (a pot boils
  over, a balloon pops, something lunges at the lens).
- `[SUBJECT]`: who or what the frame returns to.

## Notes
- The plainest way to make a clip read as filmed by a person. Works with every style.
- A small tremor can sit under any other behavior. The flinch is what makes this one its
  own behavior, so do not add a flinch to a clip that already has another behavior.
