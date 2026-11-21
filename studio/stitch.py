#!/usr/bin/env python3
"""stitch.py - assemble OpenArt clips into a finished video.

Master canvas is 9:16 vertical (1080x1920). Every clip is scaled-to-cover +
center-cropped to that canvas, then concatenated. Optional narration + music are
mixed on top. With --crop 16:9 a second 1920x1080 file is emitted (the vertical
master centered over a blurred cover background, so nothing is clipped).

Production lessons applied:
  - scale-to-cover + center-crop (never stretch faces from a wrong aspect ratio)
  - stretch, never freeze: if narration overruns the video, slow the video to match
  - duck music under narration
  - check STREAM durations, not the container

Usage:
  python stitch.py shot1.mp4 shot2.mp4 shot3.mp4 \
      --audio narration.mp3 [--music bed.mp3] [--out final.mp4] [--crop 16:9]
"""
import argparse
import json
import subprocess
import sys

W, H = 1080, 1920  # 9:16 master


def run(cmd):
    subprocess.run(cmd, check=True)


def probe_dur(path, stream="v:0"):
    """Duration of a specific stream (not the container)."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", stream,
         "-show_entries", "stream=duration", "-of", "json", path],
        capture_output=True, text=True,
    )
    try:
        d = json.loads(out.stdout)["streams"][0].get("duration")
        if d:
            return float(d)
    except (KeyError, IndexError, ValueError):
        pass
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True,
    )
    return float(json.loads(out.stdout)["format"]["duration"])


def concat(clips, out):
    """Scale-to-cover + center-crop each clip to 1080x1920, then concat (no audio)."""
    n = len(clips)
    inputs = []
    for c in clips:
        inputs += ["-i", c]
    filters = [
        f"[{i}:v]scale={W}:{H}:force_original_aspect_ratio=increase,"
        f"crop={W}:{H},setsar=1,fps=30[v{i}]"
        for i in range(n)
    ]
    concat_in = "".join(f"[v{i}]" for i in range(n))
    filters.append(f"{concat_in}concat=n={n}:v=1:a=0[outv]")
    run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters),
         "-map", "[outv]", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", out])


def add_audio(video, out, narration, music=None):
    """Mix narration (+ optional ducked music). Stretch video if narration overruns."""
    dur_v = probe_dur(video, "v:0")
    dur_a = probe_dur(narration, "a:0")
    inputs = ["-i", video, "-i", narration]
    fc = []

    # Stretch, never freeze.
    if dur_a > dur_v + 0.15:
        ratio = dur_a / dur_v
        fc.append(f"[0:v]setpts={ratio:.4f}*PTS[vout]")
        vmap = "[vout]"
    else:
        vmap = "0:v"

    if music:
        inputs += ["-i", music]
        fc.append("[2:a]volume=0.22[bg]")  # duck music under narration
        fc.append("[1:a][bg]amix=inputs=2:duration=first:dropout_transition=2,dynaudnorm[aout]")
        amap = "[aout]"
    else:
        amap = "1:a"

    cmd = ["ffmpeg", "-y", *inputs]
    if fc:
        cmd += ["-filter_complex", ";".join(fc)]
    cmd += ["-map", vmap, "-map", amap,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
            "-shortest", out]
    run(cmd)


def to_wide(src, out):
    """9:16 master -> 16:9 (1920x1080), vertical centered over a blurred cover bg.

    Note: this reframes rather than crops, so nothing is clipped. Text cards stay
    fully visible. The sharp layer sits centered; the wide gutters are a blur of
    the same frame (standard vertical-in-wide look for cross-posting).
    """
    fc = (
        "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
        "crop=1920:1080,boxblur=20:2[bg];"
        "[0:v]scale=-2:1080[fg];"
        "[bg][fg]overlay=(W-w)/2:0,setsar=1[outv]"
    )
    run(["ffmpeg", "-y", "-i", src, "-filter_complex", fc,
         "-map", "[outv]", "-map", "0:a?",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "copy", out])


def main():
    p = argparse.ArgumentParser(description="Stitch OpenArt clips into a finished video.")
    p.add_argument("clips", nargs="+", help="clip files in order")
    p.add_argument("--audio", help="narration audio (mp3/wav)")
    p.add_argument("--music", help="background music bed (ducked under narration)")
    p.add_argument("--out", default="final.mp4", help="output file (9:16 master)")
    p.add_argument("--crop", choices=["16:9"], help="also emit a 16:9 reframe")
    args = p.parse_args()

    silent = "._concat.mp4"
    concat(args.clips, silent)

    if args.audio:
        add_audio(silent, args.out, args.audio, args.music)
    else:
        concat(args.clips, args.out)  # no audio path: just the master

    print(f"wrote {args.out}")

    if args.crop == "16:9":
        wide = args.out.rsplit(".", 1)[0] + "_16x9.mp4"
        to_wide(args.out, wide)
        print(f"wrote {wide}")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg failed: {e}", file=sys.stderr)
        sys.exit(1)
