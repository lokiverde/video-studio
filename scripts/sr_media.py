"""Storyboard reel: everything that shells out or talks to a server. ffmpeg encode, the
music + sfx mix, clip prep, rembg cutouts (its own venv), plate stills on Tim (free), and
the 9:16 contact sheet."""
import json
import random
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import common
import vision
from sr_shots import FONTS, FPS, H, W

PLATE_W, PLATE_H = 1088, 1920   # FLUX wants multiples of 16; cover() crops to 1080


def probe_seconds(path):
    """A media file's duration, or None when it is not there."""
    path = Path(path)
    if not path.exists():
        return None
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return None


def encode(frames, dst, preset="slow", crf=17, maxrate=None):
    """Pipe uint8 RGB frames into an H.264 file. maxrate (rate, buffer) caps a grainy picture."""
    cap = ["-maxrate", maxrate[0], "-bufsize", maxrate[1]] if maxrate else []
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
           "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", preset, "-crf", str(crf), *cap,
           "-pix_fmt", "yuv420p", str(dst)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    try:
        for img in frames:
            proc.stdin.write(img.tobytes())
    finally:
        proc.stdin.close()
    if proc.wait():
        raise RuntimeError(f"ffmpeg picture encode failed: {dst}")


def mix_audio(music, music_gain, fade_out, cues, total, dst, mutes=(), with_music=True):
    """Music bed trimmed to the video and faded out with the card, plus the sfx hits.
    cues: [(path, seconds, gain dB)]. mutes: [(start, end)] where the bed cuts out hard
    (the sfx still play). A silent ad, so the music sits near full level. with_music=False
    keeps the bed as the timing base at zero volume: the sound effects alone."""
    ins = ["-i", str(music)]
    cuts = "".join(f",volume=0:enable='between(t,{a:.3f},{b:.3f})'" for a, b in mutes)
    level = f"{music_gain}dB" if with_music else "0"
    parts = [f"[0:a]volume={level},atrim=0:{total:.2f}{cuts},"
             f"afade=t=out:st={total - fade_out:.2f}:d={fade_out}[m]"]
    labels = ["[m]"]
    for k, (path, at, gain) in enumerate(cues):
        ins += ["-i", str(path)]
        ms = int(round(at * 1000))
        parts.append(f"[{k + 1}:a]volume={gain}dB,adelay={ms}|{ms}[s{k}]")
        labels.append(f"[s{k}]")
    parts.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=first:normalize=0,alimiter=limit=0.89[a]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", ";".join(parts),
                    "-map", "[a]", "-c:a", "aac", "-b:a", "192k", str(dst)], check=True)


def mux(silent, mix, final, total):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(mix),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k",
                    "-ar", "48000", "-t", f"{total:.2f}", "-movflags", "+faststart", str(final)], check=True)


