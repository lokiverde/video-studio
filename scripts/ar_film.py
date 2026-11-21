"""Archive reel: picture. Grade, print-damage, intertitles, logo, product cutouts, per-shot
clips, the contact sheet, and the silent master. Everything that makes new material look
like it was on the same 1924 reel as the archive footage."""
import io
import random
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import ar_lib
import common
import platform_util

ARCHIVE = common.ROOT / "archive"
W, H, FPS = 1080, 1920, 30
PAD = 32  # extra pixels for the gate weave to move inside
BLACKLETTER = str(ARCHIVE / "fonts" / "UnifrakturMaguntia-Book.ttf")
SANS, SANS_BOLD = platform_util.pick_font_face(
    ("/System/Library/Fonts/HelveticaNeue.ttc", 1), (platform_util.WIN_FONTS / "arialbd.ttf", 0),
    fallback=(platform_util.BUNDLED_FONTS / "DejaVuSans-Bold.ttf", 0))
CREAM = (236, 226, 204)

SEPIA = "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131"
FLICKER = "eq=eval=frame:contrast=1.3:gamma=0.92:brightness='-0.03+0.03*sin(n*2.7)*sin(n*1.3)'"
WEAVE = f"crop={W}:{H}:x='16+5*sin(n*1.7)*sin(n*0.31)':y='16+5*sin(n*2.3)*sin(n*0.53)'"
GRADE = f"format=gray,format=rgb24,{SEPIA},{FLICKER},vignette=angle=0.95,noise=alls=18:allf=t,fps=18,fps={FPS}"
# Daylight Nibelungen shots: the measured tones every generated clip is matched to.
TONE_REFS = ["kriemhild_horde_charge.mp4", "kriemhild_ladders.mp4",
             "kriemhild_fortress_horde.mp4", "kriemhild_climb_wall.mp4"]
GEN_RES = (360, 640)  # generated detail must never out-resolve the ~405x720 archive crop


def run(cmd):
    result = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if result.returncode != 0:
        common.die(f"command failed: {' '.join(map(str, cmd[:6]))}...\n{result.stderr[-1500:]}")
    return result


def font(path, size, index=0):
    return ImageFont.truetype(path, size, index=index)


def centered(draw, y, text, fnt, fill):
    box = draw.textbbox((0, 0), text, font=fnt)
    draw.text(((W - (box[2] - box[0])) // 2 - box[0], y), text, font=fnt, fill=fill)


# ---------- layers ----------

def text_layer(lines, top, gap=24, size=64):
    """White sans caps with a soft shadow (end card). Transparent 1080x1920."""
    img, shadow = Image.new("RGBA", (W, H)), Image.new("RGBA", (W, H))
    d, ds = ImageDraw.Draw(img), ImageDraw.Draw(shadow)
    fnt = font(SANS, size, SANS_BOLD)
    for k, line in enumerate(lines):
        centered(ds, top + k * (size + gap), line, fnt, (0, 0, 0, 230))
        centered(d, top + k * (size + gap), line, fnt, (255, 255, 255, 255))
    return Image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(10)), img)


