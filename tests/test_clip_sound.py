"""Clip sound and the AI label: a clip scene plays its own sound by choice (keep, duck,
mute), and no on-screen AI tag is drawn: YouTube Studio's altered or synthetic content
label does that job (Tony, 2026-10-24; docs/briefs/2026-10-24-realistic-footage.md, 5.4
and 5.6). Every clip here is made locally with ffmpeg: no vendor files, no network."""
import contextlib
import io
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import assemble  # noqa: E402
import clips  # noqa: E402
import common  # noqa: E402


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def make_clip(path, dur, w=640, h=360, color="orange", tone=440):
    """A clip with its own sound: a steady tone, the stand-in for native speech."""
    ff("-f", "lavfi", "-i", f"color=c={color}:s={w}x{h}:d={dur}:r=24",
       "-f", "lavfi", "-i", f"sine=frequency={tone}:duration={dur}",
       "-pix_fmt", "yuv420p", "-shortest", str(path))
    return path


def mean_volume(path, start, dur, band=None):
    """Mean loudness in dB of a stretch of a rendered file (-91 for digital silence).
    band=Hz hears only that tone, so a clip's sound can be measured under narration."""
    af = (f"bandpass=f={band}:width_type=h:w=50," if band else "") + "volumedetect"
    out = subprocess.run(["ffmpeg", "-v", "info", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
                          "-i", str(path), "-af", af, "-f", "null", "-"],
                         capture_output=True, text=True, check=True).stderr
    found = re.search(r"mean_volume: (-?[\d.]+|-inf) dB", out)
    return -91.0 if found.group(1) == "-inf" else float(found.group(1))


def pixel(path, seconds, x, y):
    out = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{seconds:.3f}", "-i", str(path),
                          "-frames:v", "1", "-vf", f"format=rgb24,crop=2:2:{x}:{y}", "-f", "rawvideo",
                          "-"], capture_output=True, check=True)
    return tuple(out.stdout[:3])


@pytest.fixture(scope="module")
def sound_job(tmp_path_factory):
    """Rendered once: a 4s kept clip, a ducked one, a muted one, and a kept clip trimmed
    to 3.5s under 1s of narration (scene 4, from 7s). Returns (job dir, everything
    assemble printed)."""
    root = tmp_path_factory.mktemp("jobs")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(common, "JOBS_DIR", root)
        jdir = root / "sound"
        (jdir / "work").mkdir(parents=True)
        (jdir / "out").mkdir()
        (jdir / "rf").mkdir()
        (jdir / "scenes.json").write_text(json.dumps({"theme": "sketch", "end_hold": 0, "scenes": [
            {"id": 1, "caption": "Kept", "clip": "rf/long.mp4"},
            {"id": 2, "caption": "Ducked", "clip": "rf/short.mp4", "audio": "duck"},
            {"id": 3, "caption": "Muted", "clip": "rf/short.mp4", "audio": "mute"},
            {"id": 4, "caption": "Spoken over", "narration": "x", "clip": "rf/long.mp4",
             "trim": [0.5, 4.0]},
        ]}))
        make_clip(jdir / "rf" / "long.mp4", 4.0)
        make_clip(jdir / "rf" / "short.mp4", 1.5)
        ff("-f", "lavfi", "-i", "sine=frequency=220:duration=1.0", "-ar", "44100",
           str(jdir / "work" / "scene_04.wav"))
        log = io.StringIO()
        with contextlib.redirect_stdout(log):
            assemble.run("sound")
        yield jdir, log.getvalue()


def test_keep_plays_the_clip_sound_duck_lowers_it_and_mute_drops_it(sound_job):
    jdir, _ = sound_job
    final = jdir / "out" / "final_16x9.mp4"
    kept, ducked, muted = mean_volume(final, 0.5, 3.0), mean_volume(final, 4.2, 1.0), mean_volume(final, 5.7, 1.0)
    assert kept > -40, kept                 # the clip's own sound is there
    assert kept - ducked > 6, (kept, ducked)
    assert muted < -70, muted


def test_a_kept_clip_under_narration_ducks_and_says_so(sound_job):
    _, log = sound_job
    assert "scene 4: clip sound ducked under the narration" in log
    assert "scene 1: clip sound ducked" not in log


def test_a_kept_clip_ducks_only_while_the_narration_plays(sound_job):
    """Brief 5.4: duck the clip under the narration. Once the words end, the clip's own
    sound comes back to full for the rest of the scene."""
    jdir, _ = sound_job
    final = jdir / "out" / "final_16x9.mp4"
    under = mean_volume(final, 7.1, 0.8, band=440)
    after = mean_volume(final, 8.4, 2.0, band=440)
    kept = mean_volume(final, 0.5, 3.0, band=440)
    assert after - under > 6, (under, after)
    assert abs(after - kept) < 3, (after, kept)


def silent_clip(has_audio=True):
    return clips.ClipInfo(640, 360, 4.0, has_audio)


def test_a_themes_clip_duck_sets_the_ducked_level():
    sound = clips.clip_volume({"id": 1, "audio": "duck"}, silent_clip(), 0.0, {"clip_duck": 0.4})
    assert sound.level == pytest.approx(0.4)


@pytest.mark.parametrize("bad", ["loud", -0.1, 1.5, True])
def test_clip_duck_must_be_a_number_from_0_to_1(capsys, bad):
    with pytest.raises(SystemExit):
        clips.clip_volume({"id": 1, "audio": "duck"}, silent_clip(), 0.0, {"clip_duck": bad})
    assert "'clip_duck' must be a number from 0 to 1" in capsys.readouterr().err


@pytest.mark.parametrize("scene,has_audio,kept", [
    ({"id": 1}, True, True),
    ({"id": 1, "audio": "keep"}, False, False),   # nothing to keep: the music stays up
    ({"id": 1, "audio": "duck"}, True, False),
    ({"id": 1, "audio": "mute"}, True, False),
])
def test_only_a_clip_with_sound_set_to_keep_counts_as_kept(scene, has_audio, kept):
    assert clips.keeps_sound(scene, silent_clip(has_audio)) is kept


@pytest.mark.parametrize("bad", ["loud", "", None, 1])
def test_audio_must_be_keep_duck_or_mute(capsys, bad):
    scenes = [{"id": 1, "caption": "c", "clip": "a.mp4", "audio": bad},
              *({"id": i, "narration": "x", "caption": "c", "image_prompt": "a room"} for i in (2, 3))]
    with pytest.raises(SystemExit):
        common.validate_scenes({"scenes": scenes})
    assert "'audio' must be keep, duck or mute" in capsys.readouterr().err


def dark_share(path, seconds, w=360, h=160):
    """Share of near-black pixels in the top-left corner of the frame at `seconds`.
    The test clips are orange there, so dark pixels could only be a tag."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{seconds:.3f}", "-i", str(path),
                          "-frames:v", "1", "-vf", f"format=rgb24,crop={w}:{h}:0:0", "-f", "rawvideo",
                          "-"], capture_output=True, check=True).stdout
    pixels = [out[i:i + 3] for i in range(0, len(out), 3)]
    return sum(1 for p in pixels if max(p) < 60) / len(pixels)


@pytest.mark.parametrize("final", ["final_16x9.mp4", "final_9x16.mp4"])
def test_no_ai_tag_is_drawn_over_clip_scenes(sound_job, final):
    video = sound_job[0] / "out" / final
    assert dark_share(video, 0.5) == 0         # the first clip scene
    assert dark_share(video, 4.3) == 0         # and a later one
