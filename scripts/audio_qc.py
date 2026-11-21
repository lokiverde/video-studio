"""Audio QC gate for finished videos: level, true peak, loudness range and quiet stretches,
all read from ffmpeg's ebur128 log (no numpy, so the Mac mini's plain python runs it too).

Hitting the loudness target is not enough. The Nov 2026 class video measured -14.0 LUFS
with clean peaks, but four attendee stretches sat 12 LU under Tony's voice (LRA 12.8 LU),
so a listener on a phone loses them. A podcast reference (Tom Bilyeu, -15.7 LUFS) stays
within about 3 LU for 37 minutes, and Tony's other finals sit at 3.6 to 5.8 LU.

    python3 scripts/audio_qc.py out/final_16x9.mp4 [--target -14]

Exit 1 when any file has a problem, with the timestamps to listen to."""
from __future__ import annotations

import argparse
import math
import re
import statistics
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

GATE_LU = 20.0       # frames more than this under integrated are pauses or end cards (ebur128's relative gate)
BLOCK_S = 10         # quiet stretches are judged on 10 s blocks: one soft sentence does not count
MIN_FRAMES = 20      # a block needs 2 s of speech to be judged
UNDER_LU = 6.0       # a block this far under the typical block is a quiet stretch (about half as loud)
MAX_LRA = 8.0        # Tony's finals 3.6 to 5.8, class clips up to 8.1, podcasts about 3
MAX_TP = -1.0        # dBTP ceiling (Apple Podcasts spec, and headroom for YouTube's encode)
TARGET_TOL = 1.0     # LU either side of the pipeline's target
QUIET_FIX = "off-mic speech? th.py level <job> lifts it"   # talking head; no re-render

_FRAME = re.compile(r"\bt:\s*([\d.]+)\s.*?\bS:\s*(-?[\d.]+|-inf)")
_I = re.compile(r"\bI:\s+(-?[\d.]+) LUFS")
_LRA = re.compile(r"\bLRA:\s+([\d.]+) LU")
_PEAK = re.compile(r"\bPeak:\s+(-?[\d.]+|-inf) dBFS")


class Stretch(NamedTuple):
    start: int      # seconds on the file's timeline
    end: int
    low: float      # quietest block in the stretch, LUFS short-term
    under: float    # LU under the typical block (negative)


def parse(stderr: str) -> dict:
    """ebur128's frame log and summary: {"I", "LRA", "TP", "frames": [(t, S), ...]}."""
    cut = stderr.rfind("Summary:")
    if cut < 0:
        raise ValueError("ebur128 printed no summary (is there an audio stream?)")
    summary, body = stderr[cut:], stderr[:cut]
    found = {"I": _I.search(summary), "LRA": _LRA.search(summary)}
    if not all(found.values()):
        raise ValueError("ebur128 summary is missing integrated loudness or loudness range")
    peak = _PEAK.search(summary)
    frames = [(float(t), float(s)) for t, s in _FRAME.findall(body) if s != "-inf"]
    return {"I": float(found["I"].group(1)), "LRA": float(found["LRA"].group(1)),
            "TP": float(peak.group(1)) if peak else None, "frames": frames}


def measure(path: Path) -> dict:
    """Run ebur128 (true peak on) over a file's audio."""
    out = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-nostats", "-i", str(path), "-vn",
                          "-af", "ebur128=peak=true:framelog=info", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    return parse(out)


def _block_levels(frames: list[tuple[float, float]], integrated: float) -> list[tuple[int, float]]:
    """(block start, median short-term) for every 10 s block with enough speech in it. The
    file's last block is the outro (end card, music tail, a pad under the last words) and is
    never judged."""
    if not frames:
        return []
    gate = integrated - GATE_LU
    last = int(frames[-1][0] // BLOCK_S)
    blocks: dict[int, list[float]] = {}
    for t, s in frames:
        if s > gate:
            blocks.setdefault(int(t // BLOCK_S), []).append(s)
    return [(b * BLOCK_S, statistics.median(v)) for b, v in sorted(blocks.items())
            if len(v) >= MIN_FRAMES and b != last]


def quiet_stretches(frames: list[tuple[float, float]], integrated: float) -> list[Stretch]:
    """Runs of 10 s blocks sitting UNDER_LU or more under the typical block. Pauses and silent
    end cards fall under the gate and never count."""
    levels = _block_levels(frames, integrated)
    if len(levels) < 3:
        return []
    typical = statistics.median(level for _, level in levels)
    out: list[Stretch] = []
    for start, level in levels:
        if level > typical - UNDER_LU:
            continue
        last = out[-1] if out else None
        if last and start <= last.end:
            low = min(last.low, level)
            out[-1] = Stretch(last.start, start + BLOCK_S, low, round(low - typical, 1))
        else:
            out.append(Stretch(start, start + BLOCK_S, level, round(level - typical, 1)))
    return out


def _clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


def problems(m: dict, target: float | None = None) -> list[str]:
    """Everything to fix before Tony hears it. `target` is the pipeline's LUFS target, if any."""
    found = []
    if target is not None and abs(m["I"] - target) > TARGET_TOL:
        found.append(f"level {m['I']:.1f} LUFS, target {target:g} (±{TARGET_TOL:g})")
    if m["TP"] is not None and not math.isinf(m["TP"]) and m["TP"] > MAX_TP:
        found.append(f"true peak {m['TP']:.1f} dBTP, ceiling {MAX_TP:g}")
    if m["LRA"] > MAX_LRA:
        found.append(f"loudness range {m['LRA']:.1f} LU, max {MAX_LRA:g} (podcasts sit near 3, "
                     f"Tony's finals 4 to 6): the level swings")
    for s in quiet_stretches(m["frames"], m["I"]):
        found.append(f"quiet stretch {_clock(s.start)}-{_clock(s.end)}, {s.under:+.1f} LU under the voice "
                     f"(low {s.low:.1f} LUFS): {QUIET_FIX}")
    return found


def summary(m: dict) -> str:
    tp = "n/a" if m["TP"] is None else f"{m['TP']:.1f}"
    return f"{m['I']:.1f} LUFS, true peak {tp} dBTP, range {m['LRA']:.1f} LU"


def check(path: Path, target: float | None = None, label: str = "audio QC") -> list[str]:
    """Measure, print one line (plus the problems), return the problems."""
    m = measure(path)
    found = problems(m, target)
    head = f"[{label}] {Path(path).name}: {summary(m)}"
    print(head + (" ok" if not found else " PROBLEMS\n  " + "\n  ".join(found)))
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--target", type=float, default=None, help="pipeline LUFS target (-14 talking head, -16 faceless)")
    args = ap.parse_args(argv)
    bad = [f for f in args.files if check(f, args.target)]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