def intertitle(text, path):
    img = Image.new("RGB", (W, H), (12, 10, 9))
    d = ImageDraw.Draw(img)
    for inset, width in ((70, 5), (92, 2)):
        d.rectangle([inset, inset + 260, W - inset, H - inset - 260], outline=CREAM, width=width)
    lines = text.split("\n")
    size = 170  # shrink until the longest line clears the inner border with a margin
    while max(font(BLACKLETTER, size).getlength(line) for line in lines) > W * 0.72:
        size -= 6
    for k, line in enumerate(lines):
        centered(d, H // 2 - len(lines) * size * 0.65 + k * size * 1.3, line, font(BLACKLETTER, size), CREAM)
    img.save(path)
    return path


def key_white(img, thresh=40):
    """Alpha mask: white paper connected to the corners -> transparent, everything else kept."""
    probe = img.convert("RGB").copy()
    for corner in ((0, 0), (img.width - 1, 0), (0, img.height - 1), (img.width - 1, img.height - 1)):
        ImageDraw.floodfill(probe, corner, (255, 0, 255), thresh=thresh)
    arr = np.asarray(probe)
    keyed = (arr[..., 0] == 255) & (arr[..., 1] == 0) & (arr[..., 2] == 255)
    return Image.fromarray(np.where(keyed, 0, 255).astype(np.uint8))


def tee_frame(src, path, width=0.86, y=0.44, dim=0.55):
    """Product on white -> cutout on a full frame, with a black dim layer behind it."""
    tee = Image.open(src).convert("RGBA")
    mask = key_white(tee).filter(ImageFilter.GaussianBlur(1.2))
    tee.putalpha(mask)
    tee = tee.crop(mask.getbbox())
    tw = int(W * width)
    tee = tee.resize((tw, int(tee.height * tw / tee.width)), Image.LANCZOS)
    frame = Image.new("RGBA", (W, H), (0, 0, 0, int(255 * dim)))
    frame.alpha_composite(tee, ((W - tw) // 2, int(H * y - tee.height / 2)))
    frame.save(path)
    return path


def film_logo(src, path, width=0.82, outline=True, ink="light"):
    """Brand logo as a title printed on the film: paper keyed out, red ink -> light (or dark: the
    orthochromatic stock of the 1920s rendered red as near-black). outline=False drops the black
    outline so only the red ink prints. Overlaid BEFORE the grade, so it takes the same sepia,
    flicker, weave and grain."""
    logo = Image.open(src).convert("RGB")
    red = logo.getchannel("R")
    light = red.point(lambda v: int(v * 0.9)) if ink == "light" else red.point(lambda v: 28)
    mask = key_white(logo, 60)
    if not outline:  # keep only the red ink
        mask = Image.fromarray(np.where(np.asarray(red) > 120, np.asarray(mask), 0).astype(np.uint8))
    out = Image.merge("RGBA", (light, light, light, mask.filter(ImageFilter.GaussianBlur(1)))).crop(mask.getbbox())
    tw = int((W + PAD) * width)
    out.resize((tw, int(out.height * tw / out.width)), Image.LANCZOS).filter(ImageFilter.GaussianBlur(0.8)).save(path)
    return path


# ---------- film match ----------

def luma_samples(path, fps=4):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"fps={fps},scale=320:-2,format=gray",
                          "-f", "rawvideo", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8)


def match_lut(src, out):
    """1D .cube that gives a generated clip the archive's measured tones."""
    target = np.concatenate([luma_samples(ARCHIVE / "clips" / r) for r in TONE_REFS])
    Path(out).write_text(ar_lib.cube_1d(ar_lib.match_mapping(luma_samples(src), target)))
    return out


def film_damage(path, seconds=3.0, fps=18, seed=7):
    """Neutral 128 plate with dust, hairs and drifting vertical scratches (overlay blend)."""
    if Path(path).exists():
        return path
    rnd, scratches = random.Random(seed), []
    proc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray", "-s", f"{W}x{H}",
                             "-r", str(fps), "-i", "-", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p",
                             str(path)], stdin=subprocess.PIPE)
    for _ in range(int(seconds * fps)):
        img = Image.new("L", (W, H), 128)
        d = ImageDraw.Draw(img)
        for _ in range(rnd.randint(25, 70)):
            x, y, r = rnd.randrange(W), rnd.randrange(H), rnd.choice((1, 1, 2, 2, 3, 5))
            d.ellipse([x, y, x + r * rnd.uniform(0.6, 1.8), y + r], fill=rnd.choice((20, 40, 60, 215)))
        if rnd.random() < 0.15:
            x, y = rnd.randrange(W), rnd.randrange(H)
            d.line([(x + rnd.randint(-60, 60) * k, y + rnd.randint(-40, 40) * k) for k in range(5)], fill=35, width=2)
        if rnd.random() < 0.25 or not scratches:
            scratches.append([rnd.randrange(W), rnd.randint(6, 30), rnd.choice((190, 230, 60))])
        for s in scratches:
            s[0] += rnd.randint(-3, 3)
            s[1] -= 1
            d.line([(s[0], 0), (s[0] + rnd.randint(-4, 4), H)], fill=s[2], width=rnd.choice((1, 2, 2, 3)))
        scratches = [s for s in scratches if s[1] > 0][-3:]
        proc.stdin.write(img.filter(ImageFilter.GaussianBlur(0.8)).tobytes())
    proc.stdin.close()
    proc.wait()
    return path


