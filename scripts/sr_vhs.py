"""Storyboard reel: the VHS tape pass (Tony, 2026-10-18, first on the Shop Wizard).

One strength number scales every part, so 0.5 reads like the overlay at half opacity in
an editor: colour bleed, luma softening, RGB split, a tracking band rolling up the frame,
head-switch tearing along the bottom edge, scanlines, grain, vignette, flicker, and a
PLAY readout over the opening. Where it applies (the character section, fading out across
the white) is sr_lib.vhs_mix. Ported from jobs/20261017-222408-wizard/wizard_ad.py.

scripts/vhs_look.py (the `vhs-look` skill) drives this pass over finished videos, so
keep its surface stable or update it there too: make({strength, osd, osd_end}) -> callable
(float RGB frame, t) -> frame; CRF, MAXRATE, BUFSIZE; sr_shots.W, H. Tests: test_vhs_look.py."""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from sr_shots import FPS, H, W, over

# Menlo Bold on the Macs (the look Tony approved); the bundled face keeps Linux CI rendering.
OSD_FONTS = [(Path("/System/Library/Fonts/Menlo.ttc"), 1), (Path("C:/Windows/Fonts/consolab.ttf"), 0),
             (Path(__file__).resolve().parent.parent / "assets/fonts/DejaVuSans-Bold.ttf", 0)]
CRF = 18                       # the grain makes x264 spend bits; cap it
MAXRATE, BUFSIZE = "14M", "28M"   # grain would otherwise push ~35 Mbps


def osd_font(size):
    for path, index in OSD_FONTS:
        if path.exists():
            return ImageFont.truetype(str(path), size, index=index)
    raise RuntimeError(f"no PLAY readout font: {OSD_FONTS[-1][0]} is missing (git checkout assets/fonts)")


class VHSPass:
    """cfg from sr_lib.vhs_config: strength, osd text, osd_end seconds."""

    def __init__(self, cfg):
        self.k = k = float(cfg["strength"])
        self.osd_end = cfg["osd_end"]
        yy, xx = np.mgrid[:H, :W].astype(np.float32)
        r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / np.sqrt(2)
        self.vignette = (1 - 0.6 * k * r ** 2.2)[..., None]
        rows = np.ones((H, 1, 1), np.float32)
        rows[::3] = 1 - 0.24 * k            # scanlines: one dark row in three
        rows[1::3] = 1 - 0.08 * k
        self.scan = rows
        self.osd = None
        if cfg["osd"]:
            im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((88, 236), cfg["osd"], fill=(255, 255, 255, 235),
                                    font=osd_font(58))
            self.osd = np.asarray(im).astype(np.float32) / 255.0

    def __call__(self, f, t):
        """The tape look over a float RGB frame at t seconds. Seeded per frame, so a re-render
        is identical."""
        k, i = self.k, int(round(t * FPS))
        rng = np.random.default_rng(1000 + i)
        ycc = cv2.cvtColor(f.astype(np.float32), cv2.COLOR_RGB2YCrCb)
        ycc[..., 1:] = cv2.blur(ycc[..., 1:], (1 + 2 * int(round(9 * k)), 1))      # colour bleed
        ycc[..., 0] = cv2.GaussianBlur(ycc[..., 0], (0, 0), sigmaX=0.3 + 1.1 * k, sigmaY=0.1 + 0.3 * k)
        f = cv2.cvtColor(ycc, cv2.COLOR_YCrCb2RGB)
        s = int(round(7 * k))                                                      # RGB split
        if s:
            f = np.dstack([np.roll(f[..., 0], s, axis=1), f[..., 1], np.roll(f[..., 2], -s, axis=1)])
        self._tracking(f, t, rng)
        f = f * self.scan
        grain = rng.normal(0, 0.075 * k, (H // 3, W // 3)).astype(np.float32)
        f = f + cv2.resize(grain, (W, H), interpolation=cv2.INTER_LINEAR)[..., None]
        f = f * self.vignette * (1 + 0.03 * k * np.sin(i * 2.3) + 0.015 * k * rng.standard_normal())
        if self.osd is not None and t < self.osd_end:
            over(f, self.osd, 0, 0, min(1.0, 2 * k))
        return f

    def _tracking(self, f, t, rng):
        """A band of skewed rows rolling up the frame every 6.5 s, plus head-switch
        tearing along the bottom edge. Edits f in place."""
        k = self.k
        bh = int(60 + 40 * k)
        y0 = int((1 - (t % 6.5) / 6.5) * (H + bh)) - bh
        amp = 6 + 22 * k
        for y in range(max(y0, 0), min(y0 + bh, H)):
            off = int(amp * (0.5 + 0.5 * rng.random()) * np.sin(np.pi * (y - y0) / bh))
            f[y] = np.roll(f[y], off, axis=0)
        a, b = max(y0, 0), min(y0 + bh, H)
        if b > a:
            f[a:b] += (rng.random((b - a, W, 1)) > 0.985) * 0.6 * k
        for y in range(H - int(14 + 16 * k), H):
            f[y] = np.roll(f[y], int(10 + 30 * k * rng.random()), axis=0)


def make(cfg):
    """A VHSPass when the job turns the look on, else None."""
    return VHSPass(cfg) if cfg["strength"] > 0 else None
