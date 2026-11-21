"""Paste a drawn character onto a generated background.

The generator draws the world; the character is drawn by us. That split is what makes
anatomy a non-issue: a figure with two arms has two arms in every frame, forever, because
nothing is sampling it.

A scene opts in by carrying a `figure` block:

    "figure": {"pose": "point", "x": 0.34, "ground": 0.92, "height": 0.62, "flip": false}

x and ground are fractions of the frame (x is the figure's centre line, ground is where the
feet land), height is the figure's height as a fraction of frame height, flip mirrors him.
"""
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CHARACTER_DIR = ROOT / "characters" / "stickman"
sys.path.insert(0, str(CHARACTER_DIR))

import figure  # noqa: E402  (needs the path above)
import outfits  # noqa: E402

# figure.render lays the character out between these two rows, measured in head radii
# from the top of its canvas. Everything here is derived from them.
TOP_OF_HAIR = 0.04
GROUND_LINE = 4.49
FIGURE_HEIGHT = GROUND_LINE - TOP_OF_HAIR

DEFAULTS = {"x": 0.5, "ground": 0.94, "height": 0.62, "flip": False, "pose": "stand"}

# Camera framing. A figure that is always full-length and always the same size is a
# presenter standing next to the story. Changing how much of him the frame holds is what
# makes consecutive shots feel like cuts. Values are (height, ground) as frame fractions;
# an explicit height or ground on the block still wins.
SHOTS = {
    "closeup": (1.45, 1.53),   # head and shoulders, the reaction shot
    "medium":  (1.00, 1.10),   # waist up, the talking shot
    "full":    (0.62, 0.94),   # head to toe, the default
    "wide":    (0.30, 0.90),   # small in a big world, the establishing shot
}
# The 9:16 frame is narrow, so the same framings are sized off its width instead.
SHOTS_PORTRAIT = {"closeup": (0.95, 1.06), "medium": (0.60, 0.80), "wide": (0.22, 0.70)}

# A scene may set "mood" (shorthand) or "face" ({"mouth", "brows"}) on its figure block
# to override the pose's default expression. Poses carry a sensible default (think and
# shrug are already worried), but the scene's tone wins: a negative beat must not smile.
MOODS = {
    "happy":     {"mouth": "smile", "brows": "neutral",   "eyes": "open"},
    "neutral":   {"mouth": "flat",  "brows": "neutral",   "eyes": "open"},
    "worried":   {"mouth": "flat",  "brows": "worried",   "eyes": "open"},
    "sad":       {"mouth": "frown", "brows": "worried",   "eyes": "open"},
    "surprised": {"mouth": "oh",    "brows": "worried",   "eyes": "open"},
    # The truth-teller set: he has seen this pitch before and is not buying it.
    "deadpan":   {"mouth": "flat",  "brows": "neutral",   "eyes": "half"},
    "skeptical": {"mouth": "flat",  "brows": "skeptical", "eyes": "half"},
    "smirk":     {"mouth": "smirk", "brows": "skeptical", "eyes": "open"},
    "annoyed":   {"mouth": "frown", "brows": "stern",     "eyes": "half"},
}
FACE_PARTS = {
    "mouth": ("smile", "flat", "frown", "oh", "smirk"),
    "brows": ("neutral", "worried", "stern", "skeptical"),
    "eyes": ("open", "half"),
}


# The 9:16 frame is 56% as wide as it is tall, so a figure sized and placed for 16:9
# either runs off the side or gets sliced by the centre crop. Portrait gets its own
# placement: smaller, pulled toward the middle, feet above the caption band.
PORTRAIT_MAX_HEIGHT = 0.36   # of frame height; about half the frame width, so he stands BESIDE the subject
PORTRAIT_GROUND = 0.72       # feet clear even a two-line vertical caption (band ~0.74-0.83)
PORTRAIT_X_RANGE = (0.29, 0.71)
PORTRAIT_CAST_SCALE = 0.8
PORTRAIT_X_SPREAD = 1.0      # how much of the landscape left/right intent survives


def cast(spec):
    """A figure block is one character or a list of them. Always hand back a list."""
    if spec is None:
        return []
    return list(spec) if isinstance(spec, (list, tuple)) else [spec]


