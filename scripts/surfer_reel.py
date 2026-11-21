"""Shop Surfer Video: Tony's own phone/DJI footage cut into a beat-synced 9:16 shirt ad.

  surfer_reel.py new --clips A.mp4 [B.mp4 ...] [--product IMG] [--url PRODUCT_URL]
      job folder + 1-second footage sheets per clip + product facts from Shopify
  surfer_reel.py beats <music>         lead-in, drop, beat grid and final hit of a music bed
  surfer_reel.py check <job>           validate job.json against the beat grid
  surfer_reel.py sheet <job>           preview: graded frame per cut with its caption + end card
  surfer_reel.py render <job>          out/final_9x16.mp4 with music + final_9x16_nomusic.mp4 silent
                                       (--clean: no captions)
  surfer_reel.py upload <job>          BunnyCDN

The look lives in skills/surf-reel/style.json; the edit lives in jobs/<job>/job.json.
Recipe and rules: skills/surf-reel/SKILL.md. Reference job: 20260926-surf-beach.
"""
import argparse
import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import common
import platform_util

ROOT = common.ROOT
STYLE_FILE = ROOT / "skills" / "surf-reel" / "style.json"
MUSIC_DIR = ROOT / "assets" / "music"


def run(cmd):
    subprocess.run(cmd, check=True)


def load_style():
    """style.json, with its font swapped for a heavy face this machine has when the named file is missing."""
    style = json.loads(STYLE_FILE.read_text())
    if not Path(style["font"]).exists():
        style = {**style, "font": platform_util.heavy_font(style["font"])}
    return style


def load_job(job_id, variant=None):
    """job.json, or job.<variant>.json for an alternate cut (e.g. a pool-only paid version)."""
    jdir = common.job_dir(job_id)
    path = jdir / (f"job.{variant}.json" if variant else "job.json")
    if not path.exists():
        common.die(f"job {job_id} has no job.json")
    return jdir, json.loads(path.read_text())


def resolve(jdir, p):
    path = Path(p).expanduser()
    if path.is_absolute():
        return path
    for base in (jdir, MUSIC_DIR):
        if (base / p).exists():
            return base / p
    return jdir / p


def seconds(cut):
    return round((cut["b"] - cut["a"]) / cut.get("speed", 1.0), 3)


# ---------- new ----------

def product_facts(url):
    """Title, price, sizes and color count from the Shopify product JSON."""
    try:
        req = urllib.request.Request(url.split("?")[0].rstrip("/") + ".json",
                                     headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            p = json.load(resp)["product"]
    except Exception as exc:  # the card can still be written by hand
        print(f"[surfer] could not read product JSON ({exc}); fill the card by hand")
        return {}
    opts = {o["name"].lower(): o["values"] for o in p.get("options", [])}
    prices = sorted({float(v["price"]) for v in p["variants"]})
    sizes = opts.get("size", [])
    bits = [f"${prices[0]:g}"]
    if sizes:
        bits.append(f"{sizes[0]}-{sizes[-1]}")
    if len(opts.get("color", [])) > 1:
        bits.append(f"{len(opts['color'])} COLORS")
    return {"title": p["title"].upper(), "details": "  /  ".join(bits)}


def cmd_new(args):
    style = load_style()
    job_id = time.strftime("%Y%m%d-%H%M%S") + "-surf"
    jdir = common.JOBS_DIR / job_id
    (jdir / "work").mkdir(parents=True)
    (jdir / "assets").mkdir()
    clips = {}
    for n, clip in enumerate(args.clips):
        src = Path(clip).expanduser()
        if not src.exists():
            common.die(f"no such clip: {src}")
        name = chr(ord("a") + n)
        clips[name] = str(src)
        dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                    "-of", "csv=p=0", str(src)], capture_output=True, text=True).stdout)
        cols = 10
        run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-vf",
             f"fps=1,scale=144:-2,tile={cols}x{-(-int(dur) // cols) or 1}", "-frames:v", "1",
             str(jdir / "work" / f"footage_{name}.jpg")])
        print(f"[surfer] clip {name}: {src.name} {dur:.1f}s -> work/footage_{name}.jpg "
              f"(1 frame per second, left to right)")
    card = {"product": "", "title": "", "details": "", "url": style["card_url"],
            "seconds": style["card_seconds"], "final_hit": None}
    if args.product:
        dst = jdir / "assets" / ("product" + Path(args.product).suffix.lower())
        shutil.copy(Path(args.product).expanduser(), dst)
        card["product"] = f"assets/{dst.name}"
    if args.url:
        card.update(product_facts(args.url))
    job = {"title": card["title"] or "Shop Surfer Video", "product_url": args.url or "",
           "music": style["music"], "music_offset": None, "bpm": style["bpm"],
           "clips": clips, "card": card, "cuts": []}
    (jdir / "job.json").write_text(json.dumps(job, indent=2))
    print(f"[surfer] job {job_id}\n         {jdir / 'job.json'}\n"
          f"         next: beats, write cuts, check, sheet")


