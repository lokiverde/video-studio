"""Upward leveller for class and room recordings: off-mic speech (attendee questions, Tony
away from the mic) sits far under the voice, so a final hits -14 LUFS and still swings. The
Nov 2026 class video had four attendee stretches 12 LU under Tony (LRA 12.8). Lifting
speech that sits more than 3 dB under the typical level up to 1 dB under it (at most +15 dB,
gain held through pauses, 0.6 s glide) took it to 5.1 LU without touching Tony's delivery."""
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import audio_qc  # noqa: E402
import voice_level  # noqa: E402

SR = 8000   # the leveller reads 1 s RMS windows, so a low rate is plenty for the maths


def speech(*runs, sr=SR, seed=1):
    """White noise in runs of (seconds, dB RMS): a stand-in for speech at a steady level."""
    rng = np.random.default_rng(seed)
    parts = [rng.standard_normal(int(secs * sr)) * 10 ** (db / 20) for secs, db in runs]
    return np.concatenate(parts).astype(np.float32)


def gain_at(curve, seconds):
    t, g = curve
    return float(np.interp(seconds, t, g))


def test_steady_speech_is_untouched():
    t, g, stats = voice_level.gain_curve(speech((60, -20)), SR)
    assert np.abs(g).max() < 0.5
    assert stats["lifted_pct"] == 0


def test_a_quiet_stretch_comes_up_to_one_db_under_the_voice():
    t, g, stats = voice_level.gain_curve(speech((30, -20), (20, -32), (30, -20)), SR)
    assert gain_at((t, g), 40) == pytest.approx(11.0, abs=0.5)
    assert gain_at((t, g), 10) == pytest.approx(0.0, abs=0.3)
    assert gain_at((t, g), 70) == pytest.approx(0.0, abs=0.3)
    assert stats["voice_db"] == pytest.approx(-20.0, abs=0.5)
    assert stats["max_db"] == pytest.approx(11.0, abs=0.5)


def test_the_lift_never_passes_fifteen_db():
    # Room noise comes up with the voice: a very quiet stretch is capped, not matched.
    t, g, _ = voice_level.gain_curve(speech((30, -20), (20, -45), (30, -20)), SR)
    assert gain_at((t, g), 40) == pytest.approx(voice_level.LV_MAX_UP, abs=0.3)
    assert g.max() <= voice_level.LV_MAX_UP + 1e-6


def test_soft_delivery_inside_the_deadband_is_left_alone():
    t, g, _ = voice_level.gain_curve(speech((30, -20), (20, -22.5), (30, -20)), SR)
    assert np.abs(g).max() < 0.5


def test_the_gain_holds_through_a_pause_in_quiet_speech():
    # A pause between an attendee's sentences keeps their lift: no dip, no pumping.
    curve = voice_level.gain_curve(speech((30, -20), (10, -32), (3, -90), (10, -32), (30, -20)), SR)[:2]
    assert gain_at(curve, 41.5) == pytest.approx(11.0, abs=0.7)


def test_a_pause_after_normal_speech_is_not_lifted():
    # Room tone between Tony's sentences stays where it was.
    curve = voice_level.gain_curve(speech((30, -20), (3, -90), (30, -20)), SR)[:2]
    assert gain_at(curve, 31.5) == pytest.approx(0.0, abs=0.3)


def test_the_gain_glides_instead_of_stepping():
    t, g, _ = voice_level.gain_curve(speech((30, -20), (20, -32), (30, -20)), SR)
    assert np.abs(np.diff(g)).max() < 1.5            # dB per 0.1 s reading
    rising = t[(g > 0.1 * g.max()) & (g < 0.9 * g.max()) & (t < 40)]
    assert rising.max() - rising.min() >= voice_level.LV_SMOOTH


def test_the_gain_is_one_value_per_sample_so_nothing_is_cut():
    x = speech((30, -20), (20, -32), (30, -20))
    gain, _ = voice_level.gain(x, SR)
    assert gain.shape == x.shape
    assert gain.min() >= 1.0 - 1e-6                    # upward only


def test_silence_is_left_alone():
    gain, stats = voice_level.gain(np.zeros(SR * 5, dtype=np.float32), SR)
    assert np.allclose(gain, 1.0)
    assert stats["lifted_pct"] == 0


def test_too_short_for_one_reading_is_left_alone():
    x = speech((0.5, -20))
    gain, stats = voice_level.gain(x, SR)
    assert gain.shape == x.shape and np.allclose(gain, 1.0)


def _tone(path, parts):
    """A mono file of pink-noise runs (seconds, dB), which ebur128 reads like speech."""
    inputs, labels = [], []
    for i, (secs, db) in enumerate(parts):
        inputs += ["-f", "lavfi", "-i", f"anoisesrc=color=pink:duration={secs}:sample_rate=48000:seed={i + 1}"]
        labels.append(f"[{i}:a]volume={db}dB[a{i}]")
    joined = "".join(f"[a{i}]" for i in range(len(parts)))
    fc = ";".join(labels) + f";{joined}concat=n={len(parts)}:v=0:a=1[out]"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", fc,
                    "-map", "[out]", "-ac", "1", str(path)], check=True)


def _duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True, check=True).stdout
    return float(out)


def test_level_file_clears_the_quiet_stretch_on_a_class_style_file(tmp_path):
    src, dst = tmp_path / "class.wav", tmp_path / "levelled.wav"
    _tone(src, [(40, -6), (30, -18), (40, -6)])
    before = audio_qc.problems(audio_qc.measure(src))
    assert any("quiet stretch" in p for p in before), before
    stats = voice_level.level_file(src, dst)
    after = audio_qc.problems(audio_qc.measure(dst))
    assert after == [], after
    assert stats["max_db"] == pytest.approx(11.0, abs=1.0)
    assert _duration(dst) == pytest.approx(_duration(src), abs=0.01)
