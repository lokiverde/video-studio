"""Beat grid for the listing video: tempo, where the first beat lands, and how many
beats each photo holds so every cut lands on the music.

Same onset-envelope approach as surfer_reel.cmd_beats, plus a tempo estimate
(autocorrelation) so a new bed does not need its BPM typed in. The brand file's
`bpm` is a hint that keeps the estimate from locking onto half or double time.
"""
import subprocess
from dataclasses import dataclass
from pathlib import Path

SR = 11025
HOP = 256


@dataclass(frozen=True)
class Segment:
    start: float
    dur: float

    @property
    def end(self) -> float:
        return self.start + self.dur


def onset_envelope(path: Path):
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32)
    frames = len(x) // HOP
    env = np.sqrt(np.mean(x[:frames * HOP].reshape(frames, HOP) ** 2, axis=1))
    return np.maximum(0, np.diff(env)), SR / HOP


def estimate_bpm(onset, fr: float, hint: float | None = None, lo: float = 60, hi: float = 160) -> float:
    import numpy as np
    if hint:
        lo, hi = hint * 0.92, hint * 1.08
    o = onset - onset.mean()
    ac = np.correlate(o, o, mode="full")[len(o) - 1:]
    lags = np.arange(int(fr * 60 / hi), int(fr * 60 / lo) + 1)
    best = lags[int(np.argmax(ac[lags]))]
    return round(60 * fr / best, 1)


def grid_score(onset, fr: float, bpm: float, phase: float) -> float:
    """Onset energy collected by a beat grid. Each grid point takes the strongest
    frame within +-1 frame so rounding to the envelope's frame rate does not matter."""
    import numpy as np
    idx = np.round(np.arange(phase, len(onset) / fr - 0.05, 60 / bpm) * fr).astype(int)
    idx = idx[(idx > 0) & (idx < len(onset) - 1)]
    return float(np.maximum(np.maximum(onset[idx - 1], onset[idx]), onset[idx + 1]).sum())


def best_phase(onset, fr: float, bpm: float) -> tuple[float, float]:
    import numpy as np
    scores = [(grid_score(onset, fr, bpm, p), float(p)) for p in np.arange(0, 60 / bpm, 0.01)]
    score, phase = max(scores)
    return phase, score


def refine(onset, fr: float, bpm: float) -> tuple[float, float]:
    """The autocorrelation lag is quantized to whole envelope frames, which at ~43
    frames a second is a couple of BPM off: 2 BPM drifts a full beat in a minute.
    Search 0.05 BPM steps around the estimate against the whole track instead."""
    import numpy as np
    best = (-1.0, bpm, 0.0)
    for cand in np.arange(bpm - 3, bpm + 3, 0.05):
        phase, score = best_phase(onset, fr, float(cand))
        if score > best[0]:
            best = (score, float(cand), phase)
    return round(best[1], 2), round(best[2], 2)


def analyze(path: Path, hint: float | None = None) -> dict:
    onset, fr = onset_envelope(path)
    bpm, offset = refine(onset, fr, float(estimate_bpm(onset, fr, hint)))
    return {"bpm": bpm, "offset": offset}


def beats_per_photo(n_photos: int, bpm: float, target: float, open_beats: int,
                    card_seconds: float, min_beats: int = 2, max_beats: int = 8) -> int:
    beat = 60 / bpm
    tour = max(target - open_beats * beat - card_seconds, beat * min_beats)
    per = round(tour / beat / max(n_photos - 1, 1))
    return max(min_beats, min(max_beats, per))


def timeline(n_photos: int, bpm: float, target: float, open_beats: int, card_seconds: float,
             overrides: dict | None = None) -> tuple[list[Segment], Segment]:
    """Photo segments (cut to cut, every cut on a beat) plus the end-card segment.
    `overrides` maps a photo index to its own beat count (a hero shot held longer)."""
    beat = 60 / bpm
    per = beats_per_photo(n_photos, bpm, target, open_beats, card_seconds)
    segments, t = [], 0.0
    for i in range(n_photos):
        count = (overrides or {}).get(i, open_beats if i == 0 else per)
        dur = round(count * beat, 4)
        segments.append(Segment(round(t, 4), dur))
        t += dur
    return segments, Segment(round(t, 4), card_seconds)
