"""Clip scenes: a finished video file as a scene's picture, in both cuts, behind the
preview gate (docs/briefs/2026-10-24-realistic-footage.md, 5.4). Every clip here is made
locally with ffmpeg: no vendor files, no network."""
import contextlib
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import approval  # noqa: E402
import assemble  # noqa: E402
import common  # noqa: E402
import gen_images  # noqa: E402


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def make_clip(path, w, h, dur, fps=24, top="red", bottom="blue"):
    """A test clip whose top half and bottom half are different colours, so a crop's
    anchor can be read back off the rendered frame."""
    ff("-f", "lavfi", "-i", f"color=c={top}:s={w}x{h}:d={dur}:r={fps}",
       "-vf", f"drawbox=x=0:y=ih/2:w=iw:h=ih/2:color={bottom}:t=fill",
       "-pix_fmt", "yuv420p", str(path))
    return path


def make_two_tone_clip(path, w, h, first, second, split, dur, fps=24):
    """A clip that shows one colour until `split` seconds, then another: trim's start
    point can be read back off the first frame of the scene."""
    ff("-f", "lavfi", "-i", f"color=c={first}:s={w}x{h}:d={split}:r={fps}",
       "-f", "lavfi", "-i", f"color=c={second}:s={w}x{h}:d={dur - split}:r={fps}",
       "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]", "-map", "[v]",
       "-pix_fmt", "yuv420p", str(path))
    return path


def pixel(path, seconds, x, y):
    """(r, g, b) of one pixel of the frame at `seconds`."""
    out = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{seconds:.3f}", "-i", str(path),
                          "-frames:v", "1", "-vf", f"format=rgb24,crop=2:2:{x}:{y}", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True)
    return tuple(out.stdout[:3])


def make_rotated_clip(path, flat):
    """What a phone records held upright: 640x360 pixels plus a 90 degree display
    rotation, so every player shows it 360x640."""
    make_clip(flat, 640, 360, 1.0)
    ff("-display_rotation", "90", "-i", str(flat), "-c", "copy", str(path))
    return path


def make_narration(path, dur):
    ff("-f", "lavfi", "-i", f"sine=frequency=330:duration={dur}", "-ar", "44100", str(path))


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,width,height:format=duration", "-of", "json",
                          str(path)], capture_output=True, text=True, check=True)
    info = json.loads(out.stdout)
    video = next(s for s in info["streams"] if s["codec_type"] == "video")
    return video["width"], video["height"], float(info["format"]["duration"])


