"""Synthesize a quiet ambient pad for voice-led videos: slow warm chords, no beat, no melody.

Made 2026-11-10 after Tony disliked the listing bed under his own voice ("wrong theme, too
loud"). A pad sits under talk without competing: nothing rhythmic for the ear to follow,
nothing in the upper voice range. Ours from scratch, so there is no license question.

    /usr/local/bin/python3 tools/make_ambient_bed.py assets/music/operator-ambient.mp3

Pure numpy for the tones, ffmpeg for the room (two soft echoes), the fades and the mp3.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

RATE = 44100
CHORD_S = 16.0        # each chord rings this long
FADE_S = 5.0          # chords cross-fade over this long, so there is never a hard change
DETUNE_CENTS = 4.0    # two slightly detuned voices per note give the pad its slow shimmer
HARMONICS = (1.0, 0.30, 0.10, 0.04)   # soft and dark: little above the third harmonic
TARGET_LUFS = -16     # about as loud as the other beds; music_volume sets it under voice

# D add9, B minor 7, G major 7, A sus2, twice: warm, unresolved, never sad. MIDI numbers,
# kept between G2 and F#4 so the pad stays under the voice's presence range.
PROGRESSION = [
    (50, 57, 62, 64, 66),
    (47, 54, 59, 62, 66),
    (43, 50, 55, 59, 66),
    (45, 52, 57, 59, 64),
] * 2


def _hz(midi: int) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _note(midi: int, t: np.ndarray, phase: float) -> np.ndarray:
    tone = np.zeros_like(t)
    for cents in (-DETUNE_CENTS / 2, DETUNE_CENTS / 2):
        f = _hz(midi) * 2 ** (cents / 1200)
        for k, amp in enumerate(HARMONICS, start=1):
            tone += amp * np.sin(2 * np.pi * f * k * t + phase * k)
    return tone


def _envelope(n: int, fade: int) -> np.ndarray:
    env = np.ones(n)
    ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, fade))
    env[:fade], env[-fade:] = ramp, ramp[::-1]
    return env


def render(seed: int = 7) -> np.ndarray:
    rng = np.random.default_rng(seed)
    step, fade = int(CHORD_S * RATE), int(FADE_S * RATE)
    n_chord = step + fade
    out = np.zeros(step * len(PROGRESSION) + fade)
    t = np.arange(n_chord) / RATE
    swell = 1 + 0.08 * np.sin(2 * np.pi * t / 7.3)   # a slow breath, not a tremolo
    for i, chord in enumerate(PROGRESSION):
        voices = sum(_note(m, t, rng.uniform(0, 2 * np.pi)) for m in chord)
        out[i * step:i * step + n_chord] += voices * swell * _envelope(n_chord, fade)
    return out / np.max(np.abs(out)) * 0.5


def _write_wav(path: Path, mono: np.ndarray) -> None:
    pcm = (np.clip(mono, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(pcm.tobytes())


def main(dest: str) -> None:
    out = Path(dest)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "pad.wav"
        _write_wav(raw, render())
        total = CHORD_S * len(PROGRESSION) + FADE_S
        room = "aecho=0.8:0.6:83|131:0.25|0.18,lowpass=f=2200"
        fades = f"afade=t=in:d=3,afade=t=out:st={total - 4:.1f}:d=4"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-af",
                        f"{room},{fades},loudnorm=I={TARGET_LUFS}:TP=-2",
                        "-ac", "2", "-ar", str(RATE), "-b:a", "192k", str(out)], check=True)
    print(f"[bed] {out} ({total:.0f}s)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: make_ambient_bed.py OUT.mp3")
    main(sys.argv[1])
