"""Outfits: what a cast member wears, so a shot can say "the chef", "the scientist" or
"the builder" without a word on screen. Drawn, like everything else on the figure.

A figure block takes "outfit": "chef" or a list, "outfit": ["suit", "glasses"]. Each
outfit has a body part (drawn over the torso, under the arms) and/or a head part (drawn
over the hair). Coordinates are head radii, origin at the head centre, y down: the same
space figure.py draws in.
"""
import math

INK = (17, 17, 17, 255)
OUTLINE_W = 0.028
COAT = (250, 250, 250, 255)
COAT_LIGHT = (255, 255, 255, 255)
COAT_SHADE = (214, 219, 230, 255)
DENIM = (64, 104, 158, 255)
DENIM_LIGHT = (98, 140, 192, 255)
DENIM_DARK = (44, 76, 120, 255)
SHIRT_WHITE = (248, 248, 248, 255)
TIE = (196, 44, 40, 255)
TIE_DARK = (150, 30, 28, 255)
LAPEL = (78, 78, 84, 255)
STRAW = (232, 196, 116, 255)
STRAW_DARK = (196, 156, 80, 255)
HAT_BAND = (170, 50, 42, 255)
HARD_HAT = (246, 196, 18, 255)
HARD_HAT_LIGHT = (255, 226, 110, 255)
VEST = (244, 120, 32, 255)
REFLECT = (226, 230, 236, 255)
STRAP = (120, 78, 40, 255)


def _coat(canvas, g, length):
    """A white coat over the torso: filled, then outlined by hand so the straight top edge
    of the polygon never shows across the shoulders."""
    top, bottom, lean = g["top"], g["bottom"] + length, g["lean"]
    ht, hb = g["half_top"] + 0.02, g["half_bottom"] + 0.05
    shoulders = (lean, top + 0.03)
    canvas.ellipse(shoulders, (ht, 0.10), fill=COAT)
    body = [(-ht + lean, top + 0.03), (ht + lean, top + 0.03), (hb, bottom), (-hb, bottom)]
    canvas.polygon(body, fill=COAT)
    # Core shadow down the side away from the light, following the taper like the shirt's.
    canvas.stroke([(ht + lean - 0.05, top + 0.14), (hb - 0.06, bottom - 0.06)], 0.08, COAT_SHADE)
    canvas.stroke([(-ht + lean, top + 0.05), (-hb, bottom)], OUTLINE_W, INK)
    canvas.stroke([(ht + lean, top + 0.05), (hb, bottom)], OUTLINE_W, INK)
    canvas.stroke([(-hb, bottom), (hb, bottom)], OUTLINE_W, INK)
    canvas.arc(shoulders, (ht, 0.10), 180, 360, INK, OUTLINE_W)
    return top, bottom, lean


def _lab(canvas, g):
    """Long lab coat: lapels in a V, a breast pocket, two buttons."""
    top, bottom, lean = _coat(canvas, g, length=0.30)
    neck = (lean, top + 0.04)
    for side in (-1, 1):
        canvas.stroke([neck, (lean + side * 0.13, top + 0.50)], OUTLINE_W, INK)
        canvas.stroke([(lean + side * 0.05, top + 0.06), (lean + side * 0.20, top + 0.16),
                       (lean + side * 0.13, top + 0.50)], OUTLINE_W, INK)
    pocket_x = lean + 0.10 - g["half_top"]
    canvas.polygon([(pocket_x - 0.07, top + 0.34), (pocket_x + 0.07, top + 0.34),
                    (pocket_x + 0.07, top + 0.46), (pocket_x - 0.07, top + 0.46)],
                   fill=COAT, outline=INK, width=OUTLINE_W * 0.8)
    canvas.stroke([(pocket_x - 0.03, top + 0.30), (pocket_x - 0.03, top + 0.40)], 0.03, (52, 112, 200, 255))
    for y in (top + 0.70, top + 0.95):
        canvas.dot((lean * 0.5, y), 0.035, INK)


