"""capqc: the caption is whatever differs between a captions-on and a captions-off render.
Synthetic frames pin the two judgments: a caption over the mouth-to-chin zone, and light
text that does not stand out from what is around it. Negative controls first: each check
must FAIL on a frame built to fail, not just pass the good ones."""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import capqc  # noqa: E402

W, H = 200, 300
FACE = {"face": [0.25, 0.2, 0.5, 0.4], "lips": [0.4, 0.5, 0.2, 0.04], "chin": 0.6}   # mouth y 150..180


def frame(bg):
    return np.full((H, W, 3), bg, dtype=np.uint8)


def with_text(img, y0, y1, color=(255, 255, 255), box=None):
    """Draw caption 'letters' (vertical bars) on rows y0..y1, optionally on a box."""
    out = img.copy()
    if box is not None:
        out[y0 - 6:y1 + 6, 20:180] = box
    for x in range(30, 170, 8):
        out[y0:y1, x:x + 3] = color
    return out


def test_mask_is_exactly_what_changed():
    off = frame(90)
    on = with_text(off, 100, 120)
    mask = capqc.caption_mask(on, off)
    assert mask[110, 31] and not mask[110, 34] and not mask[50, 50]


def test_caption_over_the_mouth_is_a_problem_in_the_opening():
    off = frame(90)
    problems = capqc.frame_problems(1.0, with_text(off, 155, 175), off, [FACE])
    assert any("mouth" in p and "opening" in p for p in problems)


def test_caption_below_the_chin_is_fine():
    off = frame(90)
    problems = capqc.frame_problems(1.0, with_text(off, 230, 250), off, [FACE])
    assert not any("mouth" in p for p in problems)


def test_tiny_faces_are_not_the_speaker():
    off = frame(90)
    small = {**FACE, "face": [0.4, 0.2, 0.04, 0.05]}
    assert not any("mouth" in p for p in capqc.frame_problems(9.0, with_text(off, 155, 175), off, [small]))


def test_white_text_on_a_light_wall_is_hard_to_read():
    off = frame(215)
    problems = capqc.frame_problems(9.0, with_text(off, 230, 250, color=(255, 255, 255)), off, [])
    assert any("hard to read" in p for p in problems)


def test_gold_on_a_light_wall_is_hard_to_read():
    off = frame(200)
    problems = capqc.frame_problems(9.0, with_text(off, 230, 250, color=(245, 197, 66)), off, [])
    assert any("hard to read" in p for p in problems)


def test_white_text_in_a_dark_box_reads_on_any_background():
    off = frame(240)
    on = with_text(off, 230, 250, box=(15, 32, 50))
    assert capqc.frame_problems(9.0, on, off, []) == []


def test_white_text_on_dark_footage_reads():
    off = frame(40)
    assert capqc.frame_problems(9.0, with_text(off, 230, 250), off, []) == []


def test_frame_without_a_caption_is_skipped():
    off = frame(90)
    assert capqc.frame_problems(1.0, off.copy(), off, [FACE]) == []


def test_pick_frames_covers_the_opening_layout_moments_and_spreads_the_rest():
    caps = [{"s": i * 2.0, "e": i * 2.0 + 1.8, "t": "x"} for i in range(100)]
    frames = capqc.pick_frames(caps, moments=[50.5, 120.2], max_frames=30)
    # every 5th frame of the opening while a caption is up (1.8 to 2.0 s has none)
    assert set(range(0, 76, 5)) - {55} <= set(frames) and 55 not in frames
    assert round(50.5 * 30) in frames and round(120.2 * 30) in frames
    assert len(frames) <= 30 and max(frames) > 150 * 30


def test_pick_frames_skips_times_with_no_caption():
    caps = [{"s": 5.0, "e": 6.0, "t": "x"}]
    assert capqc.pick_frames(caps, moments=[1.0]) == [153]
