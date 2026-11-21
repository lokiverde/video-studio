"""Draw Stick Man from a pose spec, deterministically.

The whole point of this module is that the character stops being generated. FLUX gives
you a figure that looks right and is free to grow a third hand, because nothing in a
diffusion sampler constrains geometry. Here two arms is two draw calls.

Coordinates are in HEAD RADII, origin at the centre of the head, y pointing down. The
reference model sheet (assets/stickman_ref_v3.png) measures head_r = 245px, so every
constant below is that sheet divided by 245. Render at any pixel size: the figure scales.
"""
import math

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import outfits
import props

SUPERSAMPLE = 4
BIG_HEAD_PX = 140      # a close-up head is already huge; 4x on top of that is 100MB+ of canvas

# Sampled off assets/stickman_ref_v3.png.
INK = (17, 17, 17, 255)
SKIN = (255, 255, 255, 255)          # the head is pure white, not a skin tone
HAIR = (153, 93, 34, 255)
SHIRT = (41, 41, 42, 255)
SHOE = (12, 13, 15, 255)
GLOVE = (255, 255, 255, 255)
SHADOW = (0, 0, 0, 70)

# The polish pass (2026-09-18): same character, same silhouette, but lit. One light,
# upper left, so every form gets a cool shade on its lower right and a highlight on its
# upper left. These are the only colours that pass added.
SKIN_SHADE = (218, 223, 233, 255)
HAIR_LIGHT = (196, 132, 62, 255)
SHIRT_LIGHT = (70, 70, 76, 255)
SHIRT_DARK = (26, 26, 28, 255)
SHOE_LIGHT = (84, 86, 92, 255)
GLOVE_SHADE = (214, 219, 230, 255)
ARM_RIM = (104, 104, 112, 255)       # edge light on an arm that crosses the dark shirt
LIGHT = (-0.13, -0.15)               # where the light sits, as an offset in head radii

# Stroke weights, also in head radii.
LIMB_W = 0.075
OUTLINE_W = 0.028
NECK_W = 0.10

HEAD_R = 1.0
NECK_Y = 0.94          # where the neck leaves the head
TORSO_TOP = 1.02
TORSO_BOTTOM = 2.14
TORSO_HALF_TOP = 0.22
TORSO_HALF_BOTTOM = 0.30
GLOVE_R = 0.13
SHOE_R = (0.20, 0.115)
GROUND_Y = 3.24


def _bezier(p0, p1, p2, steps=24):
    """Quadratic through p0 and p2 with p1 pulling the curve. The reference's arms and
    legs bow slightly rather than running dead straight, and this is that bow."""
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        pts.append((u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0],
                    u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]))
    return pts


