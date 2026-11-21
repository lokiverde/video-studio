"""th.py level: the one command for a class or room recording that fails audio QC on quiet
off-mic speech. It lifts the quiet stretches in each rendered voice final, re-applies the
-14 LUFS chain, swaps the audio in with the video copied (old finals kept as
work/final_*_prevoice.mp4, like revoice), then re-mixes the music bed exactly as the last
`th.py music` run did (Army jobs need their --switch) and reminds to re-cut the Shorts."""
import argparse
import contextlib
import io
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import audio_qc  # noqa: E402
import common  # noqa: E402
import th  # noqa: E402
import th_lib  # noqa: E402

JOB = "20261110-120000-class"
CLASS = [(40, -6), (30, -18), (40, -6)]   # an attendee question 12 dB under the voice


def _final(path, parts, size="64x36"):
    """A tiny talking-head final: a still colour video over pink-noise runs (seconds, dB),
    encoded the way the pipeline writes finals (h264 + stereo AAC)."""
    total = sum(s for s, _ in parts)
    inputs = ["-f", "lavfi", "-i", f"color=c=navy:s={size}:r=5:d={total}"]
    labels = []
    for i, (secs, db) in enumerate(parts):
        inputs += ["-f", "lavfi", "-i", f"anoisesrc=color=pink:duration={secs}:sample_rate=48000:seed={i + 1}"]
        labels.append(f"[{i + 1}:a]volume={db}dB[a{i}]")
    joined = "".join(f"[a{i}]" for i in range(len(parts)))
    fc = ";".join(labels) + f";{joined}concat=n={len(parts)}:v=0:a=1[out]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", fc,
                    "-map", "0:v", "-map", "[out]", "-c:v", "libx264", "-preset", "ultrafast",
                    "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-shortest", str(path)], check=True)


SHORT = [(2, -6), (2, -18), (2, -6)]      # the same shape in 6 s, for the file handling tests
MUSIC = {"track": "lofi-bed-a.mp3", "level": -30.0, "hook": "hook-suspense-a.mp3", "hook_level": -27.0,
         "switch": 12.5, "sfx": 4, "no_sfx": False}


def _job_dir(root):
    jdir = root / JOB
    (jdir / "work").mkdir(parents=True)
    (jdir / "out").mkdir()
    (jdir / "job.json").write_text(json.dumps({"cuts": [], "sections": []}))
    return jdir


def level(**kw):
    th.cmd_level(argparse.Namespace(job=JOB, switch=kw.get("switch")))


@pytest.fixture(scope="module")
def class_final(tmp_path_factory):
    path = tmp_path_factory.mktemp("src") / "final_16x9.mp4"
    _final(path, CLASS)
    return path


@pytest.fixture(scope="module")
def short_final(tmp_path_factory):
    path = tmp_path_factory.mktemp("src") / "final_16x9.mp4"
    _final(path, SHORT)
    return path


@pytest.fixture(scope="module")
def levelled(tmp_path_factory, class_final):
    """One real run on a class-style final with a music bed in state (cmd_music recorded)."""
    root = tmp_path_factory.mktemp("jobs")
    jdir = _job_dir(root)
    shutil.copy(class_final, jdir / "out" / "final_16x9.mp4")
    calls = []
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(common, "JOBS_DIR", root)
        mp.setattr(th, "cmd_music", lambda args: calls.append(args))
        common.set_state(JOB, music=MUSIC)
        before = audio_qc.problems(audio_qc.measure(jdir / "out" / "final_16x9.mp4"), -14)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            level()
        state = common.get_state(JOB)
    return {"jdir": jdir, "calls": calls, "before": before, "out": out.getvalue(), "state": state}


@pytest.fixture
def job(tmp_path, monkeypatch):
    """A rendered job folder; cmd_music is recorded instead of run."""
    monkeypatch.setattr(common, "JOBS_DIR", tmp_path)
    jdir = _job_dir(tmp_path)
    calls = []
    monkeypatch.setattr(th, "cmd_music", lambda args: calls.append(args))
    return jdir, calls


@pytest.fixture
def stubbed(job, monkeypatch):
    """The same job with the audio work stubbed out, for the music orchestration tests."""
    jdir, calls = job
    (jdir / "out" / "final_16x9.mp4").write_bytes(b"rendered")
    monkeypatch.setattr(th, "_level_final", lambda jd, final: {"max_db": 11.0, "lifted_pct": 10})
    monkeypatch.setattr(th, "_audio_qc", lambda job_id, finals: {})
    return jdir, calls


def _video_md5(path):
    out = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(path), "-map", "0:v", "-c", "copy",
                          "-f", "md5", "-"], capture_output=True, text=True, check=True).stdout
    return out.strip()


def _duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True, check=True).stdout
    return float(out)


def test_level_makes_a_class_final_pass_audio_qc(levelled):
    assert any("quiet stretch" in p for p in levelled["before"])
    final = levelled["jdir"] / "out" / "final_16x9.mp4"
    assert audio_qc.problems(audio_qc.measure(final), th_lib.LOUDNESS_TARGET["I"]) == []
    assert levelled["state"]["audio_qc"] == {}
    assert levelled["state"]["level"]["final_16x9"]["max_db"] == pytest.approx(11.0, abs=1.5)


def test_level_keeps_the_old_final_and_copies_the_video(levelled, class_final):
    jdir = levelled["jdir"]
    final, backup = jdir / "out" / "final_16x9.mp4", jdir / "work" / "final_16x9_prevoice.mp4"
    assert backup.read_bytes() == class_final.read_bytes()
    assert _video_md5(final) == _video_md5(class_final)
    assert _duration(final) == pytest.approx(_duration(class_final), abs=0.05)
    assert sorted(p.name for p in (jdir / "out").iterdir()) == ["final_16x9.mp4"]
    assert sorted(p.name for p in (jdir / "work").iterdir()) == ["final_16x9_prevoice.mp4"]   # no float WAVs left


