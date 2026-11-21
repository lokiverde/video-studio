"""Echo cleanup for the cloned voice (Tony 2026-10-09: "take out the echoness"). Every
scene is packed into one file with silent gaps, run through Resemble Enhance once (the
model takes minutes to load, so per-scene runs were ~10x slower), then split back."""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import voice_cleanup  # noqa: E402


def test_pack_then_unpack_returns_every_clip_exactly():
    clips = [np.full(10, 0.1, np.float32), np.full(7, 0.2, np.float32), np.full(3, 0.3, np.float32)]
    signal, spans = voice_cleanup.pack(clips, gap=5)
    assert len(signal) == 10 + 7 + 3 + 3 * 5
    back = voice_cleanup.unpack(signal, spans)
    assert [len(c) for c in back] == [10, 7, 3]
    for a, b in zip(clips, back):
        assert np.array_equal(a, b)


def test_gaps_are_silent():
    signal, spans = voice_cleanup.pack([np.ones(4, np.float32), np.ones(4, np.float32)], gap=3)
    assert not signal[4:7].any()


def _wav(path, seconds=0.5):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", f"sine=frequency=220:duration={seconds}", "-ar", "48000", "-ac", "1",
                    "-c:a", "pcm_s16le", str(path)], check=True)


def test_skips_and_leaves_scenes_alone_without_the_enhancer(tmp_path, monkeypatch, capsys):
    _wav(tmp_path / "scene_01.wav")
    before = (tmp_path / "scene_01.wav").read_bytes()
    monkeypatch.setattr(voice_cleanup, "available", lambda: False)
    assert voice_cleanup.clean_scenes(tmp_path, [1]) is False
    assert (tmp_path / "scene_01.wav").read_bytes() == before
    assert "skipped" in capsys.readouterr().out


def test_cleans_every_scene_in_one_enhancer_run(tmp_path, monkeypatch):
    for n, sec in ((1, 0.5), (2, 0.8)):
        _wav(tmp_path / f"scene_{n:02d}.wav", sec)
    calls = []

    def fake_enhance(src, dst):  # stands in for Resemble: halves the level, keeps length
        calls.append(src)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
                        "-af", "volume=0.5", "-ar", "44100", str(dst)], check=True)

    monkeypatch.setattr(voice_cleanup, "available", lambda: True)
    monkeypatch.setattr(voice_cleanup, "_enhance", fake_enhance)
    assert voice_cleanup.clean_scenes(tmp_path, [1, 2]) is True
    assert len(calls) == 1
    for n, sec in ((1, 0.5), (2, 0.8)):
        out = tmp_path / f"scene_{n:02d}.wav"
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                    "-of", "csv=p=0", str(out)], capture_output=True,
                                   text=True).stdout)
        assert dur == pytest.approx(sec, abs=0.01)
        assert (tmp_path / "voice_raw" / f"scene_{n:02d}.wav").exists()