# ---------- shots ----------

def cover(focus, zoom=1.0):
    sw, sh = int((W + PAD) * zoom), int((H + PAD) * zoom)
    return (f"scale={sw}:{sh}:force_original_aspect_ratio=increase,"
            f"crop={W + PAD}:{H + PAD}:x='(iw-{W + PAD})*{focus}':y='(ih-{H + PAD})/2'")


def shot_source(jdir, shot):
    if shot.get("dir") == "public" or shot["kind"] in ("clip", "still"):
        return jdir / "public" / shot["src"]
    return ARCHIVE / "clips" / shot["src"]


def shot_input(jdir, i, shot):
    """ffmpeg inputs and the filter chain (from [0:v]) for one shot, before damage and tee."""
    kind, dur, focus = shot["kind"], shot["dur"], shot.get("focus", 0.5)
    work = jdir / "work"
    if kind == "card":
        png = intertitle(shot["text"], work / f"card_{i:02d}.png")
        return ["-loop", "1", "-framerate", FPS, "-t", dur, "-i", png], f"scale={W + PAD}:{H + PAD},{WEAVE},{GRADE}"
    if kind == "still":
        frames = int(dur * FPS)
        vf = (f"scale=1240:-2,zoompan=z='1+{shot.get('push', 0.08)}*on/{frames}':x='(iw-iw/zoom)*{focus}':"
              f"y='(ih-ih/zoom)/2':d=1:s={W + PAD}x{H + PAD}:fps={FPS},gblur=sigma=1.3,{WEAVE},{GRADE}")
        return ["-loop", "1", "-framerate", FPS, "-t", dur, "-i", shot_source(jdir, shot)], vf
    src = shot_source(jdir, shot)
    inputs = ["-ss", shot.get("in", 0.2), "-t", dur, "-i", src]
    if kind == "clip":  # generated motion: archive tones, archive resolution, coarse grain, 16 fps
        lut = match_lut(src, work / f"lut_{shot['id']}.cube")
        gw, gh = GEN_RES
        vf = (f"format=rgb24,lut1d=file='{lut}',scale={gw}:{gh}:force_original_aspect_ratio=increase:flags=area,"
              f"fps=16,noise=alls=26:allf=t,gblur=sigma=0.7,{cover(focus)},{WEAVE},{GRADE},gblur=sigma=1.1")
        return inputs, vf
    if "logo" in shot:  # printed on the film before the grade
        lg = shot["logo"]
        png = film_logo(jdir / "product" / lg["src"], work / "logo_film.png", lg.get("width", 0.82),
                        lg.get("outline", True), lg.get("ink", "light"))
        inputs += ["-loop", "1", "-framerate", FPS, "-t", dur, "-i", png]
        return inputs, (f"{cover(focus, shot.get('zoom', 1.0))}[pre];[1:v]format=rgba[lg];"
                        f"[pre][lg]overlay=x=(W-w)/2:y=H*{lg.get('y', 0.27)}-h/2,{WEAVE},{GRADE}")
    return inputs, f"{cover(focus, shot.get('zoom', 1.0))},{WEAVE},{GRADE}"


def render_shot(jdir, i, shot):
    out = jdir / "work" / "shots" / f"{i:02d}_{shot['id']}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    dur = shot["dur"]
    inputs, vf = shot_input(jdir, i, shot)
    n = inputs.count("-i")
    damage = film_damage(ARCHIVE / "film_damage.mp4")
    opacity = shot.get("damage", ar_lib.DAMAGE_OPACITY[shot["kind"]])
    inputs += ["-stream_loop", "-1", "-ss", f"{(i * 0.37) % 2.5:.2f}", "-i", damage]
    graph = (f"[0:v]{vf},trim=duration={dur},format=gbrp[g];[{n}:v]fps={FPS},format=gbrp[d];"
             f"[g][d]blend=all_mode=overlay:all_opacity={opacity}:shortest=1[base]")
    if "tee" in shot:
        t = shot["tee"]
        png = tee_frame(jdir / "product" / t["src"], jdir / "work" / f"tee_{i:02d}.png",
                        t.get("width", 0.86), t.get("y", 0.44), t.get("dim", 0.55))
        inputs += ["-loop", "1", "-framerate", FPS, "-t", dur, "-i", png]
        graph += (f";[{n + 1}:v]format=rgba,fade=in:st={t.get('at', 0)}:d={t.get('fade', 0.08)}:alpha=1[tee];"
                  f"[base][tee]overlay=0:0,format=yuv420p[v]")
    else:
        graph += ";[base]format=yuv420p[v]"
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[v]", "-t", dur,
         "-r", FPS, "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-an", out])
    return out


