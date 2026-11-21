"""Faces, mouths, body pose and subject cutouts, on any OS.

On a Mac the Swift tools (scripts/facedetect.swift, mouthdetect.swift, bodytrack.swift and
tools/segment_subject.swift) run Apple Vision: fast, on-device, the reference. Everywhere
else the same calls fall back to open models that pip installs: OpenCV's YuNet face model
(faces and mouths), MediaPipe pose (body joints and the person matte) and rembg (cutouts).
Each call returns the exact JSON shape its Swift tool prints, so callers never know which
ran. The open models download once into ~/video-studio/models.

Known gap off a Mac: YuNet finds faces only, not the upper-body "head" boxes Apple Vision
adds for people turned away, so face blur may miss the back of a head. Check the blur sheet.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import common
import platform_util

BIN = common.ROOT / "bin"
MODELS = platform_util.STUDIO_HOME / "models"
YUNET_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx")
POSE_URL = ("https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
            "pose_landmarker_full/float16/latest/pose_landmarker_full.task")
SEGMENT_SRC = common.ROOT / "tools" / "segment_subject.swift"
MIN_CONF = 0.5          # pose
FACE_CONF = 0.6         # YuNet: 0.5 let tiny false faces through on tile scans
MAX_PEOPLE = 4
REMBG_PY = platform_util.venv_python(platform_util.studio_venv("rembg"))
REMBG_SCRIPT = """
import sys
from pathlib import Path
from rembg import new_session, remove
from PIL import Image
session = new_session("isnet-general-use")
for src, out in zip(sys.argv[1::2], sys.argv[2::2]):
    img = Image.open(src).convert("RGB")
    remove(img, session=session, post_process_mask=True).save(out)
    print("cut", Path(src).name, flush=True)
