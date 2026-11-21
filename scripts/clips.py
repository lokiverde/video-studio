"""Clip scenes: a finished video file as a scene's picture (realistic footage).

A scene may carry "clip" instead of an image_prompt, the way it may carry a "photo".
Nothing is generated for it. assemble plays the file through the same path as an
animated scene (assemble.video_clip), and gen_images puts its first frame on the
contact sheet. Spec: docs/briefs/2026-10-24-realistic-footage.md, section 5.4.
"""
import io
import json
import subprocess
from pathlib import Path
from typing import NamedTuple, Optional

import common
import photos


class ClipInfo(NamedTuple):
    width: int
    height: int
    seconds: float
    has_audio: bool


def quarter_turned(stream):
    """True when the file asks players to show it on its side (a phone held upright
    records 640x360 pixels plus a 90 degree rotation). ffmpeg applies that rotation
    when it decodes, so the clip plays at the swapped size."""
    turns = [d.get("rotation") for d in stream.get("side_data_list", [])]
    turns.append((stream.get("tags") or {}).get("rotate"))
    return any(t is not None and abs(int(float(t))) % 180 == 90 for t in turns)


def probe(path):
    """Picture size (as it plays, rotation applied), length, and whether it has sound."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,width,height:stream_side_data=rotation:"
                          "stream_tags=rotate:format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True)
    info = json.loads(out.stdout or "{}") if out.returncode == 0 else {}
    streams = info.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    if not video or not video.get("width") or not info.get("format", {}).get("duration"):
        common.die(f"clip {path} cannot be read as a video {out.stderr.strip()[:160]}".rstrip())
    width, height = int(video["width"]), int(video["height"])
    if quarter_turned(video):
        width, height = height, width
    return ClipInfo(width, height, float(info["format"]["duration"]),
                    any(s.get("codec_type") == "audio" for s in streams))


DUCK_VOLUME = 0.25   # a ducked clip plays at a quarter of its level; a theme's "clip_duck" wins


class ClipSound(NamedTuple):
    """How loud a clip's own sound plays: `level` for the scene's first `until` seconds
    (while the narration speaks), full level after; `level` throughout when until is None."""
    level: float
    until: Optional[float] = None


def keeps_sound(scene, info):
    """True when the clip plays its own sound as recorded: "keep" (the default) and a
    sound track to keep. Such a clip counts as speech, so the music bed stays under it."""
    return info.has_audio and scene.get("audio", "keep") == "keep"


def duck_level(theme):
    duck = theme.get("clip_duck", DUCK_VOLUME)
    if isinstance(duck, bool) or not isinstance(duck, (int, float)) or not 0 <= duck <= 1:
        common.die(f"theme 'clip_duck' must be a number from 0 to 1, got {duck!r}")
    return float(duck)


def clip_volume(scene, info, narration_s, theme):
    """How the clip's own sound plays (a ClipSound), or None for not at all. "keep" (the
    default) plays it as recorded, ducked while narration speaks so the words stay clear
    and back up once they end; "duck" always plays it low; "mute" drops it. The sound is
    never run through voice cleanup or the Tony voice preset: those belong to the cloned
    narration alone."""
    mode = scene.get("audio", "keep")
    if mode == "mute" or not info.has_audio:
        return None
    duck = duck_level(theme)
    if mode == "duck":
        return ClipSound(duck)
    if narration_s:
        print(f"[clips] scene {scene['id']}: clip sound ducked under the narration")
        return ClipSound(duck, narration_s)
    return ClipSound(1.0)


def anchor(scene, info, out_w, out_h):
    """Where the cover crop sits, 0 (top) to 1 (bottom): the scene's "focus", read the
    same way a photo block's is (auto keeps faces in a tall source)."""
    return photos.anchor_for(info, out_w, out_h, scene.get("focus", "auto"))


def still(scene, path, out_path, out_w, out_h):
    """The contact-sheet picture of a clip scene: its first frame (after any trim),
    cropped the way the cut will crop it, with a badge saying how long the clip runs.
    assemble never reads this file for a clip scene; it plays the clip itself."""
    from PIL import Image
    start, length = span(scene, probe(path).seconds)
    frame = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-i", str(path),
                            "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
                           capture_output=True, check=True).stdout
    image = Image.open(io.BytesIO(frame)).convert("RGB")
    picture = photos.cover_crop(image, out_w, out_h, scene.get("focus", "auto"))
    draw_badge(picture, f"CLIP {length:.1f}s")
    picture.save(out_path)
    print(f"[clips] {out_path.name}: first frame of {path.name}, {length:.1f}s")


def draw_badge(image, text, size=0.06):
    """A dark label in the top-left corner, sized off the frame (size is the text height
    as a share of the short side) so it reads on a sheet thumbnail of either cut."""
    import captions
    from PIL import ImageDraw
    short = min(image.size)
    font = captions.load_font(max(14, round(short * size)))
    margin, pad = round(short * size / 2), max(6, round(short * size / 2))
    draw = ImageDraw.Draw(image)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    draw.rounded_rectangle((margin, margin, margin + right - left + 2 * pad,
                            margin + bottom - top + 2 * pad), radius=pad, fill=(15, 15, 15))
    draw.text((margin + pad - left, margin + pad - top), text, font=font, fill="white")


CUT_NAMES = {(1920, 1080): "16:9", (1080, 1920): "9:16"}


def warn_aspect(scene, info, out_w, out_h):
    """A clip shaped unlike the cut gets cropped hard. Say so and recommend a native
    render; never generate one here (a second generation costs credits)."""
    if abs(info.width / info.height - out_w / out_h) <= 0.02 * out_w / out_h:
        return
    cut = CUT_NAMES.get((out_w, out_h), f"{out_w}x{out_h}")
    print(f"[clips] WARNING: scene {scene['id']}: the clip is {info.width}x{info.height}, so "
          f"the {cut} cut crops it; regenerate it at {cut} if that cut matters")


def resolve(job_dir, ref):
    """A clip reference is an absolute path or a path inside the job folder (ingested
    files land in rf/returns/)."""
    path = Path(ref).expanduser()
    if not path.is_absolute():
        path = Path(job_dir) / path
    if not path.is_file():
        common.die(f"clip not found: {ref} (looked in {job_dir})")
    return path


def span(scene, clip_dur):
    """(start, length) in seconds of the stretch of the clip the scene plays: all of it,
    or the scene's "trim" [start, end] cut to what the file actually holds."""
    start, end = scene.get("trim") or (0.0, clip_dur)
    if start >= clip_dur:
        common.die(f"scene {scene['id']}: trim starts at {start:g}s but the clip is only "
                   f"{clip_dur:.2f}s long")
    if end > clip_dur + 0.05:
        print(f"[clips] WARNING: scene {scene['id']}: trim ends at {end:g}s, past the end of "
              f"the {clip_dur:.2f}s clip; playing to the end of the clip")
    return float(start), min(float(end), clip_dur) - float(start)
