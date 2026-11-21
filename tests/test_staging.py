"""Staging: camera framing, a drawn supporting cast, two-shots, and held backgrounds.
These are what let a shot act out the sentence instead of standing next to it."""
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import common  # noqa: E402
import composite  # noqa: E402
import gen_images  # noqa: E402

FRAME = (1280, 720)


def _bg(colour=(200, 190, 170)):
    return Image.new("RGB", FRAME, colour)


def test_closeup_fills_the_frame_with_his_head():
    wide, _ = composite.render_figure({"pose": "stand", "shot": "wide"}, FRAME)
    close, _ = composite.render_figure({"pose": "stand", "shot": "closeup"}, FRAME)
    assert close.height > FRAME[1]          # runs off the bottom: head and shoulders
    assert wide.height < FRAME[1] * 0.5


def test_explicit_height_beats_the_shot_preset():
    art, _ = composite.render_figure({"pose": "stand", "shot": "closeup", "height": 0.5}, FRAME)
    assert art.height < FRAME[1]


def test_unknown_shot_is_rejected():
    with pytest.raises(ValueError):
        composite.render_figure({"pose": "stand", "shot": "dutch"}, FRAME)


@pytest.mark.parametrize("who", ["stick-man", "gray", "curly"])
def test_cast_members_render_and_differ(who):
    art, _ = composite.render_figure({"pose": "stand", "who": who}, FRAME)
    hero, _ = composite.render_figure({"pose": "stand"}, FRAME)
    assert (art.tobytes() == hero.tobytes()) == (who == "stick-man")


def test_unknown_cast_member_is_rejected():
    with pytest.raises(ValueError):
        composite.render_figure({"pose": "stand", "who": "bob"}, FRAME)


def test_two_shot_pastes_both_figures():
    one = composite.place(_bg(), {"pose": "stand", "x": 0.3})
    two = composite.place(_bg(), [{"pose": "stand", "x": 0.3},
                                  {"pose": "shrug", "x": 0.7, "who": "gray", "flip": True}])
    assert one.tobytes() != two.tobytes()
    # left half is identical: the second figure only touched the right
    box = (0, 0, FRAME[0] // 2, FRAME[1])
    assert one.crop(box).tobytes() == two.crop(box).tobytes()


def test_portrait_figure_maps_over_a_cast():
    out = composite.portrait_figure([{"pose": "stand", "x": 0.2}, {"pose": "stand", "x": 0.8}])
    assert isinstance(out, list) and len(out) == 2
    assert all(f["ground"] == composite.PORTRAIT_GROUND for f in out)


def test_shot_specs_carry_hold_and_punch():
    scene = {"id": 1, "shots": [
        {"prompt": "a kitchen", "figure": {"pose": "stand"}},
        {"hold": True, "punch": 1.4, "figure": {"pose": "stand", "shot": "closeup"}}]}
    specs = common.shot_specs(scene)
    assert specs[0]["hold"] is False
    assert specs[1]["hold"] is True and specs[1]["punch"] == 1.4


def _scenes(shots):
    return {"scenes": [{"id": i, "narration": "n", "caption": "c", "shots": shots if i == 1 else ["a room"]}
                       for i in (1, 2, 3)]}


def test_a_held_shot_needs_no_prompt():
    common.validate_scenes(_scenes([{"prompt": "a kitchen"}, {"hold": True, "figure": {"pose": "stand"}}]))


def test_the_first_shot_of_a_video_cannot_hold():
    with pytest.raises(SystemExit):
        common.validate_scenes(_scenes([{"hold": True, "figure": {"pose": "stand"}}]))


def test_a_figure_list_is_validated_per_member():
    with pytest.raises(SystemExit):
        common.validate_scenes(_scenes([{"prompt": "a room", "figure": [{"pose": "stand"}, {"x": 0.5}]}]))


def test_punch_in_keeps_the_canvas_and_changes_the_picture():
    bg = _bg()
    for x in range(0, FRAME[0], 40):
        bg.paste((20, 20, 20), (x, 0, x + 8, FRAME[1]))
    out = gen_images.punch_in(bg, 1.5, 0.5)
    assert out.size == bg.size and out.tobytes() != bg.tobytes()
    assert gen_images.punch_in(bg, 1.0, 0.5) is bg


@pytest.mark.parametrize("bad", [0.9, 3.0])
def test_punch_out_of_range_is_rejected(bad):
    with pytest.raises(ValueError):
        gen_images.punch_in(_bg(), bad, 0.5)


def test_contact_sheet_orders_shot_ten_after_shot_two():
    from pathlib import Path as P
    names = ["scene_02_10.png", "scene_02_2.png", "scene_02.png", "scene_10.png", "scene_03.png"]
    ordered = sorted((P(n) for n in names), key=gen_images._shot_order)
    assert [p.name for p in ordered] == ["scene_02.png", "scene_02_2.png", "scene_02_10.png",
                                         "scene_03.png", "scene_10.png"]