def mux_section(silent, mix, out, t0, t1):
    """A preview section: its picture plus the same stretch of the full mix."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-ss", f"{t0}", "-t", f"{t1 - t0}",
                    "-i", str(mix), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                    "-shortest", str(out)], check=True)


def clip_filter(lens=False):
    """A clip fills the 9:16 frame. A scope clip is a 16:9 pan: a square from its middle
    fills the lens and the rest of the frame stays black."""
    fit = f"scale=-2:{W}:flags=lanczos,crop={W}:{W},pad={W}:{H}:0:(oh-ih)/2" if lens else f"scale={W}:{H}:flags=lanczos"
    return f"{fit},fps={FPS}"


def prep_clip(src, dst, lens=False):
    """Kling mp4 (24 fps, its own size, maybe audio) -> 30 fps, 1080x1920, silent."""
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-an", "-vf",
                    clip_filter(lens), "-c:v", "libx264",
                    "-crf", "12", "-pix_fmt", "yuv420p", str(dst)], check=True)


def rembg(pairs):
    """Cut out [(src, dst)] with rembg isnet (vision.rembg_cutouts: its own venv or this Python)."""
    vision.rembg_cutouts(pairs)


def tim_plate(prompt, out_dir, model="flux", seed=None):
    """One portrait plate still from FLUX on Tim (free). Returns its path."""
    cfg = common.load_config()
    seed = seed or random.randint(1, 2 ** 31)
    payload = {"prompt": prompt, "model": model, "width": PLATE_W, "height": PLATE_H, "seed": seed}
    if model == "flux-dev":
        payload["guidance"] = 3.5
    data = common.http_json(f"{cfg['TIM_MEDIA_URL'].rstrip('/')}/image", payload, timeout=900)
    out = Path(out_dir) / f"plate_{model}_{seed}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return out


def contact_sheet(stills, dst, cols=6):
    """[(PIL image, label, seconds)] -> one sheet of 270x480 thumbs. The pale strip across
    each thumb's bottom fifth is where Reels/TikTok put the caption and buttons."""
    tw, th, pad, lab = 270, 480, 14, 44
    rows = (len(stills) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (tw + pad) + pad, rows * (th + pad + lab) + pad), (24, 24, 24))
    d = ImageDraw.Draw(sheet)
    font = ImageFont.truetype(str(FONTS["body"]), 17)
    for i, (im, label, t) in enumerate(stills):
        x = pad + (i % cols) * (tw + pad)
        y = pad + (i // cols) * (th + pad + lab)
        sheet.paste(im.resize((tw, th), Image.LANCZOS), (x, y))
        ui = Image.new("RGBA", (tw, 96), (255, 255, 255, 38))
        sheet.paste(ui, (x, y + th - 96), ui)
        d.text((x, y + th + 6), f"{label}  ({t:.1f}s)", font=font, fill=(235, 235, 235))
    sheet.save(dst, quality=90)
    return dst


def _ruled(rgba, y0, s):
    """A cutout crop on magenta, scaled by s, with a ruler in SOURCE pixels every 50."""
    crop = Image.fromarray(rgba[y0:]).convert("RGBA")
    bg = Image.new("RGBA", crop.size, (255, 0, 255, 255))
    bg.alpha_composite(crop)
    img = bg.convert("RGB").resize((max(1, int(crop.width * s)), max(1, int(crop.height * s))))
    d = ImageDraw.Draw(img)
    h, w = rgba.shape[:2]
    for x in range(0, w, 50):
        d.line([(x * s, 0), (x * s, 6 if x % 100 else 14)], fill=(255, 255, 255))
        if x % 100 == 0:
            d.text((x * s + 2, 14), str(x), fill=(255, 255, 255))
    for y in range((y0 // 50 + 1) * 50, h, 50):
        d.line([(0, (y - y0) * s), (6 if y % 100 else 14, (y - y0) * s)], fill=(255, 255, 255))
        if y % 100 == 0:
            d.text((16, (y - y0) * s - 6), str(y), fill=(255, 255, 255))
    return img


def feet_sheet(checks, dst, width=560):
    """[(name, raw rgba, repaired rgba)] uint8 -> the bottom quarter of each cutout, rembg
    left and repaired right, with a ruler in source pixels for reading feet boxes."""
    rows = []
    for name, raw, fixed in checks:
        y0, s = int(raw.shape[0] * 0.75), width / raw.shape[1]
        rows.append((name, _ruled(raw, y0, s), _ruled(fixed, y0, s)))
    sheet = Image.new("RGB", (2 * width + 30, sum(r[1].height + 30 for r in rows) + 10), (30, 30, 30))
    d = ImageDraw.Draw(sheet)
    y = 10
    for name, before, after in rows:
        d.text((10, y), f"{name}: rembg (left) / repaired (right)", fill=(235, 235, 235))
        sheet.paste(before, (10, y + 20))
        sheet.paste(after, (20 + width, y + 20))
        y += before.height + 30
    sheet.save(dst, quality=90)
    return dst


def video_summary(path):
    """'1080x1920 30/1 28.608s, audio' for the render log."""
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                          "stream=codec_type,width,height,r_frame_rate:format=duration", "-of", "json",
                          str(path)], capture_output=True, text=True)
    info = json.loads(out.stdout or "{}")
    video = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
    return (f"{video.get('width')}x{video.get('height')} {video.get('r_frame_rate')} "
            f"{float(info.get('format', {}).get('duration', 0)):.3f}s, {'audio' if audio else 'NO AUDIO'}")