def render_shots(jdir, job):
    rows, total = ar_lib.timeline(job)
    for i, shot, start in rows:
        render_shot(jdir, i, shot)
        print(f"[ar] {start:6.2f}s  {shot['dur']:.2f}s  {shot['id']}")
    return total


# ---------- end card, sheet, silent master ----------

def end_png(jdir, job):
    path = jdir / "work" / "endcard.png"
    text_layer(job["end"]["lines"], job["end"].get("top", 820)).save(path)
    return path


def frame_at(clip, t):
    png = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t}", "-i", str(clip), "-frames:v", "1",
                          "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True).stdout
    return Image.open(io.BytesIO(png)).convert("RGBA")


def contact_sheet(jdir, job):
    """One frame per shot with the end card applied and the platform UI zones outlined."""
    rows, total = ar_lib.timeline(job)
    end_from, end_img = total - job["end"]["seconds"], Image.open(end_png(jdir, job))
    label = font(SANS, 40, SANS_BOLD)
    tiles = []
    for i, shot, start in rows:
        mid = shot["dur"] - 0.1 if "tee" in shot else min(shot["dur"] - 0.05, shot["dur"] * 0.6)
        img = frame_at(jdir / "work" / "shots" / f"{i:02d}_{shot['id']}.mp4", mid)
        if start + mid >= end_from:
            img.alpha_composite(end_img)
        d = ImageDraw.Draw(img)
        d.rectangle([0, int(H * ar_lib.SAFE_BOTTOM), W, H], outline=(0, 255, 255), width=6)
        d.rectangle([int(W * 0.86), int(H * 0.40), W, int(H * ar_lib.SAFE_BOTTOM)], outline=(0, 255, 255), width=6)
        d.rectangle([0, 0, W, 70], fill=(0, 0, 0))
        d.text((16, 12), f"{start + mid:5.2f}s  {shot['id']}", font=label, fill=(255, 220, 0))
        tiles.append(img.convert("RGB").resize((360, 640), Image.LANCZOS))
    cols = 6
    sheet = Image.new("RGB", (cols * 364, -(-len(tiles) // cols) * 644), "white")
    for k, tile in enumerate(tiles):
        sheet.paste(tile, ((k % cols) * 364, (k // cols) * 644))
    path = jdir / "work" / "contact_sheet.jpg"
    sheet.save(path, quality=88)
    return path


def silent_master(jdir, job):
    """Concatenate the shots, lay the end card on, cap the bitrate (grain inflates it)."""
    rows, total = ar_lib.timeline(job)
    work, out = jdir / "work", jdir / "out"
    out.mkdir(exist_ok=True)
    listing = work / "concat.txt"
    listing.write_text("".join(f"file '{work / 'shots' / f'{i:02d}_{s['id']}.mp4'}'\n" for i, s, _ in rows))
    end_from = total - job["end"]["seconds"]
    master = out / "master_silent.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing,
         "-loop", "1", "-t", total, "-i", end_png(jdir, job),
         "-filter_complex", f"[1:v]format=rgba,fade=in:st={end_from}:d=0.2:alpha=1[e];"
                            f"[0:v][e]overlay=0:0:enable='gte(t,{end_from})',format=yuv420p[v]",
         "-map", "[v]", "-t", total, "-r", FPS, "-c:v", "libx264", "-crf", "19", "-preset", "slow",
         "-maxrate", "16M", "-bufsize", "32M", "-movflags", "+faststart", master])
    return master