"""

# MediaPipe pose landmark index -> the Apple Vision joint name the callers read.
POSE_JOINTS = {
    0: "head_joint", 2: "left_eye_joint", 5: "right_eye_joint", 7: "left_ear_joint", 8: "right_ear_joint",
    11: "left_shoulder_1_joint", 12: "right_shoulder_1_joint", 13: "left_forearm_joint",
    14: "right_forearm_joint", 15: "left_hand_joint", 16: "right_hand_joint", 23: "left_upLeg_joint",
    24: "right_upLeg_joint", 25: "left_leg_joint", 26: "right_leg_joint", 27: "left_foot_joint",
    28: "right_foot_joint",
}


def use_swift() -> bool:
    """True on a Mac with the Swift toolchain (Xcode or the Command Line Tools)."""
    return platform_util.IS_MAC and shutil.which("swiftc") is not None


def swift_tool(name: str, src: Path | None = None) -> Path:
    """bin/<name>, compiled from its .swift source when missing or older than the source."""
    src = src or common.ROOT / "scripts" / f"{name}.swift"
    out = BIN / name
    if not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
        BIN.mkdir(exist_ok=True)
        subprocess.run(["swiftc", "-O", str(src), "-o", str(out)], check=True, capture_output=True)
    return out


def model_file(url: str) -> Path:
    """A model file from ~/video-studio/models, downloaded on first use."""
    path = MODELS / url.rsplit("/", 1)[-1]
    if not path.exists():
        MODELS.mkdir(parents=True, exist_ok=True)
        part = path.with_name(path.name + ".part")
        print(f"[vision] downloading {path.name} (one time)", flush=True)
        urllib.request.urlretrieve(url, part)
        part.replace(path)
    return path


def _need(module: str, pip_name: str):
    try:
        return __import__(module)
    except ImportError:
        sys.exit(f"[vision] this step needs {pip_name} off a Mac: pip install {pip_name}")


def _frames(folder: Path, exts: tuple[str, ...]) -> list[Path]:
    return sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in exts)


def tiles(n: int) -> list[tuple[float, float, float, float]]:
    """n x n overlapping tiles (x, y, w, h fractions), the same scan facedetect.swift does."""
    size = min(1.0, 1.5 / n)
    step = (1.0 - size) / (n - 1) if n > 1 else 0.0
    return [(i * step, j * step, size, size) for i in range(n) for j in range(n)]


def overlap(a: list[float], b: list[float]) -> float:
    """Intersection over the smaller box, so a face found whole and in a tile merges."""
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    return inter / max(1e-9, min(a[2] * a[3], b[2] * b[3]))


def merge(found: list[list[float]], limit: float = 0.4) -> list[list[float]]:
    """Highest confidence first, dropping any box that mostly overlaps one already kept."""
    kept: list[list[float]] = []
    for box in sorted(found, key=lambda b: -b[4]):
        if not any(overlap(k, box) > limit for k in kept):
            kept.append(box)
    return kept


def _yunet(cv2):
    return cv2.FaceDetectorYN.create(str(model_file(YUNET_URL)), "", (320, 320), FACE_CONF, 0.3, 5000)


def _faces_in(det, img) -> list[list[float]]:
    """YuNet rows: x, y, w, h, 5 landmarks (right eye, left eye, nose, right and left mouth corner), score."""
    h, w = img.shape[:2]
    det.setInputSize((w, h))
    _, rows = det.detect(img)
    return [] if rows is None else rows.tolist()


def _swift_json(args: list[str]) -> dict:
    return json.loads(subprocess.run(args, capture_output=True, text=True, check=True).stdout)


def detect_faces(folder: Path, grid: int = 4) -> dict:
    """{"frame.jpg": [[x, y, w, h, conf], ...]} for every .jpg in folder, fractions, origin top-left."""
    if use_swift():
        return _swift_json([str(swift_tool("facedetect")), str(folder), str(grid)])
    cv2 = _need("cv2", "opencv-python-headless")
    det, out = _yunet(cv2), {}
    for path in _frames(folder, (".jpg",)):
        img = cv2.imread(str(path))
        if img is None:
            continue
        H, W = img.shape[:2]
        found = []
        for tx, ty, tw, th in tiles(1) + tiles(2) + tiles(3) + (tiles(grid) if grid > 3 else []):
            x0, y0, x1, y1 = int(tx * W), int(ty * H), int((tx + tw) * W), int((ty + th) * H)
            for f in _faces_in(det, img[y0:y1, x0:x1]):
                found.append([(x0 + f[0]) / W, (y0 + f[1]) / H, f[2] / W, f[3] / H, f[14]])
        out[path.name] = merge(found)
    return out


def mouth_of(row: list[float], W: int, H: int) -> dict:
    """One YuNet row -> {"face", "lips", "chin"} as mouthdetect.swift reports them. Pure."""
    x, y, w, h = row[:4]
    rmx, rmy, lmx, lmy = row[10:14]
    mw = abs(lmx - rmx) or w * 0.4
    my = (rmy + lmy) / 2
    return {"face": [x / W, y / H, w / W, h / H],
            "lips": [min(rmx, lmx) / W, (my - 0.25 * mw) / H, mw / W, 0.5 * mw / H],
            "chin": min(1.0, (y + h) / H)}


def detect_mouths(folder: Path) -> dict:
    """{"frame.png": [{"face": [x,y,w,h], "lips": [x,y,w,h], "chin": y}, ...]} for every .png/.jpg."""
    if use_swift():
        return _swift_json([str(swift_tool("mouthdetect")), str(folder)])
    cv2 = _need("cv2", "opencv-python-headless")
    det, out = _yunet(cv2), {}
    for path in _frames(folder, (".png", ".jpg")):
        img = cv2.imread(str(path))
        if img is not None:
            H, W = img.shape[:2]
            out[path.name] = [mouth_of(r, W, H) for r in _faces_in(det, img)]
    return out


def joints_of(landmarks) -> dict:
    """MediaPipe pose landmarks -> {"head_joint": [x, y, conf], ...} with Apple Vision names. Pure."""
    joints = {}
    for i, name in POSE_JOINTS.items():
        p = landmarks[i]
        if 0.0 <= p.x <= 1.0 and 0.0 <= p.y <= 1.0:
            joints[name] = [float(p.x), float(p.y), float(getattr(p, "visibility", 1.0) or 0.0)]
    return joints


def track_bodies(folder: Path, mattes: Path) -> dict:
    """{"frame.jpg": [{joint: [x, y, conf]}, ...]} for every .jpg, plus <mattes>/<frame>.png person mattes."""
    if use_swift():
        return _swift_json([str(swift_tool("bodytrack")), str(folder), str(mattes)])
    cv2 = _need("cv2", "opencv-python-headless")
    mp = _need("mediapipe", "mediapipe")
    import numpy as np
    from mediapipe.tasks.python import BaseOptions
    from mediapipe.tasks.python import vision as mpv
    Path(mattes).mkdir(parents=True, exist_ok=True)
    opts = mpv.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(model_file(POSE_URL))),
        running_mode=mpv.RunningMode.IMAGE, num_poses=MAX_PEOPLE, output_segmentation_masks=True,
        min_pose_detection_confidence=MIN_CONF)
    out = {}
    with mpv.PoseLandmarker.create_from_options(opts) as marker:
        for path in _frames(folder, (".jpg",)):
            image = mp.Image.create_from_file(str(path))
            res = marker.detect(image)
            out[path.name] = [j for j in (joints_of(p) for p in res.pose_landmarks) if j]
            matte = np.zeros((image.height, image.width), np.float32)
            for m in res.segmentation_masks or []:
                matte = np.maximum(matte, m.numpy_view().reshape(matte.shape))
            cv2.imwrite(str(Path(mattes) / f"{path.stem}.png"), (matte * 255).clip(0, 255).astype(np.uint8))
    return out


def rembg_python() -> Path | None:
    """The interpreter with rembg: its own venv, else this Python if rembg was pip installed here."""
    if REMBG_PY.exists():
        return REMBG_PY
    if importlib.util.find_spec("rembg"):
        return Path(sys.executable)
    return None


REMBG_HINT = ("rembg missing: pip install \"rembg[cpu]\", or give it its own venv at "
              f"{REMBG_PY.parent.parent}")


def rembg_cutouts(pairs: list[tuple[Path, Path]]) -> None:
    """Cut out [(src, dst)] with rembg isnet in one model load (about 10 s a picture on CPU)."""
    if not pairs:
        return
    py = rembg_python()
    if py is None:
        raise RuntimeError(REMBG_HINT)
    subprocess.run([str(py), "-c", REMBG_SCRIPT, *[str(p) for pair in pairs for p in pair]], check=True)


def subject_cutout(src: Path, dst: Path) -> tuple[bool, str]:
    """The main subject of a picture lifted onto transparency at dst. Apple Vision on a Mac,
    rembg elsewhere. Returns (ok, why-not)."""
    if platform_util.IS_MAC and shutil.which("swift"):
        done = subprocess.run(["swift", str(SEGMENT_SRC), str(src), str(dst)],
                              capture_output=True, text=True, timeout=300)
        ok = done.returncode == 0 and Path(dst).exists()
        return ok, "" if ok else (done.stdout + done.stderr).strip()[:160]
    if rembg_python() is None:
        return False, REMBG_HINT
    try:
        rembg_cutouts([(Path(src), Path(dst))])
    except subprocess.CalledProcessError as exc:
        return False, f"rembg failed ({exc.returncode})"
    return Path(dst).exists(), ""
