---
name: handover
proves: the camera is held by a person and can change hands
needs: "a moment when a character takes the camera"
not_this: [an edit from one camera to another, a second camera showing in frame]
failure_modes: [the model cuts instead of holding one continuous take, the taker's arm or hand fills the frame, a second camera appears in frame, the frame never settles, the subject is lost at the end]
---

# Handover

> **UNTESTED, AUTHORED FRESH.** The source shows this behavior only as a demo, with no
> prompt text, so this paragraph is not modeled on a prompt that is known to work. Run it
> as a 480p draft before anything else and expect to rewrite it. Every failure mode below
> is a guess.

## Camera

```text
The shot starts steady, locked off or in a slow glide, on [SUBJECT]. At [MOMENT], [CHARACTER] reaches toward the lens and takes the camera. The frame jolts, tilts and swings through [CHARACTER]'s movement for a beat, then settles into handheld shake as [CHARACTER] holds it and points it back at [SUBJECT]. [SUBJECT] stays in frame at the end. The take never breaks: one camera passes between two pairs of hands, not an edit from one camera to another.
```

## Fill-ins
- `[SUBJECT]`: who the shot opens and ends on.
- `[MOMENT]`: what prompts the grab (the subject waves someone over, an argument about
  who films).
- `[CHARACTER]`: who takes the camera.

## Notes
- The usual "operator never seen" guard has to bend here. Say it in CAST: the first
  operator is never seen; [CHARACTER]'s hand may cross the lens once, during the handover
  only.
- Keep the rest of the clip simple. With an untested behavior, every other variable
  should be one that already works.
