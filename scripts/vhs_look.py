"""Shop VHS: the tape look from the Shop Wizard (Tony, 2026-10-18) over any finished
9:16 Shop video, whichever skill made it (archive-reel, surf-reel, storyboard-reel).

Tony's rules: 50% by default, PLAY readout over the opening, and the overlay is gone by the
time the shirt comes back (it fades out over --fade seconds, ending at --clean-from).
The recipe itself lives in sr_vhs.VHSPass; this only drives it over a file. Audio is copied
untouched, so the loudness the source was mastered to is kept.

  python3 scripts/vhs_look.py in.mp4 out_vhs.mp4 --clean-from 19.3
      [--strength 0.5] [--fade 0.7] [--osd "PLAY ▶"] [--osd-end 4.2] [--duration N]
"""
import argparse
import json
import subprocess
import sys

import numpy as np

import sr_vhs
from sr_shots import H, W

DEFAULT_STRENGTH = 0.5
DEFAULT_FADE = 0.7
DEFAULT_OSD = "PLAY ▶"
DEFAULT_OSD_END = 4.2


def mix(t: float, clean_from: float | None, fade: float) -> float:
    """How much of the tape look shows at t: 1 until the fade, eased to 0 at clean_from."""
    if clean_from is None:
        return 1.0
    if t >= clean_from:
        return 0.0
    if fade <= 0 or t <= clean_from - fade:
        return 1.0
    x = (clean_from - t) / fade
    return x * x * (3 - 2 * x)


def probe(src: str) -> tuple[float, float]:
    """(fps, duration seconds) of the first video stream."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=r_frame_rate:format=duration", "-of", "json", src],
                         capture_output=True, text=True, check=True)
    info = json.loads(out.stdout)
    num, den = info["streams"][0]["r_frame_rate"].split("/")
    return float(num) / float(den), float(info["format"]["duration"])


def apply(src: str, dst: str, strength: float = DEFAULT_STRENGTH, clean_from: float | None = None,
          fade: float = DEFAULT_FADE, osd: str = DEFAULT_OSD, osd_end: float = DEFAULT_OSD_END,
          duration: float | None = None) -> None:
    fps, length = probe(src)
    length = min(length, duration) if duration else length
    tape = sr_vhs.make({"strength": strength, "osd": osd, "osd_end": osd_end})
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", src, "-t", f"{length:.3f}",
                            "-vf", f"scale={W}:{H}:flags=lanczos", "-f", "rawvideo",
                            "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", f"{fps:.6f}", "-i", "-", "-i", src,
                            "-map", "0:v", "-map", "1:a?", "-t", f"{length:.3f}",
                            "-c:v", "libx264", "-preset", "slow", "-crf", str(sr_vhs.CRF),
                            "-maxrate", sr_vhs.MAXRATE, "-bufsize", sr_vhs.BUFSIZE,
                            "-pix_fmt", "yuv420p", "-c:a", "copy", "-movflags", "+faststart", dst],
                           stdin=subprocess.PIPE)
    size, n = W * H * 3, 0
    while True:
        raw = dec.stdout.read(size)
        if len(raw) < size:
            break
        t = n / fps
        m = mix(t, clean_from, fade) if tape else 0.0
        if m > 0:
            f = np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(np.float32) / 255.0
            f = np.clip(tape(f, t), 0, 1) * m + f * (1 - m)
            raw = (np.clip(f, 0, 1) * 255).astype(np.uint8).tobytes()
        enc.stdin.write(raw)
        n += 1
        if n % 150 == 0:
            print(f"[vhs-look] {t:.1f}s / {length:.1f}s", flush=True)
    enc.stdin.close()
    if dec.wait() or enc.wait():
        sys.exit("[vhs-look] ffmpeg failed")
    print(f"[vhs-look] {dst} ({n} frames, strength {strength:g}, clean from {clean_from})")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("src")
    p.add_argument("dst")
    p.add_argument("--strength", type=float, default=DEFAULT_STRENGTH, help="0 off to 1 full (default 0.5)")
    p.add_argument("--clean-from", type=float, default=None,
                   help="seconds where the shirt comes back; the overlay is fully gone here")
    p.add_argument("--fade", type=float, default=DEFAULT_FADE, help="fade-out length before --clean-from")
    p.add_argument("--osd", default=DEFAULT_OSD, help='readout text over the opening, "" for none')
    p.add_argument("--osd-end", type=float, default=DEFAULT_OSD_END)
    p.add_argument("--duration", type=float, default=None, help="only process the first N seconds (tests)")
    a = p.parse_args()
    if not 0 <= a.strength <= 1:
        sys.exit("--strength must be between 0 and 1")
    apply(a.src, a.dst, a.strength, a.clean_from, a.fade, a.osd, a.osd_end, a.duration)


if __name__ == "__main__":
    main()
