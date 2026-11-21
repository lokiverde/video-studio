"""Loudness for finished videos: one straight gain to TARGET_I plus a peak limiter, so
every final plays at the same level in the feed.

The mix chain's dynaudnorm evens the level out but never aims at a target, which is why
finals landed at -19 to -21 LUFS before 2026-10-09. Dynamic loudnorm fixed the level the
same day but acts like an automatic gain: it lifts the gaps between words, and with them
the room echo of the cloned voice. A straight gain keeps the dynamics exactly as mixed and
the limiter only touches the loudest syllables (same approach as th.py). Tony heard -15
LUFS as "a little too loud", so the target is -16.

Rewrites only the audio track and copies the video stream untouched."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

TARGET_I = -16.0    # integrated loudness, LUFS (Tony 2026-10-09: -15 was a little loud)
TOLERANCE = 0.4     # LU; outside this the gain is topped up once
# Linear ceiling for the limiter, about -2 dBFS. Run at 4x oversampling it approximates a
# true-peak limit; th.py measured +1.1 dBTP after AAC without the oversampling.
LIMIT = 0.79
SAMPLE_RATE = "48000"

_JSON_BLOCK = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}", re.S)


def first_pass_filter() -> str:
    """Measurement only: loudnorm prints the input loudness as JSON."""
    return f"loudnorm=I={TARGET_I:g}:TP=-1.5:LRA=11:print_format=json"


def parse(stderr: str) -> dict:
    """The measurement JSON loudnorm prints at the end of ffmpeg's stderr."""
    match = _JSON_BLOCK.search(stderr)
    if not match:
        raise ValueError("loudnorm printed no measurement (is there an audio stream?)")
    return json.loads(match.group(0))


def measure(path: Path) -> float:
    """Integrated loudness of a file, LUFS."""
    out = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-vn",
                          "-af", first_pass_filter(), "-f", "null", "-"],
                         capture_output=True, text=True, check=True).stderr
    return float(parse(out)["input_i"])


def level_chain(input_i: float, extra_db: float = 0.0) -> str:
    gain = round(TARGET_I - input_i + extra_db, 1)
    return (f"volume={gain}dB,aresample=192000,"
            f"alimiter=limit={LIMIT}:attack=2:release=50:level=disabled,aresample={SAMPLE_RATE}")


def _render(src: Path, dst: Path, chain: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-af", chain,
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                    str(dst)], check=True)


def normalize(path: Path) -> float:
    """Bring a finished mp4 to TARGET_I in place. Returns the loudness it started at.
    The limiter shaves a little off, so measure the result and top it up once."""
    path = Path(path)
    before = measure(path)
    tmp = path.with_name(f".level_{path.name}")
    try:
        _render(path, tmp, level_chain(before))
        got = measure(tmp)
        if abs(got - TARGET_I) > TOLERANCE:
            _render(path, tmp, level_chain(before, TARGET_I - got))
            got = measure(tmp)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    print(f"[loudness] {path.name}: {before:.1f} -> {got:.1f} LUFS (target {TARGET_I:g})")
    return before
