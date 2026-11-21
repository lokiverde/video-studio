"""The prop library: small drawn objects a cast member holds.

Same reasoning as the figure itself. FLUX will not reliably put a phone in a hand, and
when it does the hand grows a sixth finger. A prop here is a few draw calls anchored to
the end of an arm, so it is identical in every frame and on both cuts.

Every prop is drawn in head radii around `hand` (the glove centre). `side` is +1 for the
right hand and -1 for the left, so a prop that leans or extends does it AWAY from the
body. Props stay upright whatever the arm is doing. The glove is drawn afterwards by
figure.py, on top, so the hand reads as gripping. NO text on any prop, ever: captions
carry words.
"""
import math

INK = (17, 17, 17, 255)
LINE = 0.026

PAPER = (250, 248, 240, 255)
PAPER_LINE = (176, 178, 186, 255)
SCREEN = (112, 196, 255, 255)
PHONE = (34, 35, 40, 255)
CASH = (92, 170, 96, 255)
CASH_DARK = (58, 124, 66, 255)
GOLD = (232, 182, 60, 255)
LEATHER = (139, 88, 46, 255)
LEATHER_DARK = (98, 60, 30, 255)
CUP = (248, 246, 240, 255)
SLEEVE = (150, 100, 58, 255)
GLASS = (190, 228, 250, 255)
WOOD = (168, 120, 70, 255)
SIGN_RED = (208, 52, 44, 255)
WALL = (244, 232, 206, 255)
ROOF = (176, 70, 52, 255)
BULB = (255, 221, 87, 255)
BULB_BASE = (150, 152, 160, 255)


def _rect(cx, cy, w, h, angle=0.0):
    """Corner points of a w x h rectangle centred on (cx, cy), tilted by `angle` degrees."""
    rad = math.radians(angle)
    cos, sin = math.cos(rad), math.sin(rad)
    return [(cx + x * cos - y * sin, cy + x * sin + y * cos)
            for x, y in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))]


def _phone(c, hand, side):
    cx, cy = hand[0] + side * 0.03, hand[1] - 0.20
    c.polygon(_rect(cx, cy, 0.25, 0.46, side * 8), fill=PHONE, outline=INK, width=LINE)
    c.polygon(_rect(cx, cy - 0.01, 0.19, 0.36, side * 8), fill=SCREEN)


def _cash(c, hand, side):
    for tilt, shade in ((-24, CASH_DARK), (0, CASH), (24, CASH_DARK)):
        ang = side * tilt
        cx = hand[0] + 0.30 * math.sin(math.radians(ang))
        cy = hand[1] - 0.30 * math.cos(math.radians(ang))
        c.polygon(_rect(cx, cy, 0.20, 0.44, ang), fill=shade, outline=INK, width=LINE)
        c.circle((cx, cy), 0.055, fill=PAPER, outline=INK, width=LINE * 0.8)


def _keys(c, hand, side):
    ring = (hand[0], hand[1] + 0.20)
    c.circle(ring, 0.10, outline=GOLD, width=0.035)
    c.circle(ring, 0.118, outline=INK, width=LINE * 0.7)
    for lean in (-16, 14):
        rad = math.radians(lean)
        tip = (ring[0] + 0.40 * math.sin(rad), ring[1] + 0.10 + 0.40 * math.cos(rad))
        root = (ring[0] + 0.10 * math.sin(rad), ring[1] + 0.10 * math.cos(rad))
        c.stroke([root, tip], 0.06, INK)
        c.stroke([root, tip], 0.034, GOLD)
        c.stroke([(tip[0], tip[1] - 0.10), (tip[0] + 0.07, tip[1] - 0.10)], 0.034, GOLD)


def _contract(c, hand, side):
    cx, cy = hand[0] + side * 0.10, hand[1] - 0.26
    page = _rect(cx, cy, 0.46, 0.60, side * 6)
    c.polygon(page, fill=PAPER, outline=INK, width=LINE)
    # Ruled lines, not writing: a block of text would need to be legible and it cannot be.
    for i in range(5):
        y = cy - 0.19 + i * 0.085
        c.stroke([(cx - 0.15, y + side * 0.012), (cx + (0.15 if i < 4 else 0.02), y - side * 0.012)],
                 0.02, PAPER_LINE)
    c.stroke([(cx - 0.02, cy + 0.22), (cx + 0.16, cy + 0.20)], 0.024, INK)   # the signature line


def _coffee(c, hand, side):
    cx, top, bottom = hand[0] + side * 0.02, hand[1] - 0.34, hand[1] + 0.12
    c.polygon([(cx - 0.15, top), (cx + 0.15, top), (cx + 0.11, bottom), (cx - 0.11, bottom)],
              fill=CUP, outline=INK, width=LINE)
    c.polygon([(cx - 0.14, top + 0.14), (cx + 0.14, top + 0.14),
               (cx + 0.12, top + 0.32), (cx - 0.12, top + 0.32)], fill=SLEEVE)
    c.polygon(_rect(cx, top - 0.025, 0.36, 0.07), fill=CUP, outline=INK, width=LINE)


def _briefcase(c, hand, side):
    cx, cy = hand[0], hand[1] + 0.38
    c.arc((cx, hand[1] + 0.13), (0.13, 0.13), 180, 360, INK, 0.04)
    c.polygon(_rect(cx, cy, 0.74, 0.50), fill=LEATHER, outline=INK, width=LINE)
    c.polygon(_rect(cx, cy - 0.17, 0.74, 0.12), fill=LEATHER_DARK)
    c.polygon(_rect(cx, cy, 0.74, 0.50), outline=INK, width=LINE)
    c.polygon(_rect(cx, cy - 0.10, 0.12, 0.09), fill=GOLD, outline=INK, width=LINE * 0.8)


