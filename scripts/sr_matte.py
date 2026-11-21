"""Storyboard reel: cutout and image prep. Matte repair around the feet, defringing,
the one-time upscale, the white-keyed logo, the blanked shirt, and the measurements that
line two poses up on one scale and centre line.

Arrays are float RGB(A) in 0..1 unless a function says uint8."""
import cv2
import numpy as np
from PIL import Image

# Pixels that count as the prop's light, per preset (Wizard: a pink crystal orb).
LIGHT_PRESETS = {
    "magenta": lambda rgb: (rgb[..., 0] > 0.7) & (rgb[..., 2] > 0.7) & (rgb[..., 1] < 0.68),
}


def load_rgba(path):
    return np.asarray(Image.open(path).convert("RGBA")).astype(np.float32) / 255.0


def crop_alpha(rgba):
    ys, xs = np.nonzero(rgba[..., 3] > 0.04)
    return rgba[ys.min():ys.max() + 1, xs.min():xs.max() + 1]


# ---------- feet repair (uint8 arrays, source render and its rembg cutout) ----------

def _rebuild(rgb, cut, box):
    """Rebuild alpha in the box from the source: robe red and lit bone become solid,
    shaded bone keeps what rembg kept, the pale floor and its shadow go."""
    x0, y0, x1, y1 = box
    z = rgb[y0:y1, x0:x1]
    a = cut[y0:y1, x0:x1, 3].astype(np.float32) / 255
    lum = z.mean(axis=2)
    chroma = z.max(axis=2) - z.min(axis=2)
    floor = np.median(lum[(a < 0.05) & (chroma < 14)])
    red = z[..., 0] - z[..., 2] > 30
    pale = (lum > floor + 14) & (chroma < 60)
    shade = (z[..., 2] - z[..., 0] > 12) & (lum > floor - 55) & (a > 0.3)
    new = np.where(red | pale | shade, np.maximum(a, (red | pale).astype(np.float32)), 0.0)
    cut[y0:y1, x0:x1, 3] = (new * 255).astype(np.uint8)


def _add(rgb, cut, box, lum, chroma):
    """Pale source pixels in the box (bone rembg dropped on a pale floor) become opaque."""
    x0, y0, x1, y1 = box
    floor = np.median(lum[y1:y1 + 15, x0:x1])
    pale = (lum[y0:y1, x0:x1] > floor + 12) & (chroma[y0:y1, x0:x1] < 60)
    region = cut[y0:y1, x0:x1]
    region[pale, :3] = rgb[y0:y1, x0:x1][pale]
    region[pale, 3] = 255


def _drop(rgb, cut, box, lum):
    """Dark, non-red floor shadow in the box (rembg kept the cast shadow) becomes clear."""
    x0, y0, x1, y1 = box
    z = rgb[y0:y1, x0:x1]
    floor = np.median(lum[y1:y1 + 15, x0:x1])
    region = lum[y0:y1, x0:x1]
    shadow = (region < floor - 18) & (z[..., 0] - z[..., 2] < 12) & (region < 120)
    cut[y0:y1, x0:x1, 3][shadow] = 0


def repair_feet(src_rgb, cut_rgba, spec):
    """Return a repaired copy of a rembg cutout. spec: {rebuild|add|drop: [x0, y0, x1, y1]}
    in source pixels, applied rebuild, add, drop."""
    rgb = np.asarray(src_rgb)[..., :3].astype(np.int32)
    cut = np.array(cut_rgba, dtype=np.uint8, copy=True)
    lum = rgb.mean(axis=2)
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    if spec.get("rebuild"):
        _rebuild(rgb, cut, spec["rebuild"])
    if spec.get("add"):
        _add(rgb, cut, spec["add"], lum, chroma)
    if spec.get("drop"):
        _drop(rgb, cut, spec["drop"], lum)
    return cut


# ---------- figure prep ----------

def defringe(rgba):
    """Pull edge colour in from the solid interior (kills the pale studio-sky fringe a
    glow would light up) and shave one pixel off the matte."""
    a = rgba[..., 3]
    solid = (a > 0.97).astype(np.float32)
    num = cv2.GaussianBlur(rgba[..., :3] * solid[..., None], (0, 0), 3)
    den = cv2.GaussianBlur(solid, (0, 0), 3)[..., None]
    bleed = num / np.maximum(den, 1e-4)
    rgb = np.where((a[..., None] < 0.97) & (den > 1e-3), bleed, rgba[..., :3])
    return np.dstack([rgb, cv2.erode(a, np.ones((3, 3), np.uint8))])


