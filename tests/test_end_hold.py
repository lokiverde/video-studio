"""The ending: the last frame holds for a beat while the music fades, instead of the
video stopping dead on the final syllable."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import assemble  # noqa: E402


def test_default_hold_applies_when_nothing_is_set():
    assert assemble.end_hold_seconds({}, {}) == assemble.END_HOLD_DEFAULT > 0


def test_scenes_file_beats_theme():
    assert assemble.end_hold_seconds({"end_hold": 4}, {"end_hold": 1}) == 4.0


def test_zero_turns_it_off():
    assert assemble.end_hold_seconds({"end_hold": 0}, {}) == 0.0


@pytest.mark.parametrize("bad", [-1, 30, "long", None, True])
def test_bad_values_are_rejected(bad):
    with pytest.raises(ValueError):
        assemble.end_hold_seconds({"end_hold": bad}, {})


def test_hold_pads_picture_and_sound_and_fades_the_music():
    fc, amap = assemble.concat_filter(3, has_music=True, mvol=0.18, total=60.0, hold=3.0)
    assert "tpad=stop_mode=clone:stop_duration=3.000" in fc
    assert "apad=pad_dur=3.000" in fc
    assert "afade=t=out:st=60.500:d=2.500" in fc
    # the fade has to come after the normaliser, or dynaudnorm pumps it back up
    assert fc.index("dynaudnorm") < fc.index("afade")
    assert amap == "[af]"


def test_no_music_still_holds_the_frame():
    fc, amap = assemble.concat_filter(2, has_music=False, mvol=0.18, total=20.0, hold=2.5)
    assert "tpad=stop_mode=clone" in fc and "apad=pad_dur=2.500" in fc
    assert "afade" not in fc and "amix" not in fc


def test_zero_hold_leaves_the_old_graph():
    fc, amap = assemble.concat_filter(2, has_music=False, mvol=0.18, total=20.0, hold=0.0)
    assert fc == "[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[vf][na]"
    assert amap == "[na]"
