"""Room voice: the voice track for class and room recordings (th.py enhance --room before the
render, th.py revoice --room after it).

The local AI voice (Resemble Enhance) is generative. In a room it turns off-mic speech
(attendee questions, Tony walking away from the mic) into confident gibberish: on the Nov 2026
class video the word check found 95 problems and "had ChatGPT do the whole report" came out
as "never chashed or". Splicing raw audio into those gaps was worse to listen to: the AI
leaves dead-silent pauses and the raw track has room tone, so the room switched on and off
92 times, and the AI runs about 21 ms behind the camera, so every crossfade doubled the voice.

The room voice uses the same enhancer in denoise-only mode on the whole raw track: a mask
denoiser that never invents words and keeps the camera's timing (0 ms lag). A little raw goes
back under it so pauses keep their air, ROOM_EQ (fitted on that class video to the approved
AI voice) sets the tone, and a compressor just over the typical level holds the loud end.
9 ASR differences against the raw track, against 95 for the AI voice. Quiet attendees still
need th.py level afterwards.

The raw underlay is notched at the mains hum first (HUM_HZ): the denoiser takes the hum out
of its own track, but the raw one carried the office's 120 Hz line straight back in (+12 dB
over its neighbours in the pauses on the class video, gone after a notch). Only the underlay:
a notch that narrow on the whole mix rings Tony's own 120 Hz voice into every pause (the line
went UP to +10 dB on the class video), while at -26 dB the underlay's ringing stays inaudible."""
from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

import th_lib

RAW_UNDER_DB = -26.0    # raw camera track under the denoised one: air in the pauses, not hiss
# Octave EQ fitted on the class video (DJI camera in the office) to the AI voice's tone, three
# passes; the 63 Hz boost is capped at +2 because the AI invents low end and a room mic there
# only brings up rumble. Re-fit if the room or the mic changes.
ROOM_EQ = [(63, 2.0), (125, 1.4), (250, 0.6), (500, 0.8), (1000, -1.3), (2000, -0.3), (4000, -6.0),
           (8000, 2.1), (12000, -2.3)]
# Mains hum and its harmonics: true notches (bandreject, Q 30, a few Hz wide) on the raw underlay
# only. A peaking EQ cut this deep dipped 100 to 210 Hz by about 1.2 dB; the notch moves the
# voice band less than 0.15 dB and takes the hum down 33 to 80 dB.
HUM_HZ = (60, 120, 180, 240)
HUM_Q = 30
COMP_OVER_DB = 3.0      # compressor threshold over the typical speech level: the camera swings with every
                        # step Tony takes (385 half-second blocks 6 dB over typical on the class video, 0 after)
SEARCH_S = 0.3          # how far either side of the expected spot a segment is looked for
MATCH_S = 12.0          # seconds of a segment used to find it
SLIVER_S = 1.0          # a segment shorter than this (0.02 s between two cuts) keeps the last offset


def denoise_cmd(python: Path, enhancer: Path, src: Path, dst: Path) -> list[str]:
    """The enhancer in denoise-only mode. About 1 minute for 26 minutes of audio on the M3."""
    return [str(python), str(enhancer), str(src), str(dst), "--mode", "denoise"]


def blend(dn: np.ndarray, raw: np.ndarray, under_db: float = RAW_UNDER_DB) -> np.ndarray:
    """Denoised voice with the raw track under it, trimmed to the shorter of the two."""
    n = min(len(dn), len(raw))
    return (dn[:n] + raw[:n] * 10 ** (under_db / 20)).astype(np.float32)


def dehum_chain() -> str:
    return ",".join(f"bandreject=f={hz}:t=q:w={HUM_Q}" for hz in HUM_HZ)


def dehum(x: np.ndarray, sr: int) -> np.ndarray:
    """x with the mains hum notched out, same length."""
    out = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1",
                          "-i", "-", "-af", dehum_chain(), "-f", "f32le", "-"],
                         input=x.astype("<f4").tobytes(), capture_output=True, check=True).stdout
    y = np.frombuffer(out, dtype=np.float32)
    return np.pad(y, (0, max(0, len(x) - len(y))))[:len(x)]