def master(rgba, tint, factor=2.0):
    """Upscale once (Lanczos + light unsharp, softened matte steps) so per-frame sizes
    only ever shrink. The tint cools a studio-lit render toward the plate."""
    h, w = rgba.shape[:2]
    big = cv2.resize(defringe(rgba), (int(w * factor), int(h * factor)), interpolation=cv2.INTER_LANCZOS4)
    blur = cv2.GaussianBlur(big[..., :3], (0, 0), 1.6)
    big[..., :3] = np.clip(big[..., :3] * 1.35 - blur * 0.35, 0, 1) * np.asarray(tint, np.float32)
    big[..., 3] = cv2.GaussianBlur(big[..., 3], (0, 0), 1.0)
    return np.clip(big, 0, 1)


def dolly_figure(rgba, tint):
    """Cropped cutout for a dolly shot. Its centre is the alpha-weighted column mean, so a
    staff held out to one side does not pull the figure off centre."""
    rgba = crop_alpha(rgba)
    cols = rgba[..., 3].sum(axis=0)
    cx = float((cols * np.arange(len(cols))).sum() / cols.sum()) / rgba.shape[1]
    return {"img": master(rgba, tint), "cx": cx}


def _body_mask(rgb, a, centre_on):
    if centre_on == "alpha":
        return a > 0.5
    return (a > 0.5) & (rgb[..., 0] - rgb[..., 2] > 0.16) & (rgb[..., 0] > 0.35)   # "red": the robe


def pose_figure(rgba, tint, centre_on="red"):
    """Uncropped cutout plus where its body sits, so poses from separate renders share
    one scale and centre line: centre = mean column of the body (the red robe by default),
    height = top of the body (the hood) to the lowest opaque pixel (the feet)."""
    rgb, a = rgba[..., :3], rgba[..., 3]
    ys, xs = np.nonzero(_body_mask(rgb, a, centre_on))
    feet = np.nonzero(a > 0.5)[0].max()
    return {"img": master(rgba, tint), "src_w": rgba.shape[1], "src_h": rgba.shape[0],
            "cx": float(xs.mean()), "feet": float(feet), "body": float(feet - ys.min())}


def find_light(fig, light):
    """(x, y, r) of the prop's light as fractions of the figure box: `at` when given,
    otherwise the pixels matching the `find` preset."""
    if light.get("at"):
        return tuple(light["at"])
    rgb, a = fig["img"][..., :3], fig["img"][..., 3]
    ys, xs = np.nonzero(LIGHT_PRESETS[light.get("find", "magenta")](rgb) & (a > 0.5))
    if not len(xs):
        raise ValueError("no light pixels found, set the glow shot's light.at [x, y, r] by hand")
    h, w = a.shape
    return xs.mean() / w, ys.mean() / h, np.sqrt(len(xs) / np.pi) / h


# ---------- logo and shirt ----------

def white_keyed(path):
    """Logo on white -> RGBA with the white removed and edges un-premultiplied."""
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.float32) / 255.0
    a = np.clip((1.0 - rgb.min(axis=2)) * 1.15, 0, 1)
    fg = (rgb - (1 - a[..., None])) / np.maximum(a[..., None], 1e-3)
    return crop_alpha(np.dstack([np.clip(fg, 0, 1), a]))


def blank_shirt(rgb, box):
    """Paint the print out of the shirt photo so the design can fade in on it. The whole
    print box goes, not just its bright pixels: dark parts of a design differ from the
    fabric too and leave a ghost. box = [x0, y0, x1, y1] fractions of the photo."""
    img = (rgb * 255).astype(np.uint8)
    h, w = img.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    mask[int(h * box[1]):int(h * box[3]), int(w * box[0]):int(w * box[2])] = 255
    out = cv2.inpaint(img, mask, 15, cv2.INPAINT_TELEA)
    soft = cv2.GaussianBlur(out, (0, 0), 14)
    grain = np.random.default_rng(7).normal(0, 1.6, out.shape)
    m = cv2.GaussianBlur(mask, (0, 0), 10)[..., None] / 255.0
    return np.clip(out * (1 - m) + (soft + grain) * m, 0, 255).astype(np.float32) / 255.0