def _chef(canvas, g):
    """Double-breasted chef jacket: two rows of buttons, a neckerchief."""
    top, bottom, lean = _coat(canvas, g, length=0.06)
    canvas.polygon([(lean - 0.13, top + 0.02), (lean + 0.13, top + 0.02), (lean, top + 0.20)],
                   fill=TIE, outline=INK, width=OUTLINE_W * 0.8)
    for row in range(3):
        y = top + 0.40 + row * 0.24
        for x in (-0.08, 0.08):
            canvas.dot((lean * 0.6 + x, y), 0.032, INK)


def _suit(canvas, g):
    """Dark jacket (the default torso) with a white shirt V, lapels and a red tie."""
    top, lean = g["top"], g["lean"]
    canvas.polygon([(lean - 0.12, top + 0.01), (lean + 0.12, top + 0.01), (lean, top + 0.48)],
                   fill=SHIRT_WHITE)
    canvas.polygon([(lean - 0.045, top + 0.05), (lean + 0.045, top + 0.05), (lean + 0.03, top + 0.12),
                    (lean - 0.03, top + 0.12)], fill=TIE_DARK)
    canvas.polygon([(lean - 0.03, top + 0.12), (lean + 0.03, top + 0.12), (lean + 0.06, top + 0.52),
                    (lean, top + 0.60), (lean - 0.06, top + 0.52)], fill=TIE)
    for side in (-1, 1):
        canvas.stroke([(lean + side * 0.12, top + 0.02), (lean + side * 0.04, top + 0.50)], 0.03, LAPEL)


def _farmer(canvas, g):
    """Suspender straps over the denim shirt the palette already gave him."""
    top, bottom, lean = g["top"], g["bottom"], g["lean"]
    for side in (-1, 1):
        canvas.stroke([(lean + side * 0.12, top + 0.04), (side * 0.15, bottom - 0.04)], 0.045, STRAP)
        canvas.dot((side * 0.15, top + 0.62), 0.03, (220, 196, 120, 255))


def _builder(canvas, g):
    """Hi-vis vest: orange panels with two reflective stripes."""
    top, bottom, lean = g["top"], g["bottom"], g["lean"]
    ht, hb = g["half_top"] - 0.02, g["half_bottom"] - 0.02
    vest = [(-ht + lean, top + 0.08), (ht + lean, top + 0.08), (hb, bottom - 0.02), (-hb, bottom - 0.02)]
    canvas.polygon(vest, fill=VEST)
    canvas.polygon([(lean - 0.06, top + 0.08), (lean + 0.06, top + 0.08), (lean, top + 0.36)],
                   fill=(41, 41, 42, 255))
    for frac in (0.50, 0.74):
        y = top + (bottom - top) * frac
        half = ht + (hb - ht) * frac
        canvas.polygon([(-half + lean * (1 - frac), y - 0.045), (half + lean * (1 - frac), y - 0.045),
                        (half + lean * (1 - frac), y + 0.045), (-half + lean * (1 - frac), y + 0.045)],
                       fill=REFLECT)
    canvas.polygon(vest, outline=INK, width=OUTLINE_W * 0.8)


def _glasses(canvas, dx, drop):
    eye_y = -0.04 + drop
    for side in (-1, 1):
        canvas.circle((dx + side * 0.27, eye_y), 0.20, outline=INK, width=0.04)
    canvas.arc((dx, eye_y + 0.02), (0.08, 0.06), 200, 340, INK, 0.035)
    for side in (-1, 1):
        canvas.stroke([(dx + side * 0.47, eye_y - 0.03), (dx + side * 0.80, eye_y - 0.10)], 0.035, INK)


def _toque(canvas, dx, drop):
    """Chef's hat: a puff of overlapping discs over a band. Ink discs first, fills on top,
    so the union gets one outline (the same trick as the curly hair)."""
    puffs = [((dx - 0.50, drop - 1.14), 0.42), ((dx + 0.50, drop - 1.14), 0.42),
             ((dx - 0.22, drop - 1.40), 0.42), ((dx + 0.24, drop - 1.42), 0.42),
             ((dx, drop - 1.18), 0.46)]
    for centre, r in puffs:
        canvas.dot(centre, r + OUTLINE_W, INK)
    for centre, r in puffs:
        canvas.dot(centre, r, COAT)
    canvas.arc((dx - 0.22, drop - 1.40), (0.25, 0.25), 200, 280, COAT_SHADE, 0.04)
    # The band sits low and wide enough to hide the hair under it: a hat worn, not perched.
    band = [(dx - 0.88, drop - 0.96), (dx + 0.88, drop - 0.96), (dx + 0.84, drop - 0.52),
            (dx - 0.84, drop - 0.52)]
    canvas.polygon(band, fill=COAT, outline=INK, width=OUTLINE_W)


