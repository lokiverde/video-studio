"""Depth-parallax camera moves on still photos (the "2.5D" look).

MiDaS v2.1 small (Intel ISL, ONNX, run through OpenCV's dnn module, no torch) gives
a relative depth map. Each output pixel is then pulled from the source with an
offset and scale that grow with nearness, so the foreground slides against the
background like a gimbal or drone move. No pixels are invented, which matters for
listings: the room is shown as photographed, only the camera moves.

Shifts stay small (a few percent of the frame) and the depth map is smoothed, so
the usual 2.5D tearing at object edges stays below what the eye catches in motion.
"""
from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np

import common

MODEL = common.ROOT / "assets" / "models" / "midas-v21-small.onnx"
MODEL_URL = "https://github.com/isl-org/MiDaS/releases/download/v2_1/model-small.onnx"
MARGIN = 1.04  # working image this much larger than the frame: room for the parallax shift only


@lru_cache(maxsize=1)
def _net():
    if not MODEL.exists():
        raise RuntimeError(f"depth model missing: curl -L -o {MODEL} {MODEL_URL}")
    return cv2.dnn.readNet(str(MODEL))


def estimate(rgb: np.ndarray) -> np.ndarray:
    """Depth 0 (far) to 1 (near) at the image's own size, smoothed for warping."""
    blob = cv2.dnn.blobFromImage(rgb[:, :, ::-1], 1 / 255.0, (256, 256),
                                 (123.675, 116.28, 103.53), swapRB=True, crop=False)
    net = _net()
    net.setInput(blob)
    d = net.forward()[0].astype(np.float32)
    d = (d - d.min()) / max(float(d.max() - d.min()), 1e-6)
    d = cv2.resize(d, (rgb.shape[1], rgb.shape[0]), interpolation=cv2.INTER_CUBIC)
    k = max(3, int(min(rgb.shape[:2]) * 0.02) | 1)
    return cv2.GaussianBlur(d, (k, k), 0)


@dataclass(frozen=True)
class Move:
    """A camera move. zoom: extra scale at the end for the nearest depth.
    pan: whole-frame travel as a fraction of frame width (depth independent).
    orbit/rise: depth-dependent sideways/vertical parallax, fraction of frame size."""
    zoom: float = 0.10
    pan: float = 0.0
    orbit: float = 0.0
    rise: float = 0.0
    ease: float = 2.2  # speed ramp: fast start settling into a slow drift


MOVES = {
    "dolly": Move(zoom=0.12),
    "orbit_r": Move(zoom=0.05, orbit=0.035),
    "orbit_l": Move(zoom=0.05, orbit=-0.035),
    "rise": Move(zoom=0.06, rise=-0.03),
    "pan_r": Move(zoom=0.03, pan=0.5, orbit=0.02),
    "pan_l": Move(zoom=0.03, pan=-0.5, orbit=-0.02),
}


def speed_ramp(p: float, ease: float) -> float:
    p = min(1.0, max(0.0, p))
    return 1 - (1 - p) ** ease


class Parallax:
    """One photo prepared for one frame size. frame(p) renders progress p in 0..1."""

    def __init__(self, rgb: np.ndarray, out_size, move: Move, focus: float = 0.5):
        w, h = out_size
        self.out_size = out_size
        self.move = move
        src_h, src_w = rgb.shape[:2]
        if move.pan:
            # Full height, full width kept so the pan can travel across the room.
            scale = h * MARGIN / src_h
        else:
            scale = max(w * MARGIN / src_w, h * MARGIN / src_h)
        size = (max(round(src_w * scale), int(w * MARGIN)), max(round(src_h * scale), int(h * MARGIN)))
        self.img = cv2.resize(rgb, size, interpolation=cv2.INTER_AREA)
        self.depth = estimate(self.img)
        self.cx = size[0] / 2
        if move.pan:
            slack = size[0] - w * 1.02
            self.cx = min(max(focus * size[0], w / 2 + 1), size[0] - w / 2 - 1)
            self.pan_span = min(slack, abs(move.pan) * slack * 2)
        # Landscape: focus places the frame vertically (0 top, 1 bottom); 0.35 keeps rooflines.
        self.cy = size[1] / 2 if move.pan else min(max(focus * size[1], h / 2), size[1] - h / 2)
        gx, gy = np.meshgrid(np.arange(w, dtype=np.float32) - w / 2, np.arange(h, dtype=np.float32) - h / 2)
        self.gx, self.gy = gx, gy

    def frame(self, p: float) -> np.ndarray:
        w, h = self.out_size
        m = self.move
        q = speed_ramp(p, m.ease)
        cx = self.cx
        if m.pan:
            direction = 1 if m.pan > 0 else -1
            cx = self.cx - direction * self.pan_span / 2 + direction * self.pan_span * q
            cx = min(max(cx, w / 2 + 1), self.img.shape[1] - w / 2 - 1)
        # Depth sampled at the destination position (backward-warp approximation, fine
        # for shifts this small once the depth map is smoothed).
        x0, y0 = int(round(cx - w / 2)), int(round(self.cy - h / 2))
        d = self.depth[y0:y0 + h, x0:x0 + w]
        if d.shape != (h, w):
            d = cv2.resize(d, (w, h))
        scale = 1 + m.zoom * q * (0.35 + 0.65 * d)
        off_x = m.orbit * w * q * (d - 0.5)
        off_y = m.rise * h * q * (d - 0.5)
        map_x = (cx + self.gx / scale - off_x).astype(np.float32)
        map_y = (self.cy + self.gy / scale - off_y).astype(np.float32)
        return cv2.remap(self.img, map_x, map_y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