class Canvas:
    """Character-space drawing onto a supersampled RGBA bitmap."""

    def __init__(self, width, height, head_r_px, origin):
        self.ss = SUPERSAMPLE if head_r_px < BIG_HEAD_PX else 2
        self.mirror_text = False
        self.scale = head_r_px * self.ss
        self.ox, self.oy = origin[0] * self.ss, origin[1] * self.ss
        self.image = Image.new("RGBA", (width * self.ss, height * self.ss), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)

    def px(self, point):
        return (self.ox + point[0] * self.scale, self.oy + point[1] * self.scale)

    def stroke(self, points, width, colour):
        self.draw.line([self.px(p) for p in points], fill=colour,
                       width=max(1, round(width * self.scale)), joint="curve")
        # PIL has no round cap, so cap the ends by hand or limbs end in a chisel.
        for end in (points[0], points[-1]):
            self.dot(end, width / 2, colour)

    def dot(self, centre, radius, colour):
        cx, cy = self.px(centre)
        r = radius * self.scale
        self.draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=colour)

    def circle(self, centre, radius, fill=None, outline=None, width=OUTLINE_W):
        cx, cy = self.px(centre)
        r = radius * self.scale
        self.draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=outline,
                          width=max(1, round(width * self.scale)))

    def ellipse(self, centre, radii, fill=None, outline=None, width=OUTLINE_W):
        cx, cy = self.px(centre)
        rx, ry = radii[0] * self.scale, radii[1] * self.scale
        self.draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=fill, outline=outline,
                          width=max(1, round(width * self.scale)))

    def polygon(self, points, fill=None, outline=None, width=OUTLINE_W):
        pts = [self.px(p) for p in points]
        self.draw.polygon(pts, fill=fill)
        if outline:
            self.draw.line(pts + [pts[0]], fill=outline,
                           width=max(1, round(width * self.scale)), joint="curve")

    def arc(self, centre, radii, start, end, colour, width):
        cx, cy = self.px(centre)
        rx, ry = radii[0] * self.scale, radii[1] * self.scale
        self.draw.arc([cx - rx, cy - ry, cx + rx, cy + ry], start, end, fill=colour,
                      width=max(1, round(width * self.scale)))

    def shade(self, centre, radii, colour, offset=LIGHT, grow=1.0):
        """Cel shade an ellipse: tint the part of it that a copy slid toward the light
        does not cover. That leaves a crescent on the side away from the light."""
        mask = Image.new("L", self.image.size, 0)
        pen = ImageDraw.Draw(mask)
        cx, cy = self.px(centre)
        rx, ry = radii[0] * self.scale, radii[1] * self.scale
        pen.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255)
        lx, ly = cx + offset[0] * self.scale, cy + offset[1] * self.scale
        pen.ellipse([lx - rx * grow, ly - ry * grow, lx + rx * grow, ly + ry * grow], fill=0)
        self.image.paste(colour, (0, 0), mask)

    def soft_ellipse(self, centre, radii, colour, blur):
        """A blurred blob on its own layer, composited under whatever comes next."""
        layer = Image.new("RGBA", self.image.size, (0, 0, 0, 0))
        cx, cy = self.px(centre)
        rx, ry = radii[0] * self.scale, radii[1] * self.scale
        ImageDraw.Draw(layer).ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=colour)
        layer = layer.filter(ImageFilter.GaussianBlur(blur * self.scale))
        self.image = Image.alpha_composite(self.image, layer)
        self.draw = ImageDraw.Draw(self.image)

    def text(self, centre, glyphs, height, colour):
        """Centred bold glyphs, `height` head radii tall. Only for bubble icons: a drawn
        "?" is still a symbol, not copy. Words belong in captions."""
        font = ImageFont.truetype(str(FONT), max(8, round(height * self.scale)),
                                  layout_engine=ImageFont.Layout.BASIC)
        box = self.draw.textbbox((0, 0), glyphs, font=font)
        cx, cy = self.px(centre)
        tile = Image.new("RGBA", (box[2] - box[0] + 4, box[3] - box[1] + 4), (0, 0, 0, 0))
        ImageDraw.Draw(tile).text((2 - box[0], 2 - box[1]), glyphs, font=font, fill=colour)
        if self.mirror_text:
            # The whole figure gets flipped afterwards; pre-mirror so "?" still reads.
            tile = tile.transpose(Image.FLIP_LEFT_RIGHT)
        self.image.alpha_composite(tile, (round(cx - tile.width / 2), round(cy - tile.height / 2)))

    def finish(self):
        return self.image.resize(
            (self.image.width // self.ss, self.image.height // self.ss),
            Image.LANCZOS)


def _limb(canvas, joints, width=LIMB_W, rim=False):
    """shoulder/hip, then the joint that bends, then the end. Three points bow as one
    curve. Four or more are hard joints (shoulder, elbow, wrist): a folded arm needs a
    real elbow, which a single curve cannot make. `rim` lays a lighter edge under the
    ink, for a black arm lying across a black shirt, where it would otherwise vanish."""
    path = _bezier(*joints) if len(joints) == 3 else list(joints)
    if rim:
        # Forearm only: that is the part lying on the shirt. A rim on the upper arm would
        # halo against the background instead.
        canvas.stroke(path[-2:] if len(joints) > 3 else path, width + 0.06, ARM_RIM)
    canvas.stroke(path, width, INK)


def _glove(canvas, centre, angle):
    """White mitten: a round palm with a thumb bump, outlined."""
    thumb = (centre[0] + GLOVE_R * 0.85 * math.cos(angle),
             centre[1] + GLOVE_R * 0.85 * math.sin(angle))
    canvas.circle(thumb, GLOVE_R * 0.45, fill=GLOVE, outline=INK)
    canvas.circle(centre, GLOVE_R, fill=GLOVE)
    canvas.shade(centre, (GLOVE_R, GLOVE_R), GLOVE_SHADE, offset=(-0.035, -0.04))
    canvas.circle(centre, GLOVE_R, outline=INK)


def _shoe(canvas, foot, facing):
    centre = (foot[0] + SHOE_R[0] * 0.35 * facing, foot[1] + SHOE_R[1] * 0.4)
    canvas.ellipse(centre, SHOE_R, fill=SHOE)
    # A toe highlight is the cheapest way to make a black blob read as a shoe.
    shine = (centre[0] + SHOE_R[0] * 0.30 * facing, centre[1] - SHOE_R[1] * 0.38)
    canvas.ellipse(shine, (SHOE_R[0] * 0.34, SHOE_R[1] * 0.22), fill=SHOE_LIGHT)


def _torso(canvas, lean=0.0, drop=0.0, palette=None):
    """A rounded tunic, wider at the hem. lean shifts the shoulders sideways, drop lowers
    the whole upper body so a crouch or a kneel does not leave the head hanging in place.
    palette (fill, lit edge, core shadow) recolours it for an outfit."""
    shirt, shirt_light, shirt_dark = palette or (SHIRT, SHIRT_LIGHT, SHIRT_DARK)
    top, bottom = TORSO_TOP + drop, TORSO_BOTTOM + drop
    pts = [(-TORSO_HALF_TOP + lean, top), (TORSO_HALF_TOP + lean, top),
           (TORSO_HALF_BOTTOM, bottom), (-TORSO_HALF_BOTTOM, bottom)]
    canvas.polygon(pts, fill=shirt)
    canvas.ellipse((0, bottom), (TORSO_HALF_BOTTOM, 0.10), fill=shirt)
    # Rounded shoulders instead of a sawn-off top edge.
    canvas.ellipse((lean, top + 0.03), (TORSO_HALF_TOP, 0.09), fill=shirt)
    # Lit edge on the left, core shadow on the right, both following the taper.
    flare = TORSO_HALF_BOTTOM - TORSO_HALF_TOP
    rim = [(-TORSO_HALF_TOP + lean + 0.035, top + 0.10), (-TORSO_HALF_TOP + lean + 0.085, top + 0.10),
           (-TORSO_HALF_TOP - flare * 0.8 + 0.085, bottom - 0.12),
           (-TORSO_HALF_TOP - flare * 0.8 + 0.035, bottom - 0.12)]
    canvas.stroke([((rim[0][0] + rim[1][0]) / 2, rim[0][1]),
                   ((rim[2][0] + rim[3][0]) / 2, rim[2][1])], 0.05, shirt_light)
    canvas.stroke([(TORSO_HALF_TOP + lean - 0.035, top + 0.12),
                   (TORSO_HALF_TOP + flare * 0.8 - 0.035, bottom - 0.10)], 0.07, shirt_dark)


def _head(canvas, tilt=0.0, face=None, drop=0.0, look=None):
    face = face or {}
    look = look or LOOKS["stick-man"]
    canvas.stroke([(0, NECK_Y - 0.05 + drop), (0, TORSO_TOP + 0.02 + drop)], NECK_W, INK)
    centre = (tilt * 0.10, drop)
    canvas.circle(centre, HEAD_R, fill=SKIN)
    canvas.shade(centre, (HEAD_R, HEAD_R), SKIN_SHADE)
    canvas.circle(centre, HEAD_R, outline=INK, width=OUTLINE_W * 1.25)
    HAIR_STYLES[look["style"]](canvas, tilt, drop, look)
    _face(canvas, tilt, face, drop)
    if look.get("lashes"):
        _lashes(canvas, tilt, drop)


def _lashes(canvas, tilt, drop):
    """Two short flicks off the outer top corner of each eye. With the long hair, this is
    what reads as a woman at thumbnail size without changing the shared face rig."""
    dx = tilt * 0.10
    eye_y = -0.04 + drop
    for side in (-1, 1):
        cx = dx + side * 0.27
        canvas.stroke([(cx + side * 0.07, eye_y - 0.12), (cx + side * 0.15, eye_y - 0.19)], 0.03, INK)
        canvas.stroke([(cx + side * 0.095, eye_y - 0.075), (cx + side * 0.18, eye_y - 0.11)], 0.03, INK)


HAIR_START, HAIR_END = 207, 337     # degrees around the head, 270 is the crown
HAIR_SPIKES = 4
HAIR_TIP = 1.21                     # how far a spike reaches past the scalp
FRINGE_TEETH = 4
FRINGE_DEPTH = 0.05
HAIR_SWEEP = 11                     # degrees each tip leans, which is what makes it a sweep


def _on_head(angle_deg, radius, dx, drop):
    rad = math.radians(angle_deg)
    return (dx + radius * math.cos(rad), drop + radius * math.sin(rad))


def _hair_spiky(canvas, tilt, drop, look):
    """Spiky chestnut sweep sitting on the crown, tips leaning right. Built off the head
    circle rather than hand-placed points, so it stays glued to the scalp at any tilt."""
    dx = tilt * 0.10
    span = HAIR_END - HAIR_START
    edge = []
    for i in range(HAIR_SPIKES * 2 + 1):
        angle = HAIR_START + span * i / (HAIR_SPIKES * 2)
        if i % 2:
            edge.append(_on_head(angle + HAIR_SWEEP, HAIR_TIP, dx, drop))
        else:
            edge.append(_on_head(angle, 1.01, dx, drop))
    # The return trip across the forehead is the fringe. It used to be one straight
    # chord, which read as a paper hat; now it is a row of short teeth cut into it.
    first, last = edge[0], edge[-1]
    for i in range(1, FRINGE_TEETH * 2):
        t = i / (FRINGE_TEETH * 2)
        x = last[0] + (first[0] - last[0]) * t
        y = last[1] + (first[1] - last[1]) * t
        edge.append((x, y + (FRINGE_DEPTH if i % 2 else 0.0)))
    canvas.polygon(edge, fill=look["hair"])
    # Depth: a lit streak up the left face of each spike.
    for i in range(1, HAIR_SPIKES * 2, 2):
        tip = edge[i]
        root = ((edge[i - 1][0] + edge[i + 1][0]) / 2, (edge[i - 1][1] + edge[i + 1][1]) / 2)
        start = (root[0] + (tip[0] - root[0]) * 0.15 - 0.03, root[1] + (tip[1] - root[1]) * 0.15)
        end = (root[0] + (tip[0] - root[0]) * 0.62 - 0.02, root[1] + (tip[1] - root[1]) * 0.62)
        canvas.stroke([start, end], 0.04, look["hair_light"])
    canvas.polygon(edge, outline=INK, width=OUTLINE_W)


def _hair_neat(canvas, tilt, drop, look):
    """A combed cap with a side part: the older, tidier man. Same scalp arc as the spikes."""
    dx = tilt * 0.10
    cap = [_on_head(a, 1.05, dx, drop) for a in range(205, 336, 5)]
    # The hairline arches UP across the forehead. A straight chord here reads as a helmet.
    cap += _bezier(cap[-1], (dx + 0.10, drop - 0.86), cap[0], 14)[1:-1]
    canvas.polygon(cap, fill=look["hair"])
    canvas.stroke([_on_head(a, 0.97, dx, drop) for a in range(222, 262, 5)], 0.04, look["hair_light"])
    canvas.polygon(cap, outline=INK, width=OUTLINE_W)
    part = _on_head(296, 1.05, dx, drop)
    canvas.stroke([part, (part[0] - 0.07, part[1] + 0.20)], OUTLINE_W, INK)


def _hair_curly(canvas, tilt, drop, look):
    """A mop of overlapping curls. Ink discs first, fills on top, so the union gets one
    outline instead of every curl being ringed."""
    dx = tilt * 0.10
    curls = [(_on_head(a, r, dx, drop), size)
             for a, r, size in [(200, 0.98, 0.20), (222, 1.04, 0.23), (246, 1.08, 0.25),
                                (270, 1.10, 0.26), (294, 1.08, 0.25), (318, 1.04, 0.23),
                                (340, 0.98, 0.20), (234, 0.80, 0.20), (270, 0.78, 0.21),
                                (306, 0.80, 0.20)]]
    for centre, size in curls:
        canvas.dot(centre, size + OUTLINE_W, INK)
    for centre, size in curls:
        canvas.dot(centre, size, look["hair"])
    for centre, size in curls[:7]:
        canvas.arc((centre[0] - 0.02, centre[1] - 0.02), (size * 0.6, size * 0.6), 190, 260,
                   look["hair_light"], 0.035)


LONG_HAIR_END = 1.42       # where the ends fall below the head centre: just past the chin, on the shoulders
LONG_HAIR_WIDTH = 0.98     # half-width at the ends: tapers in under the jaw so the arms stay clear


def _hair_long_back(canvas, tilt, drop, look):
    """The length of a shoulder-length cut, hanging behind the head and neck. render()
    draws it before the body, so the torso and arms sit in front of it."""
    dx = tilt * 0.10
    crown = [_on_head(a, 1.12, dx, drop) for a in range(160, 381, 5)]
    right_end = (dx + LONG_HAIR_WIDTH, drop + LONG_HAIR_END)
    left_end = (dx - LONG_HAIR_WIDTH, drop + LONG_HAIR_END)
    right_side = _bezier(crown[-1], (dx + 1.20, drop + 0.95), right_end, 12)[1:]
    ends = _bezier(right_end, (dx, drop + LONG_HAIR_END + 0.10), left_end, 16)[1:]
    left_side = _bezier(left_end, (dx - 1.20, drop + 0.95), crown[0], 12)[1:-1]
    shape = crown + right_side + ends + left_side
    canvas.polygon(shape, fill=look["hair"], outline=INK, width=OUTLINE_W)
    for side in (-1, 1):
        canvas.stroke([(dx + side * 1.00, drop + 0.50), (dx + side * 0.98, drop + 1.22)], 0.035,
                      look["hair_light"])


def _hair_long(canvas, tilt, drop, look):
    """The front of the shoulder-length cut: crown, a fringe swept from a part on her left
    down toward the other temple, and a lock down each side of the face. The fringe stays
    above every brow shape (the skeptical brow peaks near y -0.41)."""
    dx = tilt * 0.10
    outer = [_on_head(a, 1.08, dx, drop) for a in range(165, 381, 5)]
    right_lock = [_on_head(a, r, dx, drop) for a, r in [(20, 0.92), (5, 0.90), (350, 0.89), (332, 0.87)]]
    part = _on_head(318, 0.86, dx, drop)
    temple = _on_head(200, 0.86, dx, drop)
    fringe = _bezier(part, (dx - 0.35, drop - 0.62), temple, 16)
    left_lock = [_on_head(a, r, dx, drop) for a, r in [(186, 0.90), (172, 0.92), (165, 0.93)]]
    shape = outer + right_lock + fringe + left_lock
    canvas.polygon(shape, fill=look["hair"])
    canvas.stroke([_on_head(a, 0.98, dx, drop) for a in range(222, 262, 5)], 0.04, look["hair_light"])
    canvas.polygon(shape, outline=INK, width=OUTLINE_W)
    canvas.stroke([_on_head(318, 1.07, dx, drop), part], OUTLINE_W, INK)


FONT = Path(__file__).resolve().parents[2] / "assets" / "fonts" / "DejaVuSans-Bold.ttf"
BUBBLE_AT, BUBBLE_R = (1.34, -0.60), 0.54
RED, GREEN, GOLD_INK = (214, 48, 40, 255), (52, 160, 80, 255), (196, 140, 20, 255)


def _icon_x(canvas, c):
    for dx in (-1, 1):
        canvas.stroke([(c[0] - 0.24 * dx, c[1] - 0.24), (c[0] + 0.24 * dx, c[1] + 0.24)], 0.12, RED)


def _icon_check(canvas, c):
    canvas.stroke([(c[0] - 0.26, c[1] + 0.02), (c[0] - 0.08, c[1] + 0.22), (c[0] + 0.28, c[1] - 0.22)],
                  0.12, GREEN)


def _icon_heart(canvas, c):
    for dx in (-0.13, 0.13):
        canvas.dot((c[0] + dx, c[1] - 0.08), 0.155, RED)
    canvas.polygon([(c[0] - 0.275, c[1] - 0.02), (c[0] + 0.275, c[1] - 0.02), (c[0], c[1] + 0.30)], fill=RED)


# icon name -> drawer. The signature gag of the countdown format: a character "says" a
# symbol. One glyph, never a word.
BUBBLES = {
    "x": _icon_x,
    "check": _icon_check,
    "heart": _icon_heart,
    "question": lambda canvas, c: canvas.text(c, "?", 0.72, INK),
    "exclaim": lambda canvas, c: canvas.text(c, "!", 0.72, RED),
    "dollar": lambda canvas, c: canvas.text(c, "$", 0.68, GREEN),
    "zzz": lambda canvas, c: canvas.text(c, "zzz", 0.42, INK),
}


def _bubble(canvas, icon, drop=0.0):
    """Speech bubble up and to the right of the head, tail pointing back at the mouth."""
    if icon not in BUBBLES:
        raise ValueError(f"unknown bubble '{icon}' (have: {', '.join(BUBBLES)})")
    c = (BUBBLE_AT[0], BUBBLE_AT[1] + drop)
    tail = [(c[0] - 0.40, c[1] + 0.26), (c[0] - 0.12, c[1] + 0.46), (c[0] - 0.62, c[1] + 0.72)]
    canvas.polygon(tail, fill=SKIN, outline=INK, width=OUTLINE_W)
    canvas.circle(c, BUBBLE_R, fill=SKIN, outline=INK, width=OUTLINE_W)
    canvas.polygon([(c[0] - 0.37, c[1] + 0.27), (c[0] - 0.15, c[1] + 0.43), (c[0] - 0.30, c[1] + 0.20)],
                   fill=SKIN)      # erase the outline where tail meets bubble
    BUBBLES[icon](canvas, c)


HAIR_STYLES = {"spiky": _hair_spiky, "neat": _hair_neat, "curly": _hair_curly, "long": _hair_long}
# Styles with length that hangs behind the body, drawn before the torso and arms.
HAIR_BACK = {"long": _hair_long_back}

# The drawn cast. Same body, same face rig, same light: only the hair changes, which is
# the design language the character library already describes for these three.
LOOKS = {
    "stick-man": {"style": "spiky", "hair": HAIR, "hair_light": HAIR_LIGHT},
    "gray":      {"style": "neat",  "hair": (152, 155, 162, 255), "hair_light": (205, 208, 214, 255)},
    "curly":     {"style": "curly", "hair": (34, 30, 32, 255),    "hair_light": (92, 86, 92, 255)},
    # Shoulder-length black hair and lashes: the wife, the client, any woman in the story.
    "raven":     {"style": "long",  "hair": (46, 44, 50, 255),    "hair_light": (116, 112, 124, 255),
                  "lashes": True},
}


EYE_R = (0.105, 0.15)
BROW_W = 0.042
MOUTH_W = 0.038


def _face(canvas, tilt, face, drop=0.0):
    dx = tilt * 0.10
    eye_y = -0.04 + drop
    half = face.get("eyes") == "half"
    for side in (-1, 1):
        cx = dx + side * 0.27
        canvas.ellipse((cx, eye_y), EYE_R, fill=INK)
        canvas.circle((cx - 0.035, eye_y - 0.055), 0.034, fill=SKIN)
        canvas.circle((cx + 0.035, eye_y + 0.06), 0.016, fill=SKIN)
        if half:
            # Half-lidded: the lid is a slab of skin over the top of the eye with an ink
            # edge. This one detail is most of what makes a face read as unimpressed.
            lid = eye_y - 0.015
            canvas.polygon([(cx - 0.14, eye_y - 0.19), (cx + 0.14, eye_y - 0.19),
                            (cx + 0.14, lid), (cx - 0.14, lid)], fill=SKIN)
            canvas.stroke([(cx - 0.125, lid), (cx + 0.125, lid)], 0.034, INK)
    _brows(canvas, dx, eye_y, face.get("brows", "neutral"))
    _mouth(canvas, dx, face.get("mouth", "smile"), drop)


def _brows(canvas, dx, eye_y, kind):
    """Short slanted strokes, not arcs. An arc reads as a smiley face. `lift` raises the
    inner end (worried), a negative lift drops it (stern). Skeptical cocks one brow only."""
    for side in (-1, 1):
        cx = dx + side * 0.27
        base = eye_y - 0.27
        inner_lift, raise_all = 0.0, 0.0
        if kind == "worried":
            inner_lift = 0.07
        elif kind == "stern":
            inner_lift, raise_all = -0.09, -0.03
        elif kind == "skeptical":
            if side == 1:
                # the cocked brow: higher, and bowed
                pts = _bezier((cx - 0.15, base), (cx, base - 0.10), (cx + 0.16, base - 0.01), 10)
                canvas.stroke(pts, BROW_W, INK)
                continue
            inner_lift, raise_all = -0.05, -0.05
        outer = (cx + side * 0.14, base - raise_all)
        inner = (cx - side * 0.14, base - inner_lift - raise_all)
        canvas.stroke([outer, inner], BROW_W, INK)


def _mouth(canvas, dx, kind, drop=0.0):
    if kind == "oh":
        canvas.ellipse((dx, 0.46 + drop), (0.075, 0.10), fill=INK)
    elif kind == "flat":
        canvas.stroke([(dx - 0.16, 0.46 + drop), (dx + 0.16, 0.46 + drop)], MOUTH_W, INK)
    elif kind == "frown":
        # Inverted arc, centred lower so the corners turn down below the cheek line.
        canvas.arc((dx, 0.62 + drop), (0.20, 0.16), 205, 335, INK, MOUTH_W)
    elif kind == "smirk":
        # Flat on one side, hooked up on the other, with a cheek tick at the hooked end.
        canvas.stroke(_bezier((dx - 0.15, 0.48 + drop), (dx + 0.08, 0.52 + drop),
                              (dx + 0.20, 0.38 + drop), 12), MOUTH_W, INK)
        canvas.stroke([(dx + 0.215, 0.33 + drop), (dx + 0.25, 0.40 + drop)], MOUTH_W * 0.8, INK)
    else:
        canvas.arc((dx, 0.30 + drop), (0.22, 0.20), 25, 155, INK, MOUTH_W)


def render(pose, head_r_px=120, canvas_size=None, shadow=True, who="stick-man", prop=None,
           bubble=None, flipped=False, outfit=None):
    """Return an RGBA image of `who` in `pose`, transparent everywhere else. A hat makes
    the canvas taller by outfits.headroom() head radii, all of it added at the top."""
    if who not in LOOKS:
        raise ValueError(f"unknown cast member '{who}' (have: {', '.join(LOOKS)})")
    worn = outfits.resolve(outfit)
    lift = outfits.headroom(worn)
    width = canvas_size[0] if canvas_size else round(head_r_px * 4.2)
    height = canvas_size[1] if canvas_size else round(head_r_px * (5.2 + lift))
    origin = (width / 2, head_r_px * (1.25 + lift))
    canvas = Canvas(width, height, head_r_px, origin)
    canvas.mirror_text = flipped

    if shadow and pose.get("shadow", True):
        canvas.soft_ellipse((0.06, pose.get("ground", GROUND_Y) + 0.07), (0.66, 0.10), SHADOW, 0.05)

    for side in ("l", "r"):
        leg = pose["legs"][side]
        _limb(canvas, leg)
        _shoe(canvas, leg[2], -1 if side == "l" else 1)

    drop = pose.get("drop", 0.0)
    lean = pose.get("lean", 0.0)
    look = LOOKS[who]
    if look["style"] in HAIR_BACK:
        HAIR_BACK[look["style"]](canvas, pose.get("tilt", 0.0), drop, look)
    _torso(canvas, lean, drop, outfits.torso_palette(worn))
    outfits.draw_body(canvas, worn, {"top": TORSO_TOP + drop, "bottom": TORSO_BOTTOM + drop,
                                     "half_top": TORSO_HALF_TOP, "half_bottom": TORSO_HALF_BOTTOM,
                                     "lean": lean})

    held = props.resolve(prop)
    # arm_order lets a pose say which arm lies on top (crossed arms); hidden_gloves is a
    # hand tucked out of sight behind the other arm.
    for side in pose.get("arm_order", ("l", "r")):
        arm = pose["arms"][side]
        _limb(canvas, arm, rim=side in pose.get("arm_rim", ()))
        if held and held[1] == side:
            props.draw(canvas, held[0], arm[-1], -1 if side == "l" else 1)
        if side not in pose.get("hidden_gloves", ()):
            _glove(canvas, arm[-1], math.pi if side == "l" else 0)

    _head(canvas, pose.get("tilt", 0.0), pose.get("face"), drop, LOOKS[who])
    outfits.draw_head(canvas, worn, pose.get("tilt", 0.0) * 0.10, drop)
    if bubble:
        _bubble(canvas, bubble, drop)
    return canvas.finish()
