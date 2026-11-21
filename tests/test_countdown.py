"""Countdown format (theme chill-dude): number cards as shots, icon speech bubbles."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import cards  # noqa: E402
import common  # noqa: E402
import composite  # noqa: E402

FRAME = (1280, 720)


def test_card_is_the_canvas_size_and_mostly_background():
    img = cards.render({"number": 10, "title": "The lowball offer"}, FRAME)
    assert img.size == FRAME and img.mode == "RGB"
    assert img.getpixel((5, 5)) == (255, 255, 255)
    dark = sum(1 for px in img.resize((160, 90)).getdata() if sum(px) < 200)
    assert 0 < dark < 160 * 90 * 0.4


def test_a_bare_number_is_a_card():
    assert cards.render(7, FRAME).tobytes() != cards.render(8, FRAME).tobytes()


def test_card_colours_come_from_the_theme_style():
    img = cards.render(3, FRAME, {"bg": "#101014", "text": "#ffd60a"})
    assert img.getpixel((5, 5)) == (16, 16, 20)


def test_portrait_card_renders():
    assert cards.render({"number": 1, "title": "A very long title that has to wrap somewhere"},
                        (1088, 1920)).size == (1088, 1920)


@pytest.mark.parametrize("bad", [None, "", {"title": "no number"}, {"number": ""}])
def test_bad_cards_are_rejected(bad):
    with pytest.raises(ValueError):
        cards.render(bad, FRAME)


def _scenes(shots):
    return {"scenes": [{"id": i, "narration": "n", "caption": "c",
                        "shots": shots if i == 1 else ["a room"]} for i in (1, 2, 3)]}


def test_a_card_shot_needs_no_prompt():
    common.validate_scenes(_scenes([{"card": 10}, {"prompt": "a kitchen"}]))
    assert common.shot_specs({"id": 1, "shots": [{"card": 10}]})[0]["card"] == 10


def test_a_card_cannot_carry_a_figure():
    with pytest.raises(SystemExit):
        common.validate_scenes(_scenes([{"card": 10, "figure": {"pose": "stand"}}]))


def test_a_hold_skips_back_over_a_card():
    import gen_images
    data = _scenes([{"prompt": "a kitchen"}, {"card": 9}, {"hold": True, "figure": {"pose": "stand"}}])
    work = Path("/tmp/x")
    holds = gen_images.hold_sources(data, work)
    assert [p.name for p in holds.values()] == ["scene_01.png"]


@pytest.mark.parametrize("icon", ["x", "check", "question", "exclaim", "dollar", "heart", "zzz"])
def test_every_bubble_icon_changes_the_drawing(icon):
    plain, _ = composite.render_figure({"pose": "stand"}, FRAME)
    art, _ = composite.render_figure({"pose": "stand", "bubble": icon}, FRAME)
    assert art.tobytes() != plain.tobytes()


def test_unknown_bubble_is_rejected():
    with pytest.raises(ValueError, match="question"):
        composite.render_figure({"pose": "stand", "bubble": "skull"}, FRAME)
