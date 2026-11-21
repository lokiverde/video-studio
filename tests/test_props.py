"""Props: drawn objects in a cast member's hand, so a shot can show him holding the
thing the sentence is about. Plus the arms_crossed pose reading as crossed arms."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "characters" / "stickman"))

import composite  # noqa: E402
import props  # noqa: E402

FRAME = (1280, 720)
EXPECTED = {"phone", "keys", "cash", "contract", "coffee", "briefcase", "magnifier",
            "sign", "house", "lightbulb"}


def _art(**spec):
    art, _ = composite.render_figure({"pose": "stand", **spec}, FRAME)
    return art


def test_the_library_has_the_starter_set():
    assert EXPECTED <= set(props.names())


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_prop_changes_the_drawing(name):
    assert _art(prop=name).tobytes() != _art().tobytes()


def test_prop_can_go_in_the_left_hand():
    right = _art(prop="phone")
    left = _art(prop={"name": "phone", "hand": "l"})
    assert right.tobytes() != left.tobytes()


def test_unknown_prop_is_rejected_with_the_list():
    with pytest.raises(ValueError, match="phone"):
        _art(prop="chainsaw")


def test_unknown_hand_is_rejected():
    with pytest.raises(ValueError):
        _art(prop={"name": "phone", "hand": "both"})


def test_props_work_on_the_whole_cast_and_every_pose():
    for who in ("stick-man", "gray", "curly"):
        for pose in composite.pose_names():
            art, _ = composite.render_figure(
                {"pose": pose, "who": who, "prop": "contract"}, FRAME)
            assert art.getbbox() is not None


def test_arms_crossed_shows_arms_over_the_shirt():
    """The old pose drew black arms on a black shirt: invisible. The forearms now carry a
    lighter rim, so the chest band must contain pixels lighter than shirt and ink."""
    import figure
    art = _art(pose="arms_crossed", height=0.9)
    w, h = art.size
    head_r = 0.9 * FRAME[1] / composite.FIGURE_HEIGHT
    top = round(head_r * (1.25 + 1.35))
    band = art.crop((round(w / 2 - head_r * 0.2), top, round(w / 2 + head_r * 0.2),
                     round(top + head_r * 0.45)))
    rim = figure.ARM_RIM[:3]
    assert any(px[:3] == rim for px in band.getdata())