def room_mix(dn: np.ndarray, raw: np.ndarray, sr: int, under_db: float = RAW_UNDER_DB) -> np.ndarray:
    """The room voice before tone: the denoised track with the dehummed raw track under it.
    The denoised track is never notched (see the module note on ringing)."""
    return blend(dn, dehum(raw, sr), under_db)


def eq_chain() -> str:
    """Tone chain for the room voice: rumble filter and ROOM_EQ. No second denoiser, no gate."""
    return ",".join(["highpass=f=70"] + [f"equalizer=f={hz}:t=o:w=1:g={g}" for hz, g in ROOM_EQ])


def speech_level(x: np.ndarray, sr: int) -> float:
    """Typical speech level in dBFS: the median 100 ms reading within 25 dB of the loud end."""
    hop = sr // 10
    m = len(x) // hop
    db = 10 * np.log10(np.maximum((x[:m * hop].reshape(m, hop).astype(np.float64) ** 2).mean(1), 1e-12))
    return float(np.median(db[db > np.percentile(db, 95) - 25]))


def room_chain(typical_db: float) -> str:
    """eq_chain plus a compressor from COMP_OVER_DB over the voice. th.py level lifts the quiet
    attendees after the render; this brings the loud end down to meet them."""
    return (f"{eq_chain()},acompressor=threshold={typical_db + COMP_OVER_DB:.1f}dB:ratio=4:attack=5:release=120:"
            f"knee=4:detection=rms")


def kept_segments(cuts: list, src_end: float) -> list[tuple[float, float]]:
    """Source spans that survive the cuts, in order."""
    keep, t = [], 0.0
    for a, b in sorted(cuts):
        keep.append((t, a))
        t = b
    keep.append((t, src_end))
    return keep


def best_offset(ref: np.ndarray, sig: np.ndarray, at: float, length: float, sr: int,
                search: float = SEARCH_S) -> float:
    """Seconds past `at` where `sig` sits in `ref`, by cross-correlation."""
    seg = sig[:int(min(length, MATCH_S) * sr)]
    lo = max(0, int((at - search) * sr))
    win = ref[lo:lo + len(seg) + int(2 * search * sr)]
    if len(win) < len(seg) or not seg.any():
        return 0.0
    n = 1 << (len(win) + len(seg)).bit_length()
    c = np.fft.irfft(np.fft.rfft(win, n) * np.conj(np.fft.rfft(seg, n)), n)[:len(win) - len(seg) + 1]
    return (lo + int(np.argmax(c))) / sr - at


def segment_offsets(rendered: np.ndarray, used: np.ndarray, keep: list, cuts: list, sr: int) -> list[float]:
    """Where the render put each kept segment of `used` (the audio Remotion played), relative to
    th_lib.to_output. Remotion snaps segments to frames: 20 to 65 ms late on the class video."""
    offsets: list[float] = []
    for a, b in keep:
        if b - a < SLIVER_S:
            offsets.append(offsets[-1] if offsets else 0.0)
            continue
        offsets.append(best_offset(rendered, used[int(a * sr):int(b * sr)], th_lib.to_output(a, cuts), b - a, sr))
    return offsets


def place(tracks: dict, keep: list, offsets: list, cuts: list, total: float, sr: int) -> dict:
    """Source-timeline tracks moved onto the rendered timeline, segment by segment, sample index
    for sample index with the audio the render used, so they keep its sync with the picture."""
    size = int(round(total * sr))
    out = {}
    for name, x in tracks.items():
        y = np.zeros(size, dtype=np.float32)
        for (a, b), off in zip(keep, offsets):
            start = int(round((th_lib.to_output(a, cuts) + off) * sr))
            seg = x[int(round(a * sr)):int(round(b * sr))]
            if start < size and len(seg):
                y[start:start + len(seg)] = seg[:size - start]
        out[name] = y
    return out


def load(path: Path, sr: int) -> np.ndarray:
    """Any file's first audio stream as mono float32."""
    out = subprocess.run(["ffmpeg", "-nostdin", "-loglevel", "error", "-i", str(path), "-vn", "-ac", "1",
                          "-ar", str(sr), "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(out, dtype=np.float32)


def save(x: np.ndarray, sr: int, path: Path) -> None:
    subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1",
                    "-i", "-", "-c:a", "pcm_f32le", str(path)], input=x.astype("<f4").tobytes(), check=True)
