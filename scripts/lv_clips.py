"""City b-roll clips (Tony's own footage) decoded once to frame-accurate JPEGs at the
exact output size, so the renderer can read any frame at random (previews) or in order
(encode) without holding whole clips in memory.

Every clip gets the same light grade (a touch more contrast and colour) so overcast
morning footage and bright midday footage cut together.
"""
import hashlib
import subprocess
from pathlib import Path

import cv2
import numpy as np

GRADE = "eq=contrast=1.08:saturation=1.18:gamma=1.02"
FPS = 30


def prepare(src: Path, start: float, seconds: float, out_size, cache_dir: Path) -> Path:
    """Cover-crop, grade, and dump `seconds` from `start` as JPEG frames. Cached by inputs."""
    w, h = out_size
    key = hashlib.sha1(f"{src}|{start}|{seconds}|{w}x{h}|{GRADE}".encode()).hexdigest()[:12]
    folder = cache_dir / f"{src.stem}-{key}"
    if folder.is_dir() and any(folder.glob("*.jpg")):
        return folder
    folder.mkdir(parents=True, exist_ok=True)
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},{GRADE},fps={FPS}"
    cmd = ["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{seconds + 0.2:.3f}",
           "-i", str(src), "-vf", vf, "-q:v", "3", str(folder / "%04d.jpg")]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as err:
        raise RuntimeError(f"could not decode {src.name}: {err.stderr.strip()[:300]}") from err
    return folder


class Clip:
    """Frames of one prepared clip. frame(t) for t seconds into the clip, with a slow push."""

    def __init__(self, folder: Path, push: float = 0.05):
        self.files = sorted(folder.glob("*.jpg"))
        if not self.files:
            raise RuntimeError(f"no frames in {folder}")
        self.push = push

    def frame(self, t: float, p: float) -> np.ndarray:
        i = min(len(self.files) - 1, max(0, int(t * FPS)))
        img = cv2.cvtColor(cv2.imread(str(self.files[i])), cv2.COLOR_BGR2RGB)
        if not self.push:
            return img
        h, w = img.shape[:2]
        z = 1 + self.push * p
        m = np.float32([[z, 0, (1 - z) * w / 2], [0, z, (1 - z) * h / 2]])
        return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