# ---------- beats ----------

def cmd_beats(args):
    import numpy as np
    style = load_style()
    path = resolve(Path("."), args.music)
    sr, hop = 11025, 256
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-ac", "1", "-ar", str(sr),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32)
    win = int(0.1 * sr)
    rms = np.array([np.sqrt(np.mean(x[i:i + win] ** 2)) for i in range(0, len(x) - win, win)])
    peak = rms.max()
    lead = next(i for i, v in enumerate(rms) if v > 0.02) * 0.1
    drop = next(i for i, v in enumerate(rms) if v > 0.6 * peak) * 0.1
    tail = max(i for i, v in enumerate(rms) if v > 0.6 * peak) * 0.1
    env = np.array([np.sqrt(np.mean(x[i * hop:(i + 1) * hop] ** 2)) for i in range(len(x) // hop)])
    onset = np.maximum(0, np.diff(env))
    fr = sr / hop
    near = lambda t, span: max(range(int((t - span) * fr), int((t + span) * fr)), key=lambda i: onset[i]) / fr
    drop = near(drop, 0.3)
    final_hit = near(tail, 0.3)
    beat = 60 / args.bpm
    offset = round(lead - 0.1, 2)
    print(f"file        {path.name}  ({len(x) / sr:.1f}s)")
    print(f"lead-in     music starts at {lead:.1f}s  -> music_offset {offset}")
    print(f"drop        track {drop:.2f}s  -> video {drop - offset:.2f}s (intro cuts must sum to this)")
    print(f"beat        {beat:.3f}s at {args.bpm} BPM (from the prompt; override with --bpm)")
    print(f"final hit   track {final_hit:.2f}s -> video {final_hit - offset:.2f}s")
    print(f"ring-out    until ~{tail + 1.2:.1f}s")
    print(f"            beats from drop to final hit: {(final_hit - drop) / beat:.1f}")
    del style


# ---------- check ----------

def timeline(job):
    beat = 60 / job["bpm"]
    intro = sum(seconds(c) for c in job["cuts"] if c.get("mode") == "intro")
    hits = [c for c in job["cuts"] if c.get("mode") != "intro"]
    return beat, intro, hits


def cmd_check(args):
    jdir, job = load_job(args.job, getattr(args, 'variant', None))
    problems = []
    if not job["cuts"]:
        problems.append("no cuts yet")
    if job.get("music_offset") is None:
        problems.append("music_offset not set (run beats)")
    for c in job["cuts"]:
        if c["clip"] not in job["clips"]:
            problems.append(f"cut uses unknown clip {c['clip']}")
    beat, intro, hits = timeline(job)
    for n, c in enumerate(hits):
        k = seconds(c) / beat
        if abs(k - round(k)) > 0.02:
            problems.append(f"hit cut {n + 1} ({c.get('cap') or 'no caption'}) is {seconds(c)}s = "
                            f"{k:.2f} beats, not a whole beat")
    card = job["card"]
    if not card.get("product") or not resolve(jdir, card["product"]).exists():
        problems.append("card.product image missing")
    if card.get("final_hit") is None:
        problems.append("card.final_hit not set")
    total = sum(seconds(c) for c in job["cuts"]) + card["seconds"]
    print(f"intro {intro:.2f}s  (drop lands here)  |  hit section {sum(seconds(c) for c in hits):.2f}s  "
          f"|  card {card['seconds']}s  |  total {total:.2f}s")
    print("\n".join(f"  PROBLEM: {p}" for p in problems) or "  ok")
    return not problems


# ---------- sheet + render ----------

def caption_png(style, text, path, full_frame):
    W, H = style["width"], style["height"]
    font_path = style["font"]
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    size = style["caption_size"]
    font = ImageFont.truetype(font_path, size)
    while probe.textlength(text.upper(), font=font) > W - 120:
        size -= 4
        font = ImageFont.truetype(font_path, size)
    tw = int(probe.textlength(text.upper(), font=font))
    pad = 24
    tight = Image.new("RGBA", (tw + 2 * pad, size + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(tight).text((pad, pad), text.upper(), font=font, fill="white",
                               stroke_width=style["caption_stroke"], stroke_fill="black")
    if not full_frame:
        tight.save(path)
        return
    frame = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    frame.alpha_composite(tight, ((W - tight.width) // 2, int(H * style["caption_y"] - tight.height / 2)))
    frame.save(path)


def end_card(style, jdir, card, path):
    W, H = style["width"], style["height"]
    out = Image.new("RGB", (W, H), (8, 8, 8))
    prod = Image.open(resolve(jdir, card["product"])).convert("RGB")
    bg = prod.resize((H, H)).filter(ImageFilter.GaussianBlur(40)).crop(((H - W) // 2, 0, (H - W) // 2 + W, H))
    out.paste(Image.blend(bg, Image.new("RGB", (W, H), (0, 0, 0)), 0.6))
    side = W - 80
    prod.thumbnail((side, side))
    top = 330
    out.paste(prod, ((W - prod.width) // 2, top))
    d = ImageDraw.Draw(out)
    big = ImageFont.truetype(style["font"], 124)
    mid = ImageFont.truetype(style["font"], 70)
    base = top + prod.height
    for text, font, y, fill in [(card["title"], big, 140, "white"),
                                (card["details"], mid, base + 50, "white"),
                                (card["url"], big, base + 170, tuple(style["accent"]))]:
        f = font
        while d.textlength(text, font=f) > W - 80:
            f = ImageFont.truetype(style["font"], f.size - 4)
        tw = d.textlength(text, font=f)
        d.text(((W - tw) / 2, y), text, font=f, fill=fill, stroke_width=6, stroke_fill="black")
    out.save(path)


IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".heic"}
SFX_DIR = ROOT / "assets" / "sfx"
GHOST = STYLE_FILE.parent / "ghost_skull.png"
FEATHER = STYLE_FILE.parent / "feather.png"
SIGIL = STYLE_FILE.parent / "sigil.png"


def clip_spec(job, name):
    """A clip is a path, or {"path", "crop": [x, y, w, h]} in source fractions. Images become held shots."""
    spec = job["clips"][name]
    spec = {"path": spec} if isinstance(spec, str) else dict(spec)
    spec["image"] = Path(spec["path"]).suffix.lower() in IMAGE_EXT
    return spec


def source_graph(style, job, cut, dur, first_input=0):
    """Inputs + filter graph from the source clip to a graded-ready [src] at 1.6x the output size.

    Handles stills (held and drifted), crops, and privacy masks (blur + wispy ghost skull
    over each masked region, in source fractions, for the whole cut).
    """
    fps, W, H = style["fps"], style["width"], style["height"]
    spec = clip_spec(job, cut["clip"])
    n = first_input
    if spec["image"]:
        inputs = ["-loop", "1", "-framerate", str(fps), "-t", f"{dur + 0.2:.3f}", "-i", spec["path"]]
        head = f"[{n}:v]format=rgb24,setpts=N/{fps}/TB"
    else:
        inputs = ["-i", spec["path"]]
        head = (f"[{n}:v]trim={cut['a']}:{cut['b']},setpts=(PTS-STARTPTS)/{cut.get('speed', 1.0)},"
                f"fps={fps},format=rgb24")
    n += 1
    parts, label = [], "s0"
    if spec.get("crop"):
        x, y, w, h = spec["crop"]
        head += f",crop=iw*{w}:ih*{h}:iw*{x}:ih*{y}"
    parts.append(f"{head}[{label}]")
    for k, (x, y, w, h) in enumerate(cut.get("masks", [])):
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{dur + 0.2:.3f}", "-i", str(GHOST),
                   "-loop", "1", "-framerate", str(fps), "-t", f"{dur + 0.2:.3f}", "-i", str(FEATHER)]
        a, b, blur, gk, nxt = f"ma{k}", f"mb{k}", f"bl{k}", f"gk{k}", f"s{k + 1}"
        parts += [
            f"[{label}]split[{a}][{b}]",
            f"[{b}]crop=iw*{w}:ih*{h}:iw*{x}:ih*{y},boxblur=22:5,format=rgba[{blur}raw]",
            # feathered oval edge so it reads as haze, not a censor box
            f"[{n + 1}:v]format=gray[{blur}f0]",
            f"[{blur}f0][{blur}raw]scale2ref[{blur}f][{blur}r]",
            f"[{blur}r][{blur}f]alphamerge[{blur}]",
            f"[{a}][{blur}]overlay=x=main_w*{x}:y=main_h*{y}[{a}o]",
            # wispy spirit: semi-transparent, softened, drifting slightly
            f"[{n}:v]format=rgba,colorchannelmixer=aa=0.62,gblur=sigma=1.5[{gk}raw]",
            f"[{gk}raw][{a}o]scale2ref=w=main_w*{w * 0.9}:h=ow*1.2[{gk}][{a}r]",
            f"[{a}r][{gk}]overlay=x='main_w*{x + w * 0.05}+3*sin(t*2.1)':"
            f"y='main_h*{y}+main_h*{h}*0.5-overlay_h*0.55+2*cos(t*1.7)':shortest=1[{nxt}]",
        ]
        label, n = nxt, n + 2
    big_w, big_h = round(W * 1.6), round(H * 1.6)
    parts.append(f"[{label}]scale={big_w}:{big_h}:force_original_aspect_ratio=increase,"
                 f"crop={big_w}:{big_h},setsar=1[src]")
    return inputs, ";".join(parts), n


def cmd_sheet(args):
    style = load_style()
    jdir, job = load_job(args.job, args.variant)
    W, H = style["width"], style["height"]
    work = jdir / "work"
    work.mkdir(exist_ok=True)
    tiles = []
    for i, cut in enumerate(job["cuts"]):
        frame = work / f"sheet_{i:02d}.jpg"
        grade = style["intro_grade"] if cut.get("mode") == "intro" else style["hit_grade"]
        dur = seconds(cut)
        inputs, graph, _ = source_graph(style, job, cut, dur)
        graph += f";[src]scale={W}:{H},{grade}[o]"
        run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[o]",
             "-ss", f"{dur / 2:.2f}", "-frames:v", "1", str(frame)])
        tile = Image.open(frame).convert("RGBA")
        if cut.get("cap"):
            caption_png(style, cut["cap"], work / f"capfull_{i:02d}.png", full_frame=True)
            tile.alpha_composite(Image.open(work / f"capfull_{i:02d}.png"))
        tiles.append(tile.convert("RGB"))
    end_card(style, jdir, job["card"], work / "end_card.png")
    tiles.append(Image.open(work / "end_card.png"))
    tw, th, cols = 270, 480, 7
    rows = -(-len(tiles) // cols)
    sheet = Image.new("RGB", (cols * tw, rows * (th + 40)), "black")
    d = ImageDraw.Draw(sheet)
    label = ImageFont.truetype(style["font"], 26)
    t = 0.0
    lengths = [seconds(c) for c in job["cuts"]] + [job["card"]["seconds"]]
    for n, (tile, length) in enumerate(zip(tiles, lengths)):
        x, y = (n % cols) * tw, (n // cols) * (th + 40)
        sheet.paste(tile.resize((tw, th)), (x, y + 40))
        d.text((x + 8, y + 6), f"{n + 1}  {t:.1f}s  ({length:.1f}s)", font=label, fill="white")
        t += length
    name = f"contact_sheet_9x16{'_' + args.variant if args.variant else ''}.jpg"
    sheet.save(work / name, quality=90)
    print(f"[surfer] sheet {work / name}  total {t:.1f}s")


def motion(style, beat, mode, dur, punch):
    """zoompan: intro drifts slowly; hit cuts punch in, shake, and pulse on every beat."""
    fps = style["fps"]
    W, H = style["width"], style["height"]
    t = f"(on/{fps})"
    if mode == "intro":
        z = f"1.04+0.07*{t}/{dur}"
        sx = sy = "0"
    else:
        decay = f"max(0,1-{t}/0.3)"
        z = f"1.06+{punch}*max(0,1-{t}/0.16)+{style['pulse']}*max(0,1-mod({t},{beat})/0.13)"
        sx = f"{style['shake_x']}*sin(on*2.9)*{decay}"
        sy = f"{style['shake_y']}*cos(on*3.7)*{decay}"
    return (f"zoompan=z='{z}':x='iw/2-iw/zoom/2+{sx}':y='ih/2-ih/zoom/2+{sy}'"
            f":d=1:s={W}x{H}:fps={fps}")


def overlay_sigil(inputs, graph, label, n, fps, dur, at=0.0):
    """Red triangle sigil flashes over the frame and burns out in 0.45s."""
    inputs += ["-loop", "1", "-framerate", str(fps), "-t", f"{dur:.3f}", "-i", str(SIGIL)]
    graph += (f";[{n}:v]format=rgba,fade=t=in:st={at}:d=0.04:alpha=1,"
              f"fade=t=out:st={at + 0.08}:d=0.45:alpha=1[sg]"
              f";[{label}][sg]overlay=x=(W-w)/2:y=(H-h)/2:shortest=1[sgo]")
    return inputs, graph, "sgo", n + 1


def render_cut(style, job, work, i, cut, next_flash, clean, tag):
    fps = style["fps"]
    beat = 60 / job["bpm"]
    dur = seconds(cut)
    hit = cut.get("mode") != "intro"
    inputs, graph, n = source_graph(style, job, cut, dur)
    chain = [motion(style, beat, cut.get("mode", "hit"), dur,
                    style["punch_flash"] if cut.get("flash") else style["punch"]),
             style["hit_grade"] if hit else style["intro_grade"]]
    if cut.get("flicker"):   # candlelight
        chain.append("eq=brightness='0.045*sin(t*19)*sin(t*6.1)+0.02*sin(t*41)':eval=frame")
    whip = f"avgblur=sizeX={style['whip_blur']}:sizeY=1"
    if hit:
        if not cut.get("flash"):
            chain.append(f"{whip}:enable='lt(t,0.07)'")
        if not next_flash:
            chain.append(f"{whip}:enable='gte(t,{dur - 0.07})'")
    if cut.get("flash"):
        chain.append("fade=t=in:st=0:d=0.18:color=white")
    if i == 0:
        chain.append("fade=t=in:st=0:d=0.4")
    chain.append(f"trim=duration={dur}")
    graph += f";[src]{','.join(chain)}[v]"
    label = "v"
    if cut.get("sigil") is not None and cut.get("sigil") is not False:
        at = 0.0 if cut["sigil"] is True else float(cut["sigil"])
        inputs, graph, label, n = overlay_sigil(inputs, graph, label, n, fps, dur, at)
    if cut.get("cap") and not clean:
        cap = work / f"cap_{i:02d}.png"
        caption_png(style, cut["cap"], cap, full_frame=False)
        inputs += ["-loop", "1", "-framerate", str(fps), "-t", str(dur), "-i", str(cap)]
        y = f"H*{style['caption_y']}-h/2"
        if hit:   # slam: starts 1.8x and snaps to size in 0.12s
            k = "(1+0.8*max(0,1-t/0.12))"
            graph += (f";[{n}:v]format=rgba,scale=w='iw*{k}':h='ih*{k}':eval=frame[c]"
                      f";[{label}][c]overlay=x='(W-w)/2':y='{y}':shortest=1[o]")
        else:     # intro: fade in
            graph += (f";[{n}:v]format=rgba,fade=t=in:st=0.1:d=0.35:alpha=1[c]"
                      f";[{label}][c]overlay=x='(W-w)/2':y='{y}':shortest=1[o]")
        label = "o"
    graph += f";[{label}]format=yuv420p[fin]"
    part = work / f"part_{i:02d}{tag}.mp4"
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[fin]", "-an",
         "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-t", str(dur), str(part)])
    return part


def render_card(style, job, work, tag):
    fps, W, H = style["fps"], style["width"], style["height"]
    beat = 60 / job["bpm"]
    card = job["card"]
    secs, hit_at = card["seconds"], card["final_hit"]
    t = f"(on/{fps})"
    z = (f"1.0+0.2*max(0,1-{t}/0.16)+0.02*max(0,1-mod({t},{beat})/0.13)"
         f"+0.08*max(0,1-abs({t}-{hit_at})/0.12)*gte({t},{hit_at})")
    inputs = ["-loop", "1", "-framerate", str(fps), "-t", str(secs), "-i", str(work / "end_card.png"),
              "-f", "lavfi", "-t", str(secs), "-i", f"color=white:s={W}x{H}:r={fps}"]
    graph = (f"[0:v]scale={W * 1.1:.0f}:{H * 1.1:.0f},zoompan=z='{z}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2'"
             f":d=1:s={W}x{H}:fps={fps},fade=t=in:st=0:d=0.18:color=white[b];"
             f"[1:v]format=rgba,colorchannelmixer=aa=0.85[f];"
             f"[b][f]overlay=enable='between(t,{hit_at},{hit_at + 0.1})',trim=duration={secs}[v]")
    label = "v"
    if card.get("sigil"):
        inputs, graph, label, _ = overlay_sigil(inputs, graph, label, 2, fps, secs, hit_at)
    graph += f";[{label}]format=yuv420p[o]"
    part = work / f"part_card{tag}.mp4"
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[o]",
         "-c:v", "libx264", "-crf", "18", str(part)])
    return part


def sound_events(job, jdir):
    """(start, input args, filter chain) for every source-audio and sfx event on the timeline."""
    events, t = [], 0.0
    for cut in job["cuts"]:
        spec = clip_spec(job, cut["clip"])
        if cut.get("audio") and not spec["image"]:
            speed = cut.get("speed", 1.0)
            # a skull pre-pass clip is video only: its frame-aligned original has the sound
            src = job.get("sources", {}).get(cut["clip"]) or spec["path"]
            src = src["path"] if isinstance(src, dict) else src
            events.append((t, ["-i", src],
                           f"atrim={cut['a']}:{cut['b']},asetpts=PTS-STARTPTS,atempo={speed},"
                           f"volume={cut['audio']},afade=t=out:st={seconds(cut) - 0.05}:d=0.05"))
        for sfx in ([cut["sfx"]] if isinstance(cut.get("sfx"), (str, dict)) else cut.get("sfx", [])):
            sfx = {"name": sfx} if isinstance(sfx, str) else sfx
            path = SFX_DIR / f"{sfx['name']}.mp3"
            events.append((t + sfx.get("at", 0.0), ["-i", str(path)], f"volume={sfx.get('volume', 0.8)}"))
        t += seconds(cut)
    return events


def cmd_render(args):
    if not cmd_check(args):
        common.die("[surfer] fix job.json first")
    style = load_style()
    jdir, job = load_job(args.job, args.variant)
    work, out = jdir / "work", jdir / "out"
    work.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)
    tag = out_tag(args)
    end_card(style, jdir, job["card"], work / "end_card.png")
    cuts = job["cuts"]
    parts = [render_cut(style, job, work, i, c,
                        cuts[i + 1].get("flash", False) if i + 1 < len(cuts) else True, args.clean, tag)
             for i, c in enumerate(cuts)]
    parts.append(render_card(style, job, work, tag))
    listing = work / f"concat{tag}.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in parts))
    total = sum(seconds(c) for c in cuts) + job["card"]["seconds"]
    # Every render ships twice: with the music bed, and with a silent track for a sound
    # added in the app at posting.
    for silent in (False, True):
        final = out / f"final_9x16{tag}{'_nomusic' if silent else ''}.mp4"
        mux_audio(job, jdir, listing, total, silent, final)
        # The grain makes the master ~240MB for 25s; TikTok mobile caps uploads at 287MB.
        social = final.with_name(f"{final.stem}_social.mp4")
        run(["ffmpeg", "-v", "error", "-y", "-i", str(final), "-c:v", "libx264", "-preset", "slow",
             "-crf", "20", "-maxrate", "16M", "-bufsize", "32M", "-pix_fmt", "yuv420p", "-c:a", "copy",
             "-movflags", "+faststart", str(social)])
        print(f"[surfer] render {final}  {total:.2f}s\n[surfer] social {social}")


def mux_audio(job, jdir, listing, total, silent, final):
    """Concat the rendered parts and lay the music bed (or silence) plus any clip audio and sfx."""
    fade = job.get("music_fade", 1.0)
    inputs = ["-f", "concat", "-safe", "0", "-i", str(listing)]
    if silent:
        inputs += ["-f", "lavfi", "-t", f"{total:.3f}", "-i", "anullsrc=r=48000:cl=stereo"]
        graph = [f"[1:a]atrim=0:{total}[m]"]
    else:
        inputs += ["-i", str(resolve(jdir, job["music"]))]
        graph = [f"[1:a]atrim=start={job['music_offset']},asetpts=PTS-STARTPTS,atrim=0:{total},"
                 f"volume={job.get('music_volume', 1.0)}[m]"]
    mix = ["[m]"]
    events = sound_events(job, jdir)
    for k, (start, ev_in, chain) in enumerate(events):
        inputs += ev_in
        ms = int(start * 1000)
        graph.append(f"[{k + 2}:a]{chain},adelay={ms}|{ms}[e{k}]")
        mix.append(f"[e{k}]")
    if silent and not events:
        graph.append("[m]anull[a]")
    else:
        # clip sound alone (gunshots) is all transients: a lower target keeps AAC from clipping
        target, ceiling = ("I=-16:TP=-2.5", 0.72) if silent else ("I=-14:TP=-1.5", 0.84)
        graph.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,alimiter=limit=0.9,"
                     f"afade=t=out:st={total - fade}:d={fade},loudnorm={target},"
                     f"alimiter=limit={ceiling}:level=false[a]")
    run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(graph),
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
         "-movflags", "+faststart", str(final)])


def out_tag(args):
    """Output name suffix: _<variant>, _clean (no captions). The silent cut adds _nomusic."""
    return (f"_{args.variant}" if args.variant else "") + ("_clean" if args.clean else "")


def cmd_stills(args):
    """Full-resolution JPG stills from a render, for carousel posts."""
    jdir, _ = load_job(args.job, args.variant)
    tag = out_tag(args)
    src = jdir / "out" / f"final_9x16{tag}.mp4"
    for k, t in enumerate(args.at, 1):
        dst = jdir / "out" / f"still_{k}{tag}.jpg"
        run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(src), "-frames:v", "1", "-q:v", "2", str(dst)])
        print(f"[surfer] still {dst}")