def stream_durations(path):
    """(video seconds, audio seconds) of a rendered file."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True)
    streams = {s["codec_type"]: float(s["duration"]) for s in json.loads(out.stdout)["streams"]}
    return streams["video"], streams["audio"]


def write_job(root, job_id, scenes, **extra):
    jdir = root / job_id
    (jdir / "work").mkdir(parents=True)
    (jdir / "out").mkdir()
    (jdir / "scenes.json").write_text(json.dumps({"theme": "sketch", "scenes": scenes, **extra}))
    return jdir


@pytest.fixture(scope="module")
def jobs(tmp_path_factory):
    root = tmp_path_factory.mktemp("jobs")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(common, "JOBS_DIR", root)
        yield root


@pytest.fixture(scope="module")
def motion_job(jobs):
    """Three animated scenes, each clip shorter than its narration (the motion path)."""
    scenes = [{"id": i, "narration": "x", "caption": f"Scene {i}", "image_prompt": "a room",
               "motion": {}} for i in (1, 2, 3)]
    jdir = write_job(jobs, "motion", scenes, end_hold=0)
    for i in (1, 2, 3):
        ff("-f", "lavfi", "-i", "color=c=green:s=128x72:d=1:r=24", "-c:v", "libvpx-vp9",
           str(jdir / "work" / f"motion_{i:02d}.webm"))
        make_narration(jdir / "work" / f"scene_{i:02d}.wav", 1.5)
    assemble.run("motion")
    return jdir


def scenes_with(first):
    rest = [{"id": i, "narration": "x", "caption": "c", "image_prompt": "a room"} for i in (2, 3)]
    return {"scenes": [{"id": 1, "caption": "c", **first}, *rest]}


def rejected(data, capsys):
    with pytest.raises(SystemExit):
        common.validate_scenes(data)
    return capsys.readouterr().err


@pytest.mark.parametrize("other", [
    {"photo": "shop.jpg"},
    {"figure": {"pose": "wave"}},
    {"motion": {}},
    {"shots": ["a room", "a street"]},
    {"image_prompt": "the main character waves"},
    {"card": 3},
    {"graphic": {"kind": "stamp"}},
    {"hold": True},
    {"tag": "OCT 24"},
    {"note": "fake"},
])
def test_a_clip_scene_cannot_also_carry_another_picture(other, capsys):
    err = rejected(scenes_with({"narration": "x", "clip": "rf/returns/S02.mp4", **other}), capsys)
    assert "'clip'" in err and f"'{next(iter(other))}'" in err


def test_a_clip_scene_needs_no_narration(capsys):
    common.validate_scenes(scenes_with({"clip": "rf/returns/S02.mp4"}))
    # every other kind of scene still has to say something
    assert "missing 'narration'" in rejected(scenes_with({"image_prompt": "a room"}), capsys)


@pytest.mark.parametrize("trim", [[2.0, 1.0], [1.0, 1.0], [-0.5, 2.0], [1.0], "0-2", [0, "2"], [True, 2]])
def test_trim_must_be_a_start_before_an_end(trim, capsys):
    err = rejected(scenes_with({"clip": "a.mp4", "trim": trim}), capsys)
    assert "'trim'" in err


def test_a_good_trim_passes():
    common.validate_scenes(scenes_with({"clip": "a.mp4", "trim": [0, 7.5]}))


@pytest.mark.parametrize("clip", ["", "  ", 3, ["a.mp4"]])
def test_clip_must_name_a_file(clip, capsys):
    assert "'clip'" in rejected(scenes_with({"clip": clip}), capsys)


@pytest.fixture(scope="module")
def clip_job(jobs):
    """Silent clip scenes from files in the job, rendered once for the tests below.
    Returns (job dir, everything assemble printed)."""
    jdir = write_job(jobs, "clips", [
        {"id": 1, "caption": "One", "clip": "rf/returns/wide.mp4"},
        {"id": 2, "caption": "Two", "clip": "rf/returns/long.mp4", "trim": [0.5, 1.2]},
        {"id": 3, "caption": "Three", "narration": "long line", "clip": "rf/returns/wide.mp4"},
        {"id": 4, "caption": "Four", "narration": "short", "clip": "rf/returns/wide.mp4"},
        {"id": 5, "caption": "Five", "clip": "rf/returns/tall.mp4", "focus": "top"},
        {"id": 6, "caption": "Six", "clip": "rf/returns/tall.mp4", "focus": "bottom"},
        {"id": 7, "caption": "Seven", "clip": "rf/returns/rotated.mp4"},
    ], end_hold=0)
    (jdir / "rf" / "returns").mkdir(parents=True)
    make_clip(jdir / "rf" / "returns" / "wide.mp4", 640, 360, 1.0)
    make_two_tone_clip(jdir / "rf" / "returns" / "long.mp4", 640, 360, "white", "yellow", 0.5, 2.0)
    make_clip(jdir / "rf" / "returns" / "tall.mp4", 360, 640, 1.0)
    make_rotated_clip(jdir / "rf" / "returns" / "rotated.mp4", jdir / "rf" / "flat.mp4")
    make_narration(jdir / "work" / "scene_03.wav", 2.0)
    make_narration(jdir / "work" / "scene_04.wav", 0.3)
    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        assemble.run("clips")
    return jdir, log.getvalue()


def test_clip_scenes_render_both_cuts_timed_from_the_clips(clip_job):
    jdir, _ = clip_job
    w, h, dur = probe(jdir / "out" / "final_16x9.mp4")
    assert (w, h) == (1920, 1080)
    assert dur == pytest.approx(1.0 + 0.7 + 2.0 + assemble.PAD + 1.0 + 1.0 + 1.0 + 1.0, abs=0.15)
    w, h, _ = probe(jdir / "out" / "final_9x16.mp4")
    assert (w, h) == (1080, 1920)


def test_trim_plays_only_the_chosen_stretch_of_the_clip(clip_job):
    jdir, _ = clip_job
    assert common.get_state("clips")["scene_durations"][1] == pytest.approx(0.7, abs=0.05)
    # scene 2 opens 0.5s into its clip, after the white lead-in, in both cuts
    for final in ("final_16x9.mp4", "final_9x16.mp4"):
        r, g, b = pixel(jdir / "out" / final, 1.05, 300, 300)
        assert r > 200 and g > 200 and b < 90, final


def test_narration_longer_than_the_clip_holds_its_last_frame_and_warns(clip_job):
    _, log = clip_job
    assert common.get_state("clips")["scene_durations"][2] == pytest.approx(2.0 + assemble.PAD, abs=0.05)
    assert "scene 3: narration runs" in log and "last frame holds" in log


def test_a_clip_longer_than_its_narration_plays_out(clip_job):
    jdir, log = clip_job
    assert common.get_state("clips")["scene_durations"][3] == pytest.approx(1.0, abs=0.05)
    assert "scene 4: narration runs" not in log
    # the sound track runs to the end of the clip, so it never drifts ahead of the picture
    video, audio = stream_durations(jdir / "out" / "final_16x9.mp4")
    assert audio == pytest.approx(video, abs=0.1)


def test_focus_anchors_the_crop(clip_job):
    """A tall clip in the wide cut loses most of its height: focus picks which part
    stays. The test clip is red on top and blue below."""
    jdir, _ = clip_job
    wide = jdir / "out" / "final_16x9.mp4"
    top, bottom = pixel(wide, 5.55, 960, 400), pixel(wide, 6.55, 960, 400)
    assert top[0] > 200 and top[2] < 60, top
    assert bottom[2] > 200 and bottom[0] < 60, bottom


def test_a_clip_shaped_unlike_a_cut_warns_to_regenerate_at_that_shape(clip_job):
    _, log = clip_job
    assert "scene 5: the clip is 360x640" in log and "regenerate it at 16:9" in log
    assert "scene 1: the clip is 640x360" in log and "regenerate it at 9:16" in log


@pytest.fixture(scope="module")
def preview_job(jobs):
    """Clip scenes run through the preview pass. Any call to the image generator fails."""
    jdir = write_job(jobs, "preview", [
        {"id": 1, "caption": "One", "clip": "rf/returns/wide.mp4"},
        {"id": 2, "caption": "Two", "clip": "rf/returns/long.mp4", "trim": [0.5, 1.2]},
        {"id": 3, "caption": "Three", "clip": "rf/returns/tall.mp4", "focus": "bottom"},
    ])
    (jdir / "rf" / "returns").mkdir(parents=True)
    make_clip(jdir / "rf" / "returns" / "wide.mp4", 640, 360, 1.0)
    make_two_tone_clip(jdir / "rf" / "returns" / "long.mp4", 640, 360, "white", "yellow", 0.5, 2.0)
    make_clip(jdir / "rf" / "returns" / "tall.mp4", 360, 640, 1.0)

    def no_generator(*_a, **_k):
        raise AssertionError("a clip scene must never call the image generator")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(common, "http_json", no_generator)
        gen_images.run("preview")
        gen_images.run_portrait("preview")
    return jdir


def test_a_clip_that_cannot_be_read_stops_with_a_clear_message(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(common, "JOBS_DIR", tmp_path)
    jdir = write_job(tmp_path, "broken", [{"id": i, "caption": "c", "clip": "rf/bad.mp4"} for i in (1, 2, 3)])
    (jdir / "rf").mkdir()
    (jdir / "rf" / "bad.mp4").write_text("not a video at all\n" * 50)
    with pytest.raises(SystemExit):
        gen_images.run("broken")
    assert "cannot be read as a video" in capsys.readouterr().err


def still_pixel(path, x, y):
    from PIL import Image
    return Image.open(path).convert("RGB").getpixel((x, y))


@pytest.mark.parametrize("prefix,size", [("", (1280, 720)), ("p_", (720, 1280))])
def test_each_clip_gets_a_still_of_its_first_frame_for_the_contact_sheet(preview_job, prefix, size):
    from PIL import Image
    work = preview_job / "work"
    stills = [work / f"{prefix}scene_{i:02d}.png" for i in (1, 2, 3)]
    assert [Image.open(s).size for s in stills] == [size] * 3
    mid = (size[0] // 2, size[1] // 3)
    assert still_pixel(stills[1], *mid)[2] < 90          # trim start: yellow, past the white lead-in
    if not prefix:
        assert still_pixel(stills[2], *mid)[2] > 200     # focus bottom: the blue half of a tall clip


def test_the_contact_sheet_still_carries_a_duration_badge(preview_job):
    still = preview_job / "work" / "scene_01.png"
    r, g, b = still_pixel(still, 40, 40)
    assert max(r, g, b) < 60, (r, g, b)                   # the badge, not the red clip behind it
    assert (preview_job / "work" / "contact_sheet.jpg").exists()
    assert (preview_job / "work" / "contact_sheet_9x16.jpg").exists()


def gated_job(tmp_path, clip_ref):
    (tmp_path / "work").mkdir()
    (tmp_path / "rf" / "returns").mkdir(parents=True)
    (tmp_path / "rf" / "returns" / "S02.mp4").write_bytes(b"take one")
    (tmp_path / "scenes.json").write_text(json.dumps(
        {"scenes": [{"id": 1, "caption": "c", "clip": clip_ref}]}))
    (tmp_path / "work" / "scene_01.png").write_bytes(b"first frame")
    return tmp_path


@pytest.mark.parametrize("absolute", [False, True])
def test_replacing_a_clip_after_approval_voids_it(tmp_path, absolute):
    clip = tmp_path / "rf" / "returns" / "S02.mp4"
    j = gated_job(tmp_path, str(clip) if absolute else "rf/returns/S02.mp4")
    approved = approval.fingerprint(j, "faceless")
    clip.write_bytes(b"take two, same first frame")
    current = approval.fingerprint(j, "faceless")
    assert current != approved
    # finish runs this gate, so it refuses until Tony approves the new take
    assert "changed since Tony approved" in approval.gate({"approved_fingerprint": approved}, current)


@pytest.mark.skipif(sys.platform.startswith("win"), reason="Windows has no inode change time to catch a take copied with old dates")
def test_a_new_take_with_an_older_file_date_still_makes_the_sheet_stale(tmp_path):
    """A take copied in with its original dates kept (cp -p, shutil.copy2) can be older
    than the sheet; approve must still refuse until Tony sees a fresh one."""
    import os
    import time
    clip = tmp_path / "rf" / "returns" / "S02.mp4"
    j = gated_job(tmp_path, "rf/returns/S02.mp4")
    (j / "work" / "contact_sheet.jpg").write_bytes(b"sheet")
    assert approval.faceless_sheet_problem(j) is None
    clip.write_bytes(b"take two")
    old = time.time() - 86400
    os.utime(clip, (old, old))
    assert "stale" in approval.faceless_sheet_problem(j)


def test_a_job_without_clips_keeps_its_fingerprint(tmp_path):
    """Approvals given before clip scenes existed must still match."""
    (tmp_path / "work").mkdir()
    (tmp_path / "scenes.json").write_text('{"scenes": [{"id": 1, "image_prompt": "a room"}]}')
    (tmp_path / "work" / "scene_01.png").write_bytes(b"still one")
    (tmp_path / "work" / "p_scene_01.png").write_bytes(b"still one, tall")
    # recorded from the gate as it stood before clip scenes (2026-10-24)
    assert approval.fingerprint(tmp_path, "faceless") == \
        "671a26ae2ad2f35b23a57a0568d292efad3f21e8ecd86223763e3472713e01bd"


def test_a_rotated_phone_clip_is_judged_by_the_shape_it_plays_at(clip_job):
    _, log = clip_job
    assert "scene 7: the clip is 360x640" in log and "regenerate it at 16:9" in log
    assert "scene 7: the clip is 640x360" not in log


def test_motion_scenes_still_render_both_cuts_and_hold_the_last_frame(motion_job):
    w, h, dur = probe(motion_job / "out" / "final_16x9.mp4")
    assert (w, h) == (1920, 1080)
    # each scene runs for its narration plus the breathing pad, past the 1s clip
    assert dur == pytest.approx(3 * (1.5 + assemble.PAD), abs=0.15)
    w, h, _ = probe(motion_job / "out" / "final_9x16.mp4")
    assert (w, h) == (1080, 1920)


def test_the_motion_path_builds_the_same_ffmpeg_command_as_before_clip_scenes(tmp_path, monkeypatch):
    """Recorded from motion_clip before the prefactor (2026-10-24): existing themes'
    animated scenes must render exactly as they did."""
    calls = []
    monkeypatch.setattr(assemble, "run_ff", lambda args, cwd: calls.append(args))
    (tmp_path / "scene_01.wav").write_bytes(b"")
    assemble.motion_clip(tmp_path, 1, 4.2, 30, vertical=True)
    assert calls == [[
        "-i", "motion_01.webm", "-i", "scene_01.wav", "-loop", "1", "-framerate", "30",
        "-i", "caption_v_01.png", "-filter_complex",
        "[0:v]tpad=stop_mode=clone:stop_duration=4.200,fps=30,scale=1080:1920:"
        "force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[m];"
        "[m][2:v]overlay=0:0,format=yuv420p[v];[1:a]apad=pad_dur=0.35[a]",
        "-map", "[v]", "-map", "[a]", "-t", "4.200", "-c:v", "libx264", "-preset", "medium",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "clipv_01.mp4"]]