def _straw_hat(canvas, dx, drop):
    canvas.ellipse((dx, drop - 0.62), (1.52, 0.22), fill=STRAW, outline=INK, width=OUTLINE_W)
    crown = [(dx - 0.70, drop - 0.66), (dx - 0.58, drop - 1.24), (dx + 0.58, drop - 1.24),
             (dx + 0.70, drop - 0.66)]
    canvas.polygon(crown, fill=STRAW, outline=INK, width=OUTLINE_W)
    canvas.polygon([(dx - 0.675, drop - 0.82), (dx + 0.675, drop - 0.82), (dx + 0.69, drop - 0.71),
                    (dx - 0.69, drop - 0.71)], fill=HAT_BAND)
    for x in (-0.30, 0.0, 0.30):
        canvas.stroke([(dx + x, drop - 1.20), (dx + x * 1.1, drop - 0.86)], 0.022, STRAW_DARK)


def _hard_hat(canvas, dx, drop):
    centre_y = drop - 0.50
    dome = [(dx + 1.04 * math.cos(math.radians(a)), centre_y + 0.86 * math.sin(math.radians(a)))
            for a in range(180, 361, 6)]
    canvas.polygon(dome, fill=HARD_HAT, outline=INK, width=OUTLINE_W)
    canvas.stroke([(dx - 0.05, centre_y - 0.84), (dx - 0.05, centre_y - 0.10)], 0.10, HARD_HAT_LIGHT)
    canvas.ellipse((dx, centre_y), (1.24, 0.13), fill=HARD_HAT, outline=INK, width=OUTLINE_W)


# name: (torso palette or None, body painter or None, head painter or None, headroom)
# headroom is how far above the hair the outfit reaches, in head radii: the figure canvas
# grows by that much so a tall hat is not sliced off at the top.
LIBRARY = {
    "chef":    ((COAT, COAT_LIGHT, COAT_SHADE), _chef, _toque, 0.65),
    "lab":     ((COAT, COAT_LIGHT, COAT_SHADE), _lab, _glasses, 0.0),
    "suit":    (None, _suit, None, 0.0),
    "farmer":  ((DENIM, DENIM_LIGHT, DENIM_DARK), _farmer, _straw_hat, 0.10),
    "builder": (None, _builder, _hard_hat, 0.20),
    "glasses": (None, None, _glasses, 0.0),
}


def names():
    return sorted(LIBRARY)


def resolve(spec):
    """None, a name or a list of names -> a tuple of known names. Raises ValueError."""
    if spec is None or spec == "":
        return ()
    worn = (spec,) if isinstance(spec, str) else spec
    if not isinstance(worn, (list, tuple)):
        raise ValueError(f"outfit must be a name or a list of names, got {spec!r}")
    for name in worn:
        if not isinstance(name, str) or name not in LIBRARY:
            raise ValueError(f"unknown outfit {name!r} (have: {', '.join(names())})")
    return tuple(worn)


def torso_palette(worn):
    """(fill, light, dark) for the torso, from the last outfit that sets one, else None."""
    palettes = [LIBRARY[name][0] for name in worn if LIBRARY[name][0]]
    return palettes[-1] if palettes else None


def headroom(worn):
    return max((LIBRARY[name][3] for name in worn), default=0.0)


def draw_body(canvas, worn, geometry):
    """geometry: {"top", "bottom", "half_top", "half_bottom", "lean"} of the torso."""
    for name in worn:
        painter = LIBRARY[name][1]
        if painter:
            painter(canvas, geometry)


def draw_head(canvas, worn, dx, drop):
    for name in worn:
        painter = LIBRARY[name][2]
        if painter:
            painter(canvas, dx, drop)
