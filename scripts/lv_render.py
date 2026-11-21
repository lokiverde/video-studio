"""Frame renderer for the listing video.

Why Pillow instead of ffmpeg zoompan: zoompan snaps the crop window to whole
pixels, which makes slow pushes on architecture (straight lines, door frames)
visibly stair-step. Image.transform(EXTENT) takes a float box, so the motion is
sub-pixel smooth. Frames are piped straight into one ffmpeg process, which also
muxes the music, so there are no intermediate clips and no xfade graph.

Landscape moves alternate push, drift right, pull, drift left at a gentle zoom.
Portrait moves pan horizontally across a full-height landscape photo, full bleed.
"""
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps

import lv_beats
import lv_cards

FPS = 30
LANDSCAPE_MOVES = ("push", "drift_r", "pull", "drift_l")
PORTRAIT_MOVES = ("pan_r", "pan_l")
MIN_PAN_SLACK = 120  # px of spare width below which a portrait pan becomes a push
Image.MAX_IMAGE_PIXELS = None


@dataclass(frozen=True)
class Prepared:
    image: Image.Image
    move: str
    focus: float


def load_photo(path: str) -> Image.Image:
    if path.lower().endswith((".heic", ".heif")):
        import pillow_heif
        pillow_heif.register_heif_opener()
    return ImageOps.exif_transpose(Image.open(path)).convert("RGB")


def prepare(photo: Image.Image, out_size, portrait: bool, index: int, zoom: float,
            focus: float | None = None, move: str | None = None) -> Prepared:
    """Scale the source once to the working size for this cut.
    Landscape: cover (W*zoom, H*zoom), cropped vertically at `focus`.
    Portrait: height exactly H*zoom_p so the pan runs across the full width."""
    w, h = out_size
    if portrait:
        scale = h / photo.height
        src = photo.resize((max(w, round(photo.width * scale)), h), Image.LANCZOS)
        slack = src.width - w
        chosen = move or (PORTRAIT_MOVES[index % 2] if slack >= MIN_PAN_SLACK else "push")
        if chosen == "push" and slack < MIN_PAN_SLACK:
            src = ImageOps.fit(photo, (round(w * zoom), round(h * zoom)), Image.LANCZOS,
                               centering=(0.5 if focus is None else focus, 0.5))
        return Prepared(src, chosen, 0.5 if focus is None else focus)
    target = (round(w * zoom), round(h * zoom))
    src = ImageOps.fit(photo, target, Image.LANCZOS, centering=(0.5, 0.5 if focus is None else focus))
    return Prepared(src, move or LANDSCAPE_MOVES[index % len(LANDSCAPE_MOVES)], 0.5)


def crop_box(move: str, p: float, src_size, out_size, zoom: float, travel: float,
             focus: float = 0.5) -> tuple[float, float, float, float]:
    """Float source rectangle for progress p (0 to 1) of a move."""
    sw, sh = src_size
    w, h = out_size
    p = min(1.0, max(0.0, p))
    if move in ("pan_r", "pan_l"):
        slack = sw * h / sh - w  # spare width at output scale
        scale = sh / h
        span = slack * travel
        center = min(max(focus * slack, span / 2), slack - span / 2)
        start = center - span / 2 if move == "pan_r" else center + span / 2
        x = start + (span * p if move == "pan_r" else -span * p)
        return (x * scale, 0.0, (x + w) * scale, float(sh))
    if move in ("push", "pull"):
        z = 1 + (zoom - 1) * (p if move == "push" else 1 - p)
        cw, ch = sw / z, sh / z
        return ((sw - cw) / 2, (sh - ch) / 2, (sw + cw) / 2, (sh + ch) / 2)
    # drift: window is exactly the output size (1:1, sharpest), sliding across the slack
    cw, ch = sw / zoom, sh / zoom
    x = (sw - cw) * (p if move == "drift_r" else 1 - p)
    y = (sh - ch) / 2
    return (x, y, x + cw, y + ch)


def render_still(prep: Prepared, p: float, out_size, zoom: float, travel: float) -> Image.Image:
    box = crop_box(prep.move, p, prep.image.size, out_size, zoom, travel, prep.focus)
    return prep.image.transform(out_size, Image.EXTENT, box, Image.BICUBIC).convert("RGBA")


def with_opacity(overlay: Image.Image, opacity: float) -> Image.Image:
    if opacity >= 0.999:
        return overlay
    faded = overlay.copy()
    faded.putalpha(overlay.getchannel("A").point(lambda v: round(v * opacity)))
    return faded


def envelope(t: float, start: float, end: float, fade: float = 0.35) -> float:
    if t < start or t > end:
        return 0.0
    return min(1.0, (t - start) / fade, (end - t) / fade)


