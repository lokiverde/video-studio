"""Stick Man's expression vocabulary: moods resolve to a face, and every face draws."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import composite  # noqa: E402

DEADPAN_MOODS = ("deadpan", "skeptical", "smirk", "annoyed")


@pytest.mark.parametrize("mood", DEADPAN_MOODS)
def test_deadpan_moods_exist(mood):
    assert mood in composite.MOODS


def test_deadpan_is_half_lidded_and_flat():
    face = composite.resolve_face({"mood": "deadpan"}, {"face": {"mouth": "smile"}})
    assert face == {"mouth": "flat", "brows": "neutral", "eyes": "half"}


def test_mood_resets_eyes_left_by_an_earlier_default():
    face = composite.resolve_face({"mood": "happy"}, {"face": {"eyes": "half"}})
    assert face["eyes"] == "open"


def test_explicit_face_keys_override_mood():
    face = composite.resolve_face({"mood": "deadpan", "face": {"mouth": "smirk"}}, {})
    assert face["mouth"] == "smirk"
    assert face["eyes"] == "half"


@pytest.mark.parametrize("key,value", [("mouth", "grin"), ("brows", "wavy"), ("eyes", "shut")])
def test_unknown_face_values_are_rejected(key, value):
    with pytest.raises(ValueError):
        composite.resolve_face({"face": {key: value}}, {})


def test_unknown_mood_is_rejected():
    with pytest.raises(ValueError):
        composite.resolve_face({"mood": "ecstatic"}, {})


@pytest.mark.parametrize("mood", sorted(composite.MOODS))
@pytest.mark.parametrize("pose", ["stand", "arms_crossed", "shrug"])
def test_every_mood_renders_on_a_transparent_canvas(mood, pose):
    art, _ = composite.render_figure({"pose": pose, "mood": mood, "height": 0.6}, (640, 360))
    assert art.mode == "RGBA"
    assert art.getpixel((0, 0))[3] == 0
    assert art.getbbox() is not None


def test_moods_change_the_drawing():
    happy, _ = composite.render_figure({"mood": "happy"}, (640, 360))
    deadpan, _ = composite.render_figure({"mood": "deadpan"}, (640, 360))
    assert happy.tobytes() != deadpan.tobytes()