def portrait_figure(spec):
    """The figure block to use on the portrait render of a shot. Auto-derived from the
    landscape block; a "portrait": {...} key inside the figure block overrides any of
    x / ground / height / flip / pose / mood for the vertical frame only."""
    if spec is None:
        return None
    if isinstance(spec, (list, tuple)):
        # Two figures share a frame barely half as wide as it is tall: shrink the cast a
        # step so heads sit side by side instead of overlapping.
        members = [portrait_figure(member) for member in spec]
        if len(members) < 2:
            return members
        return [{**m, "height": round(m["height"] * PORTRAIT_CAST_SCALE, 3)} for m in members]
    override = spec.get("portrait") or {}
    base = {k: v for k, v in spec.items() if k != "portrait"}
    x = float(base.get("x", DEFAULTS["x"]))
    lo, hi = PORTRAIT_X_RANGE
    auto = {"x": round(min(hi, max(lo, 0.5 + (x - 0.5) * PORTRAIT_X_SPREAD)), 3)}
    # A framed shot (closeup, medium, wide) keeps its framing in the tall cut, resized for
    # the narrow frame. Only the full-length default gets shrunk to stand beside the
    # subject and clear the caption band.
    shot = base.get("shot", "full")
    if shot in SHOTS_PORTRAIT:
        height, ground = SHOTS_PORTRAIT[shot]
        auto = {**auto, "height": height, "ground": ground}
        base = {k: v for k, v in base.items() if k not in ("height", "ground")}
    else:
        auto = {**auto, "ground": PORTRAIT_GROUND,
                "height": min(float(base.get("height", DEFAULTS["height"])), PORTRAIT_MAX_HEIGHT)}
    return {**base, **auto, **override}


def resolve_face(spec, pose):
    """The face for this shot: pose default, then mood shorthand, then explicit face keys."""
    face = dict(pose.get("face", {}))
    mood = spec.get("mood")
    if mood is not None:
        if mood not in MOODS:
            raise ValueError(f"unknown mood '{mood}' (have: {', '.join(MOODS)})")
        face = {**face, **MOODS[mood]}
    explicit = spec.get("face") or {}
    for part, allowed in FACE_PARTS.items():
        if explicit.get(part) not in (None, *allowed):
            raise ValueError(f"unknown {part} '{explicit[part]}' (have: {', '.join(allowed)})")
    return {**face, **{k: v for k, v in explicit.items() if k in FACE_PARTS}}


def load_poses():
    return json.loads((CHARACTER_DIR / "poses.json").read_text())


def pose_names():
    return [name for name in load_poses() if not name.startswith("_")]


def render_figure(spec, frame_size):
    """The character alone, sized for this frame, plus where to paste him."""
    poses = load_poses()
    name = spec.get("pose", DEFAULTS["pose"])
    if name not in poses:
        raise KeyError(f"unknown pose '{name}' (have: {', '.join(pose_names())})")

    shot = spec.get("shot", "full")
    if shot not in SHOTS:
        raise ValueError(f"unknown shot '{shot}' (have: {', '.join(SHOTS)})")
    shot_height, shot_ground = SHOTS[shot]

    frame_w, frame_h = frame_size
    target_h = float(spec.get("height", shot_height)) * frame_h
    head_r = target_h / FIGURE_HEIGHT
    pose = {**poses[name], "face": resolve_face(spec, poses[name])}
    art = figure.render(pose, head_r_px=head_r, who=spec.get("who", "stick-man"),
                        prop=spec.get("prop"), bubble=spec.get("bubble"),
                        flipped=bool(spec.get("flip", DEFAULTS["flip"])),
                        outfit=spec.get("outfit"))
    if spec.get("flip", DEFAULTS["flip"]):
        art = art.transpose(Image.FLIP_LEFT_RIGHT)

    centre_x = float(spec.get("x", DEFAULTS["x"])) * frame_w
    ground_y = float(spec.get("ground", shot_ground)) * frame_h
    left = round(centre_x - art.width / 2)
    # A hat grows the canvas upward (outfits.headroom), so the feet sit that much lower in it.
    lift = outfits.headroom(outfits.resolve(spec.get("outfit")))
    top = round(ground_y - (GROUND_LINE + lift) * head_r)
    return art, (left, top)


def place(background, spec):
    """background: a PIL image or a path. Returns a new RGB image, original untouched."""
    if not isinstance(background, Image.Image):
        background = Image.open(background)
    frame = background.convert("RGBA")
    out = frame.copy()
    # A list is a cast: painted in order, so put whoever stands in front last.
    for member in cast(spec):
        art, box = render_figure(member, frame.size)
        # paste with the art as its own mask: it clips correctly when the figure runs
        # off the edge, which alpha_composite will not do.
        out.paste(art, box, art)
    return out.convert("RGB")


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("background")
    parser.add_argument("out")
    parser.add_argument("--pose", default="stand")
    parser.add_argument("--x", type=float, default=DEFAULTS["x"])
    parser.add_argument("--ground", type=float, default=DEFAULTS["ground"])
    parser.add_argument("--height", type=float, default=DEFAULTS["height"])
    parser.add_argument("--flip", action="store_true")
    args = parser.parse_args()
    spec = {"pose": args.pose, "x": args.x, "ground": args.ground,
            "height": args.height, "flip": args.flip}
    place(args.background, spec).save(args.out, quality=95)
    print(f"[composite] {args.out}  pose={args.pose}")


if __name__ == "__main__":
    main()