def cmd_upload(args):
    import upload
    cfg = common.load_config()
    out = common.job_dir(args.job) / "out"
    tag = out_tag(args)
    for name in (f"final_9x16{tag}_social.mp4", f"final_9x16{tag}_nomusic_social.mp4",
                 f"final_9x16{tag}.mp4", f"final_9x16{tag}_nomusic.mp4", "posts.md"):
        if (out / name).exists():
            print(upload.put_file(cfg, out / name, f"faceless/{args.job}/{name}"))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--clips", nargs="+", required=True)
    n.add_argument("--product")
    n.add_argument("--url")
    n.set_defaults(fn=cmd_new)
    b = sub.add_parser("beats")
    b.add_argument("music")
    b.add_argument("--bpm", type=float, default=load_style()["bpm"])
    b.set_defaults(fn=cmd_beats)
    for name, fn in (("check", cmd_check), ("sheet", cmd_sheet), ("render", cmd_render),
                     ("stills", cmd_stills), ("upload", cmd_upload)):
        s = sub.add_parser(name)
        s.add_argument("job")
        s.add_argument("--variant", help="use job.<variant>.json, output final_9x16_<variant>.mp4")
        s.add_argument("--clean", action="store_true", help="no captions, output *_clean.mp4")
        if name == "stills":
            s.add_argument("--at", nargs="+", type=float, required=True)
        s.set_defaults(fn=fn)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