def _magnifier(c, hand, side):
    lens = (hand[0] + side * 0.30, hand[1] - 0.40)
    c.stroke([hand, (hand[0] + side * 0.18, hand[1] - 0.24)], 0.085, INK)
    c.circle(lens, 0.22, fill=GLASS, outline=INK, width=0.05)
    c.arc(lens, (0.13, 0.13), 200, 260, PAPER, 0.03)


def _sign(c, hand, side):
    """A blank yard sign on a post. Red board, white band, no lettering: the caption says
    what it is (for sale, sold, open house)."""
    top = hand[1] - 0.95
    c.stroke([(hand[0], hand[1] + 0.30), (hand[0], top)], 0.07, INK)
    c.stroke([(hand[0], hand[1] + 0.30), (hand[0], top)], 0.04, WOOD)
    cx, cy = hand[0] + side * 0.36, top + 0.24
    c.polygon(_rect(cx, cy, 0.78, 0.50), fill=SIGN_RED, outline=INK, width=LINE)
    c.polygon(_rect(cx, cy, 0.62, 0.34), fill=PAPER)      # a blank placard, not a flag


def _house(c, hand, side):
    cx, base = hand[0], hand[1] - 0.10
    c.polygon([(cx - 0.24, base), (cx + 0.24, base), (cx + 0.24, base - 0.30),
               (cx - 0.24, base - 0.30)], fill=WALL, outline=INK, width=LINE)
    c.polygon([(cx - 0.31, base - 0.30), (cx + 0.31, base - 0.30), (cx, base - 0.58)],
              fill=ROOF, outline=INK, width=LINE)
    c.polygon(_rect(cx, base - 0.10, 0.11, 0.20), fill=LEATHER, outline=INK, width=LINE * 0.8)


def _lightbulb(c, hand, side):
    cx, cy = hand[0], hand[1] - 0.40
    for ang in range(200, 341, 35):
        rad = math.radians(ang)
        c.stroke([(cx + 0.29 * math.cos(rad), cy + 0.29 * math.sin(rad)),
                  (cx + 0.38 * math.cos(rad), cy + 0.38 * math.sin(rad))], 0.03, GOLD)
    c.polygon(_rect(cx, cy + 0.24, 0.16, 0.14), fill=BULB_BASE, outline=INK, width=LINE)
    c.circle((cx, cy), 0.21, fill=BULB, outline=INK, width=LINE)
    c.arc((cx, cy), (0.12, 0.12), 200, 260, PAPER, 0.03)


# name -> (draw function, what it is for). The description is what `fv.py props` prints.
LIBRARY = {
    "phone":     (_phone,     "smartphone, screen lit. Calls, apps, texting, scrolling listings"),
    "keys":      (_keys,      "key ring hanging from the hand. Closing day, handover, access"),
    "cash":      (_cash,      "fan of banknotes. Rent, commission, profit, a deposit"),
    "contract":  (_contract,  "a page with ruled lines and a signature line. Lease, offer, terms"),
    "coffee":    (_coffee,    "takeaway cup. The grind, early mornings, a casual meeting"),
    "briefcase": (_briefcase, "leather case carried low. Lawyer, investor, going to work"),
    "magnifier": (_magnifier, "magnifying glass held up. Inspection, fine print, due diligence"),
    "sign":      (_sign,      "blank red yard sign on a post. For sale, sold, open house"),
    "house":     (_house,     "small model house on the palm. The property, the asset, the deal"),
    "lightbulb": (_lightbulb, "glowing bulb held up. The idea, the fix, the realisation"),
}
HANDS = ("r", "l")


def names():
    return list(LIBRARY)


def resolve(spec):
    """A figure block's "prop" is a name or {"name": ..., "hand": "r"|"l"}. Returns
    (name, hand), or None when there is no prop. Raises ValueError on anything unknown."""
    if not spec:
        return None
    name, hand = (spec, "r") if isinstance(spec, str) else (spec.get("name"), spec.get("hand", "r"))
    if name not in LIBRARY:
        raise ValueError(f"unknown prop '{name}' (have: {', '.join(LIBRARY)})")
    if hand not in HANDS:
        raise ValueError(f"prop hand must be 'r' or 'l', got '{hand}'")
    return name, hand


SCALE = 1.3    # props were drawn at life size and read too small at full-figure framing


class _Scaled:
    """The canvas, but every point is pushed away from the hand by SCALE and every size
    grows with it. Lets the prop functions stay in plain life-size numbers."""

    def __init__(self, canvas, pivot, k):
        self._c, self._p, self._k = canvas, pivot, k

    def _pt(self, point):
        return (self._p[0] + (point[0] - self._p[0]) * self._k,
                self._p[1] + (point[1] - self._p[1]) * self._k)

    def polygon(self, points, fill=None, outline=None, width=LINE):
        self._c.polygon([self._pt(q) for q in points], fill=fill, outline=outline,
                        width=width * self._k)

    def circle(self, centre, radius, fill=None, outline=None, width=LINE):
        self._c.circle(self._pt(centre), radius * self._k, fill=fill, outline=outline,
                       width=width * self._k)

    def stroke(self, points, width, colour):
        self._c.stroke([self._pt(q) for q in points], width * self._k, colour)

    def arc(self, centre, radii, start, end, colour, width):
        self._c.arc(self._pt(centre), (radii[0] * self._k, radii[1] * self._k), start, end,
                    colour, width * self._k)


def draw(canvas, name, hand_point, side):
    LIBRARY[name][0](_Scaled(canvas, hand_point, SCALE), hand_point, side)