class Cut:
    """One aspect ratio of one listing: photos, overlays, beat timeline."""

    def __init__(self, picks: list[dict], facts: dict, brand: dict, cut: str, bpm: float,
                 mls: bool = False):
        spec = brand["cuts"][cut]
        motion = brand["motion"]
        self.size = tuple(spec["size"])
        self.portrait = self.size[1] > self.size[0]
        self.zoom = motion["zoom"]
        self.travel = motion["pan_travel"]
        self.xf = motion["crossfade"]
        self.fade_in = motion["fade_in"]
        self.fade_out = motion["fade_out"]
        self.picks = picks
        overrides = {i: p["beats"] for i, p in enumerate(picks) if p.get("beats")}
        self.segments, self.card_seg = lv_beats.timeline(
            len(picks), bpm, spec["target_seconds"], spec["open_beats"], spec["card_seconds"], overrides)
        self.duration = self.card_seg.end
        self.open_overlay = lv_cards.open_overlay(facts, brand, self.size, branded=not mls)
        self.labels = [lv_cards.label_overlay(p.get("label", ""), p.get("callout", ""), brand, self.size)
                       for p in picks]
        self.card = (lv_cards.mls_card if mls else lv_cards.placard)(facts, brand, self.size)
        self._prepared: dict[int, Prepared] = {}

    def prepared(self, i: int) -> Prepared:
        if i not in self._prepared:
            pick = self.picks[i]
            self._prepared = {**self._prepared, i: prepare(
                load_photo(pick["path"]), self.size, self.portrait, i, self.zoom,
                pick.get("focus"), pick.get("move"))}
        return self._prepared[i]

    def photo_frame(self, i: int, t: float) -> Image.Image:
        seg = self.segments[i]
        lead = 0 if i == 0 else self.xf / 2
        p = (t - (seg.start - lead)) / (seg.dur + lead + self.xf / 2)
        frame = render_still(self.prepared(i), p, self.size, self.zoom, self.travel)
        if i == 0:
            frame.alpha_composite(with_opacity(self.open_overlay, envelope(t, 0.25, seg.end - 0.3, 0.45)))
        elif self.labels[i] is not None:
            show_end = min(seg.end - 0.25, seg.start + 3.2)
            frame.alpha_composite(with_opacity(self.labels[i], envelope(t, seg.start + 0.2, show_end)))
        return frame

    def frame_at(self, t: float) -> Image.Image:
        half = self.xf / 2
        if t >= self.card_seg.start + half:
            frame = self.card.copy()
        else:
            i = next((k for k, s in enumerate(self.segments) if t < s.end), len(self.segments) - 1)
            frame = self.photo_frame(i, t)
            nxt_start = self.segments[i].end
            if t > nxt_start - half:
                mix = (t - (nxt_start - half)) / self.xf
                other = self.photo_frame(i + 1, t) if i + 1 < len(self.segments) else self.card
                frame = Image.blend(frame, other.convert("RGBA"), min(1.0, mix))
            elif i > 0 and t < self.segments[i].start + half:
                mix = 0.5 + (t - self.segments[i].start) / self.xf
                frame = Image.blend(self.photo_frame(i - 1, t), frame, min(1.0, mix))
        level = min(1.0, t / self.fade_in if self.fade_in else 1.0,
                    (self.duration - t) / self.fade_out if self.fade_out else 1.0)
        rgb = frame.convert("RGB")
        return rgb if level >= 0.999 else Image.blend(Image.new("RGB", self.size), rgb, max(0.0, level))

    def preview_times(self) -> list[float]:
        """One representative moment per photo (overlay fully visible), then the card."""
        times = [min(s.start + 1.2, s.end - 0.4) if i else s.end * 0.6 for i, s in enumerate(self.segments)]
        return times + [self.card_seg.start + self.card_seg.dur / 2]


def encode(cut: Cut, out_path: Path, music: Path, offset: float, loudness: float) -> None:
    total = cut.duration
    fade_start = max(0.0, total - 2.5)
    audio = (f"[1:a]atrim=0:{total:.3f},asetpts=PTS-STARTPTS,"
             f"afade=t=out:st={fade_start:.3f}:d=2.5,loudnorm=I={loudness}:TP=-1.5:LRA=11[a]")
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{cut.size[0]}x{cut.size[1]}",
           "-r", str(FPS), "-i", "-",
           "-stream_loop", "-1", "-ss", f"{offset:.3f}", "-i", str(music),
           "-filter_complex", audio, "-map", "0:v", "-map", "[a]",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
           "-movflags", "+faststart", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-t", f"{total:.3f}", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    frames = round(total * FPS)
    try:
        for n in range(frames):
            proc.stdin.write(cut.frame_at(n / FPS).tobytes())
            if n % (FPS * 10) == 0:
                print(f"[lv] {out_path.name}: {n / FPS:.0f}s / {total:.0f}s", flush=True)
    finally:
        proc.stdin.close()
        code = proc.wait()
    if code != 0:
        raise RuntimeError(f"ffmpeg failed encoding {out_path.name} (exit {code})")