def test_level_remixes_music_with_the_original_switch(levelled):
    assert len(levelled["calls"]) == 1
    args = levelled["calls"][0]
    assert (args.job, args.track, args.level) == (JOB, "lofi-bed-a", -30.0)
    assert (args.hook_track, args.hook_level, args.switch, args.no_sfx) == ("hook-suspense-a", -27.0, 12.5, False)


def test_level_reminds_to_recut_the_shorts(levelled):
    assert f"th_shorts.py cut {JOB}" in levelled["out"]


def test_level_does_not_overwrite_an_earlier_prevoice_backup(job, short_final):
    # revoice already kept the original voice: that one stays the way back.
    jdir, _ = job
    shutil.copy(short_final, jdir / "out" / "final_16x9.mp4")
    backup = jdir / "work" / "final_16x9_prevoice.mp4"
    backup.write_bytes(b"original voice")
    level()
    assert backup.read_bytes() == b"original voice"
    assert (jdir / "out" / "final_16x9.mp4").read_bytes() != short_final.read_bytes()


def test_level_levels_both_finals(job, short_final):
    jdir, _ = job
    for aspect in ("16x9", "9x16"):
        shutil.copy(short_final, jdir / "out" / f"final_{aspect}.mp4")
    level()
    assert sorted(common.get_state(JOB)["level"]) == ["final_16x9", "final_9x16"]
    assert (jdir / "work" / "final_9x16_prevoice.mp4").exists()


def test_a_switch_flag_overrides_the_one_in_state(stubbed):
    _, calls = stubbed
    common.set_state(JOB, music=MUSIC)
    level(switch=20.0)
    assert calls[0].switch == 20.0


def test_an_old_music_state_without_a_switch_warns(stubbed, capsys):
    # Music runs before 2026-11-10 never recorded --switch: say so instead of guessing quietly.
    _, calls = stubbed
    common.set_state(JOB, music={"track": "lofi-bed-a.mp3", "level": -30.0, "hook": "hook-suspense-a.mp3",
                                 "sfx": 183})
    level()
    assert calls[0].switch is None
    assert "--switch" in capsys.readouterr().out


def test_no_music_state_means_no_music_run(stubbed):
    _, calls = stubbed
    level()
    assert calls == []


def test_a_final_with_nothing_quiet_is_left_as_it_was(job, tmp_path, capsys):
    jdir, calls = job
    steady = tmp_path / "steady.mp4"
    _final(steady, [(12, -8)])
    final = jdir / "out" / "final_16x9.mp4"
    shutil.copy(steady, final)
    common.set_state(JOB, music={"track": "lofi-bed-a.mp3", "level": -30.0, "sfx": 0})
    level()
    assert final.read_bytes() == steady.read_bytes()
    assert not (jdir / "work" / "final_16x9_prevoice.mp4").exists()
    assert calls == []
    assert "nothing to lift" in capsys.readouterr().out


def test_level_without_finals_stops(job):
    with pytest.raises(SystemExit):
        level()


def test_music_records_what_a_rerun_needs(job, tmp_path, monkeypatch):
    # The real cmd_music: state must hold --switch, --hook-level and --no-sfx for the rerun.
    jdir, _ = job
    monkeypatch.undo()
    monkeypatch.setattr(common, "JOBS_DIR", tmp_path)
    _final(jdir / "out" / "final_16x9.mp4", [(4, -8)])
    bed = tmp_path / "bed.wav"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "anoisesrc=color=pink:duration=4:sample_rate=48000", str(bed)], check=True)
    th.cmd_music(argparse.Namespace(job=JOB, track=str(bed), level=-30.0, hook_track=None, hook_level=-26.0,
                                    switch=7.0, no_sfx=True))
    music = common.get_state(JOB)["music"]
    assert (music["switch"], music["hook_level"], music["no_sfx"]) == (7.0, -26.0, True)
    assert (jdir / "out" / "final_16x9_music.mp4").exists()


def test_rerun_args_come_from_state():
    music = {"track": "lofi-bed-a.mp3", "level": -32.0, "hook": "hook-suspense-a.mp3", "hook_level": -27.0,
             "switch": 9.0, "sfx": 3, "no_sfx": False}
    assert th_lib.music_rerun_args(music) == {"track": "lofi-bed-a", "level": -32.0, "hook_track": "hook-suspense-a",
                                              "hook_level": -27.0, "switch": 9.0, "no_sfx": False}


def test_rerun_args_for_an_old_state_use_the_defaults():
    old = {"track": "lofi-bed-a.mp3", "level": -30.0, "hook": None, "sfx": 0}
    args = th_lib.music_rerun_args(old)
    assert args["hook_track"] is None and args["switch"] is None
    assert args["hook_level"] == th_lib.MUSIC_BED_LUFS + 2
    assert args["no_sfx"] is True            # it mixed no effects, so the rerun mixes none


def test_rerun_args_take_a_switch_override():
    assert th_lib.music_rerun_args({"track": "a.mp3", "level": -30.0, "switch": 9.0}, switch=3.0)["switch"] == 3.0


def test_audio_qc_points_quiet_stretches_at_th_level():
    m = {"I": -14.0, "LRA": 6.0, "TP": -2.0,
         "frames": [(round(0.1 * i, 1), -26.5 if 600 <= i < 900 else -14.5) for i in range(1, 1500)]}
    text = "\n".join(audio_qc.problems(m, target=-14.0))
    assert "quiet stretch" in text and "th.py level" in text
