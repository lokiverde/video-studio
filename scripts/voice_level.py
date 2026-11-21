"""Upward leveller for class and room recordings (th.py level).

Off-mic speech (attendee questions, Tony away from the mic) sits far under the voice, so a
final can hit -14 LUFS and still swing. The Nov 2026 class video had four attendee stretches
12 LU under Tony (loudness range 12.8 LU). This lifts speech that sits more than LV_DEADBAND
under the typical level up to LV_LIFT_TO under it (at most LV_MAX_UP), holds the gain through
pauses so room tone is never pumped up between words, and glides every change over
LV_SMOOTH. Upward only and sample for sample: nothing is cut, Tony's normal delivery is inside
the deadband and untouched. On that class video it took the range from 12.8 to 5.1 LU.

Promoted from that job's hybrid_voice.py (level_quiet) with one change: each 1 s reading is
measured on its active 0.1 s blocks only, so the window running from speech into a pause no
longer reads as quiet speech. Same 5.1 LU on the class mix, and true pauses hold +9 dB
instead of +15 dB.

The caller re-applies the loudness chain afterwards (th._level_chain), which also limits the
peaks the lift brings up."""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

SR = 48000
LV_WIN = 1.0       # seconds of audio per level reading
LV_HOP = 0.1       # seconds between readings
LV_GATE = 30.0     # dB under the voice: below this it is a pause, hold the gain
LV_MAX_UP = 15.0   # dB, never lift more than this (room noise comes up with the voice)
LV_DEADBAND = 3.0  # dB under the typical level before anything is lifted
LV_LIFT_TO = 1.0   # ...and then it comes up to 1 dB under the typical level
LV_SMOOTH = 0.6    # seconds, gain glide so the level never pumps
LV_CEILING = 5.0   # dB over the voice: a lifted 100 ms stretch never goes past this. Tony's
                   # normal-level words inside an attendee's quiet stretch were lifted 4 to 12 dB
                   # by the 1 s readings (class video, 4:00 to 5:20); this caps them.
CEIL_WIN = 0.1     # seconds per ceiling reading
CEIL_HOP = 0.01
CEIL_HOLD = 0.05   # the ceiling drops this early and recovers this late, so no syllable slips past
MIN_ACTIVE_S = 0.3            # a reading needs this much speech in it to be judged, else it is a pause
SPEECH_RANGE = LV_GATE + 10   # readings this far under the loudest one count toward the first voice guess
SILENT_DB = -100.0            # a reading this low everywhere is digital silence: nothing to level


