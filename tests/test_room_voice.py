"""Room voice for class and room recordings (th.py enhance --room, th.py revoice --room).

The Nov 2026 class video showed why the local AI voice fails in a room: Resemble Enhance turns
off-mic speech into confident gibberish (word check: 95 problems), and splicing raw audio into
the gaps switched the room tone on and off 92 times. Denoise-only on the whole raw track kept
every word (9 ASR differences), with 0 ms lag against the camera."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import room_voice  # noqa: E402
import th_lib  # noqa: E402
import voice_level  # noqa: E402

SR = 8000


def test_denoise_runs_the_enhancer_in_denoise_mode_only():
    cmd = room_voice.denoise_cmd(Path("/py"), Path("/enh.py"), Path("in.wav"), Path("out.wav"))
    assert cmd[:4] == [str(Path("/py")), str(Path("/enh.py")), "in.wav", "out.wav"]
    assert cmd[cmd.index("--mode") + 1] == "denoise"


def test_the_raw_track_goes_back_under_the_denoised_one_for_air():
    dn = np.ones(10, dtype=np.float32)
    raw = np.ones(12, dtype=np.float32)
    out = room_voice.blend(dn, raw)
    assert len(out) == 10
    assert out[0] == pytest.approx(1 + 10 ** (room_voice.RAW_UNDER_DB / 20))
    assert -30 <= room_voice.RAW_UNDER_DB <= -20      # air, not hiss


def test_the_room_chain_never_denoises_or_gates_a_second_time():
    chain = room_voice.eq_chain()
    assert chain.startswith("highpass=")
    for hz, g in room_voice.ROOM_EQ:
        assert f"equalizer=f={hz}:" in chain and f"g={g}" in chain
    assert "afftdn" not in chain and "agate" not in chain and "anlmdn" not in chain


def test_the_low_end_is_never_boosted_much():
    # The AI voice invents low end; boosting a room mic there only adds rumble.
    assert dict(room_voice.ROOM_EQ)[63] <= 2.0


def test_kept_segments_are_the_spaces_between_cuts():
    assert room_voice.kept_segments([[10, 12], [0, 2], [20, 25]], 30) == [(0.0, 0), (2, 10), (12, 20), (25, 30)]


def test_best_offset_finds_a_known_shift():
    rng = np.random.default_rng(3)
    sig = rng.standard_normal(SR * 4).astype(np.float32)
    ref = np.concatenate([np.zeros(int(SR * 5.04)), sig, np.zeros(SR)]).astype(np.float32)
    assert room_voice.best_offset(ref, sig, 5.0, 4.0, SR) == pytest.approx(0.04, abs=1.5 / SR)


def test_place_puts_each_segment_where_the_render_put_it():
    cuts = [[2.0, 3.0]]
    keep = room_voice.kept_segments(cuts, 6.0)
    src = np.zeros(SR * 6, dtype=np.float32)
    src[int(SR * 1.0)] = 1.0     # before the cut: output 1.0
    src[int(SR * 4.0)] = 1.0     # after the cut: output 3.0
    placed = room_voice.place({"v": src}, keep, [0.0, 0.05], cuts, 5.0, SR)["v"]
    hits = np.flatnonzero(placed) / SR
    assert hits[0] == pytest.approx(1.0, abs=1 / SR)
    assert hits[1] == pytest.approx(3.05, abs=1 / SR)
    assert len(placed) == SR * 5


def test_a_room_voice_counts_as_finished_for_the_sheet_and_render():
    assert th_lib.voice_is_final({"voice": "room"})


def _speech(*runs, seed=1):
    rng = np.random.default_rng(seed)
    return np.concatenate([rng.standard_normal(int(s * SR)) * 10 ** (db / 20) for s, db in runs]).astype(np.float32)


def _rms_db(x):
    return 10 * np.log10(np.mean(x.astype(np.float64) ** 2))


def test_a_normal_word_inside_a_quiet_stretch_is_not_blasted():
    # Class video, 4:00 to 5:20: the leveller lifted Tony's normal-level words 4 to 12 dB
    # because they sat inside an attendee's quiet stretch.
    x = _speech((30, -20), (10, -32), (1, -20), (10, -32), (30, -20))
    gain, stats = voice_level.gain(x, SR)
    y = x * gain
    word = slice(int(40.2 * SR), int(40.8 * SR))
    assert _rms_db(y[word]) <= stats["voice_db"] + voice_level.LV_CEILING + 0.5
    quiet = slice(int(34 * SR), int(36 * SR))
    assert _rms_db(y[quiet]) - _rms_db(x[quiet]) == pytest.approx(11.0, abs=0.7)   # the attendee still comes up
    assert gain.min() >= 1.0 - 1e-6                                                # still upward only


def test_speech_level_reads_the_typical_level_and_skips_pauses():
    x = _speech((20, -20), (5, -90), (20, -20))
    assert room_voice.speech_level(x, SR) == pytest.approx(-20.0, abs=0.5)


def test_the_compressor_sits_just_over_the_typical_level():
    # A camera across the room swings with every step Tony takes: on the class video the
    # uncompressed room voice had 385 half-second blocks 6 dB over his typical level.
    chain = room_voice.room_chain(-30.0)
    assert chain.startswith(room_voice.eq_chain() + ",")
    comp = chain.split(",")[-1]
    assert comp.startswith("acompressor=")
    assert f"threshold={-30.0 + room_voice.COMP_OVER_DB:.1f}dB" in comp and "ratio=4" in comp


def test_the_ceiling_glides_and_never_lets_a_reading_past_it():
    x = _speech((10, -32), (0.3, -20), (10, -32))
    t, cap = voice_level.ceiling_db(x, SR, -20.0)
    sq = np.concatenate([[0.0], np.cumsum(x.astype(np.float64) ** 2)])
    win = int(voice_level.CEIL_WIN * SR)
    starts = (np.round(t * SR) - win / 2).astype(int)
    level = 10 * np.log10((sq[starts + win] - sq[starts]) / win)
    assert np.all(level + cap <= -20.0 + voice_level.LV_CEILING + 1e-6)
    assert np.abs(np.diff(cap)).max() < 3.0          # dB per 10 ms: no hard step, no click
    assert len(cap) == len(t)


HUM_SR = 48000


def _tone_db(x: np.ndarray, hz: float, sr: int) -> float:
    """Level of one sine in x, in dB, read off a Hann-windowed FFT bin."""
    n = len(x)
    spec = np.abs(np.fft.rfft(x * np.hanning(n)))
    k = int(round(hz * n / sr))
    return 20 * np.log10(spec[k - 2:k + 3].max() + 1e-12)


def _tones(freqs, seconds: float = 2.0, sr: int = HUM_SR) -> np.ndarray:
    t = np.arange(int(seconds * sr)) / sr
    return sum(0.1 * np.sin(2 * np.pi * f * t) for f in freqs).astype(np.float32)


def test_dehum_takes_the_mains_hum_out_of_the_raw_track():
    # The class video office: a 120 Hz line 12 dB over its neighbours in every pause.
    x = _tones([60, 120, 180, 240])
    y = room_voice.dehum(x, HUM_SR)
    assert len(y) == len(x)
    for hz in (60, 120, 180, 240):
        assert _tone_db(y[HUM_SR // 2:], hz, HUM_SR) < _tone_db(x[HUM_SR // 2:], hz, HUM_SR) - 18


def test_dehum_leaves_the_voice_band_alone():
    x = _tones([100, 150, 300, 1000, 3000])
    y = room_voice.dehum(x, HUM_SR)
    for hz in (100, 150, 300, 1000, 3000):
        assert abs(_tone_db(y[HUM_SR // 2:], hz, HUM_SR) - _tone_db(x[HUM_SR // 2:], hz, HUM_SR)) < 1.0


def test_the_room_mix_carries_no_hum_from_the_raw_underlay():
    dn = _tones([1000])
    raw = _tones([120])
    mix = room_voice.room_mix(dn, raw, HUM_SR)
    plain = room_voice.blend(dn, raw)
    assert _tone_db(mix[HUM_SR // 2:], 120, HUM_SR) < _tone_db(plain[HUM_SR // 2:], 120, HUM_SR) - 18
    assert abs(_tone_db(mix[HUM_SR // 2:], 1000, HUM_SR) - _tone_db(plain[HUM_SR // 2:], 1000, HUM_SR)) < 0.5


def test_the_denoised_voice_itself_is_never_notched():
    # A Q 30 notch on the whole mix rang Tony's own 120 Hz fundamental into every pause.
    dn = _tones([120])
    raw = np.zeros_like(dn)
    mix = room_voice.room_mix(dn, raw, HUM_SR)
    assert np.allclose(mix, dn)
