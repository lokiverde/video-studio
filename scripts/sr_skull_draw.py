"""Skull drawing for sr_skull: turn the drawing to match the head, blur the head under it,
and composite it onto a frame.

The drawing is a front view, so it turns the way a mask on a turned head does: a card in
perspective, its far side narrower and shorter, slid toward the face. Wrapping it round a
head shape was tried and dropped: the sides of the skull are not in the drawing, so they
stretched into blank bone. The head under the skull is blurred (person matte only, so the
background stays sharp), so the back of the head, a cap brim or an ear past the drawing reads
as soft shadow instead of a face.
"""
import math

import cv2
import numpy as np

TURN_MAX = math.radians(50)
TILT_MAX = math.radians(25)
NOSE_REACH = 1.05        # nose tip from the head's axis, in head half-widths
EAR_NEUTRAL = 0.12       # nose above the ears, in head half-widths, when looking level
EYE_NEUTRAL = 0.35       # nose below the eyes, same units, when looking level
PERSPECTIVE = 2.5        # camera distance for the card, in drawing widths
FACE_SHIFT = 0.6         # how far the card slides toward the face, in head half-widths * sin(yaw)
CARD_TURN = 0.75         # share of the head's turn the card takes: a full turn narrows it so far
                         # the cheek and ear show beside it
BLUR_REACH = 0.18        # blur past the drawing's edge, as a share of the skull's width
BLUR_SIGMA = 0.05        # blur strength, same units
STILL = math.radians(2)  # below this the drawing is used as drawn


def _disc(r):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def texture(img):
    """The drawing as sr_skull hands it round (a dict, so cached prep can be added later)."""
    return {"img": img}


def head_turn(j, x, head_w, w, h, joint, conf):
    """(yaw, tilt) radians from the pose: yaw > 0 faces image right, tilt > 0 looks up."""
    nose = joint(j, "head_joint", conf)
    if not nose:
        return 0.0, 0.0
    r = head_w / 2
    yaw = math.asin(max(-1.0, min(1.0, (nose[0] * w - x) / r / NOSE_REACH)))
    ears = [p for p in (joint(j, k, 0.4) for k in ("left_ear_joint", "right_ear_joint")) if p]
    eyes = [p for p in (joint(j, k, conf) for k in ("left_eye_joint", "right_eye_joint")) if p]
    if ears:
        lift = (np.mean([p[1] for p in ears]) - nose[1]) * h / r - EAR_NEUTRAL
    elif eyes:
        lift = (EYE_NEUTRAL - (nose[1] - np.mean([p[1] for p in eyes])) * h / r) * 1.5
    else:
        lift = 0.0
    tilt = math.asin(max(-1.0, min(1.0, lift)))
    return max(-TURN_MAX, min(TURN_MAX, yaw)), max(-TILT_MAX, min(TILT_MAX, tilt))


def turn(img, anchor, yaw, tilt):
    """(RGBA, anchor in its pixels) of the drawing turned like a card: yaw > 0 takes its right
    edge away from the camera, tilt > 0 its top. Pixels keep the drawing's scale."""
    h, w = img.shape[:2]
    if abs(yaw) < STILL and abs(tilt) < STILL:
        return img, (anchor[0] * w, anchor[1] * h)
    f = PERSPECTIVE * w

    def project(px, py):
        x, y = px - w / 2, py - h / 2
        k = f / (f + x * math.sin(yaw) - y * math.sin(tilt))
        return x * math.cos(yaw) * k, y * math.cos(tilt) * k

    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([project(*pt) for pt in src])
    lo = dst.min(0)
    size = tuple(int(math.ceil(v)) for v in dst.max(0) - lo)
    card = cv2.warpPerspective(img, cv2.getPerspectiveTransform(src, dst - lo), size,
                               flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                               borderValue=(0, 0, 0, 0))
    ax, ay = project(anchor[0] * w, anchor[1] * h)
    return card, (ax - lo[0], ay - lo[1])


def draw(frame, tex, anchor, scale_w, place, person=None, turned=True, blur=True):
    """Composite the skull onto the frame at place = (x, y, head width, roll, yaw, tilt).
    person: the person matte (0..1, frame size) for the blur, or None to blur without it."""
    x, y, head_w, roll = place[:4]
    yaw, tilt = (place[4], place[5]) if turned and len(place) > 5 else (0.0, 0.0)
    s = head_w * scale_w / tex["img"].shape[1]
    img, (ax, ay) = turn(tex["img"], anchor, yaw * CARD_TURN, tilt * CARD_TURN)
    sh, sw = img.shape[:2]
    x += head_w / 2 * math.sin(yaw) * FACE_SHIFT          # the face is forward of the head's axis
    m = cv2.getRotationMatrix2D((ax, ay), -math.degrees(roll), s)
    m[0, 2] += x - ax
    m[1, 2] += y - ay
    corners = np.array([[0, 0, 1], [sw, 0, 1], [0, sh, 1], [sw, sh, 1]], float) @ m.T
    pad = int(BLUR_REACH * sw * s) if blur else 0
    fh, fw = frame.shape[:2]
    x0, y0 = (np.floor(corners.min(0)).astype(int) - pad)
    x1, y1 = (np.ceil(corners.max(0)).astype(int) + pad)
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(fw, x1), min(fh, y1)
    if x1 <= x0 or y1 <= y0:
        return frame
    m[0, 2] -= x0
    m[1, 2] -= y0
    patch = cv2.warpAffine(img, m, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR,
                           borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    alpha = patch[..., 3:4].astype(np.float32) / 255
    out = frame.copy()
    region = out[y0:y1, x0:x1].astype(np.float32)
    if blur:
        k = max(3, pad)
        reach = cv2.dilate((alpha[..., 0] > 0.05).astype(np.uint8), _disc(k)).astype(np.float32)
        mask = cv2.GaussianBlur(reach, (0, 0), k / 3)
        if person is not None:
            mask *= cv2.dilate(person[y0:y1, x0:x1], _disc(max(1, k // 4)))
        soft = cv2.GaussianBlur(region, (0, 0), max(2.0, BLUR_SIGMA * sw * s))
        region = region * (1 - mask[..., None]) + soft * mask[..., None]
    out[y0:y1, x0:x1] = (region * (1 - alpha) + patch[..., :3] * alpha).astype(np.uint8)
    return out