def levels_db(x: np.ndarray, sr: int) -> np.ndarray:
    """RMS level in dB of LV_WIN windows every LV_HOP seconds."""
    win, hop = int(LV_WIN * sr), int(LV_HOP * sr)
    n = max(0, (len(x) - win) // hop + 1)
    sq = np.concatenate([[0.0], np.cumsum(x.astype(np.float64) ** 2)])
    starts = np.arange(n) * hop
    power = (sq[starts + win] - sq[starts]) / win
    return 10 * np.log10(np.maximum(power, 1e-12))


def active_levels_db(x: np.ndarray, sr: int, gate_db: float) -> np.ndarray:
    """Level of each LV_WIN reading measured on its active LV_HOP blocks only (those above
    gate_db), NaN where under MIN_ACTIVE_S of it is active (a pause). A plain RMS window
    that runs from speech into a pause reads as quiet speech on the way down; the one-off
    leveller held that lift (about 9 dB) through the pause and pumped the room up."""
    hop, per = int(LV_HOP * sr), int(round(LV_WIN / LV_HOP))
    nb = len(x) // hop
    n = max(0, nb - per + 1)
    if not n:
        return np.zeros(0)
    blocks = np.mean(x[:nb * hop].astype(np.float64).reshape(nb, hop) ** 2, axis=1)
    active = 10 * np.log10(np.maximum(blocks, 1e-12)) > gate_db
    psum = np.concatenate([[0.0], np.cumsum(blocks * active)])
    count = np.concatenate([[0], np.cumsum(active)])
    got, power = count[per:] - count[:-per], psum[per:] - psum[:-per]
    enough = got >= int(round(MIN_ACTIVE_S / LV_HOP))
    level = np.full(n, np.nan)
    level[enough] = 10 * np.log10(np.maximum(power[enough] / got[enough], 1e-12))
    return level


def _wanted_gain(levels: np.ndarray, ref: float) -> np.ndarray:
    """Gain in dB per reading before smoothing. Pauses (NaN) keep the last speech gain."""
    want = np.zeros(len(levels))
    g = 0.0
    for i, level in enumerate(levels):
        if not np.isnan(level):
            short = ref - level
            g = float(np.clip(short - LV_LIFT_TO, 0.0, LV_MAX_UP)) if short > LV_DEADBAND else 0.0
        want[i] = g
    return want


def _smooth(want: np.ndarray) -> np.ndarray:
    k = max(1, int(LV_SMOOTH / LV_HOP))
    kernel = np.ones(2 * k + 1) / (2 * k + 1)
    return np.convolve(np.pad(want, (k, k), mode="edge"), kernel, mode="same")[k:-k]


def _stats(ref: float, smooth: np.ndarray, speech: np.ndarray) -> dict:
    lifted = smooth[speech & (smooth > 1.0)]
    return {"voice_db": round(ref, 1),
            "lifted_pct": round(100 * len(lifted) / max(1, int(speech.sum()))),
            "median_db": round(float(np.median(lifted)), 1) if len(lifted) else 0.0,
            "max_db": round(float(smooth.max()), 1) if len(smooth) else 0.0}


def gain_curve(x: np.ndarray, sr: int) -> tuple[np.ndarray, np.ndarray, dict]:
    """(reading times in seconds, smoothed gain in dB, stats) for a mono voice track.
    Stats: voice_db (typical speech level), lifted_pct (share of speech lifted over 1 dB),
    median_db and max_db of the lift."""
    db = levels_db(x, sr)
    if not len(db) or db.max() <= SILENT_DB:
        return np.zeros(0), np.zeros(0), {"voice_db": None, "lifted_pct": 0, "median_db": 0.0, "max_db": 0.0}
    t = (np.arange(len(db)) * int(LV_HOP * sr) + int(LV_WIN * sr) // 2) / sr
    rough = float(np.median(db[db > db.max() - SPEECH_RANGE]))   # first guess, pauses and all
    levels = active_levels_db(x, sr, rough - LV_GATE)
    speech = ~np.isnan(levels)
    ref = float(np.median(levels[speech])) if speech.any() else rough
    smooth = _smooth(_wanted_gain(levels, ref))
    return t, smooth, _stats(ref, smooth, speech)


def ceiling_db(x: np.ndarray, sr: int, voice_db: float) -> tuple[np.ndarray, np.ndarray]:
    """(times, most lift in dB) so no CEIL_WIN reading ends up over voice_db + LV_CEILING.
    Never negative: speech that is already loud is left alone, not turned down."""
    win, hop = int(CEIL_WIN * sr), int(CEIL_HOP * sr)
    n = max(0, (len(x) - win) // hop + 1)
    if not n:
        return np.zeros(0), np.zeros(0)
    sq = np.concatenate([[0.0], np.cumsum(x.astype(np.float64) ** 2)])
    starts = np.arange(n) * hop
    level = 10 * np.log10(np.maximum((sq[starts + win] - sq[starts]) / win, 1e-12))
    room = np.maximum(voice_db + LV_CEILING - level, 0.0)
    # Hold the minimum over twice the glide, then glide: every reading averaged at t was already
    # at or under the room at t, so the smooth curve never lets a syllable past the ceiling.
    k = max(1, int(round(CEIL_HOLD / CEIL_HOP)))
    held = np.min(np.lib.stride_tricks.sliding_window_view(np.pad(room, (2 * k, 2 * k), mode="edge"), 4 * k + 1), axis=1)
    soft = np.convolve(np.pad(held, (k, k), mode="edge"), np.ones(2 * k + 1) / (2 * k + 1), mode="valid")
    return (starts + win / 2) / sr, soft


def gain(x: np.ndarray, sr: int) -> tuple[np.ndarray, dict]:
    """Linear gain per sample (same length as x, never under 1.0) and the stats. The lift is
    capped by ceiling_db, so a normal word inside a quiet stretch comes through at its own level."""
    t, smooth, stats = gain_curve(x, sr)
    if not len(t):
        return np.ones(len(x), dtype=np.float32), stats
    pos = np.arange(len(x)) / sr
    samples = np.interp(pos, t, smooth)
    ct, cap = ceiling_db(x, sr, stats["voice_db"])
    if len(ct):
        samples = np.minimum(samples, np.interp(pos, ct, cap))
    return (10 ** (np.maximum(samples, 0.0) / 20)).astype(np.float32), stats


def load(path: Path, sr: int = SR) -> np.ndarray:
    """Any file's first audio stream as mono float32 samples."""
    out = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path), "-vn", "-ac", "1",
                          "-ar", str(sr), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype=np.float32)


def save(x: np.ndarray, sr: int, path: Path) -> None:
    """Mono 32-bit float WAV: lifted peaks may pass 0 dBFS until the level chain limits them."""
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1",
                    "-i", "-", "-c:a", "pcm_f32le", str(path)], input=x.astype("<f4").tobytes(), check=True)


def level_file(src: Path, dst: Path, sr: int = SR) -> dict:
    """Lift the quiet speech in src's audio and write it to dst (mono WAV, same length)."""
    x = load(src, sr)
    g, stats = gain(x, sr)
    save(x * g, sr, dst)
    return stats
