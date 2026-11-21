"""Tribute Reel: Tony's own event footage + Tony's voice-over cut into a solemn 9:16 short.

Built from the surf-reel engine, but narrated and quiet: straight cuts, 6-frame dissolves
between beats, slow push-ins, white captions with a soft shadow, every face blurred.

  tribute_reel.py vo <job>        voice-over lines (job.json "lines") via Tim tony-clone
  tribute_reel.py plan <job>      print the timeline the VO lengths produce
  tribute_reel.py blur <job>      run the face pass on every cut (cached) + faces QA sheet
  tribute_reel.py sheet <job>     preview contact sheet: one graded frame per cut, with captions
  tribute_reel.py render <job>    out/final_9x16.mp4 + final_9x16_clean.mp4 + voiceover.srt
  tribute_reel.py upload <job>    BunnyCDN

The edit lives in jobs/<job>/job.json (beats -> cuts + captions). Recipe:
skills/tribute-reel/SKILL.md. Reference job: 20261008-tribute.
"""
import argparse
import json
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

import common
import platform_util
import tribute_blur

W, H, FPS = tribute_blur.W, tribute_blur.H, tribute_blur.FPS
FONT = platform_util.heavy_font("/System/Library/Fonts/Supplemental/Arial Black.ttf")
RAW_MIN = 8.0
BLACK = "black"          # a cut with "clip": "black" is a plain black frame
GRADE = "eq=saturation=0.84:contrast=1.03,colorbalance=rh=0.035:gh=0.01:bh=-0.03"


def run(cmd):
    subprocess.run(cmd, check=True)


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "csv=p=0", str(path)], capture_output=True, text=True, check=True)
    return float(out.stdout.strip())


def load_job(job_id):
    jdir = common.job_dir(job_id)
    path = jdir / "job.json"
    if not path.exists():
        common.die(f"job {job_id} has no job.json")
    return jdir, json.loads(path.read_text())


def vo_file(jdir, n):
    path = jdir / "work" / "vo" / f"line{n}.wav"
    return path if path.exists() else None


# ---------- timeline ----------

def timeline(jdir, job):
    """Absolute times for beats, cuts, captions and VO lines. The VO length sets each beat.
    The title card opens the video, or closes it when job "title_at" is "end"."""
    t = 0.0 if title_at_end(job) else job.get("title_dur", 2.0)
    beats = []
    for beat in job["beats"]:
        vo = vo_file(jdir, beat["line"]) if beat.get("line") else None
        vo_len = duration(vo) if vo else beat.get("vo_guess", 6.0)
        lead, tail = beat.get("lead", 0.3), beat.get("tail", 0.4)
        length = max(beat.get("min_dur", 0), lead + vo_len + tail)
        fixed = sum(c["dur"] for c in beat["cuts"] if not c.get("fill"))
        fills = [c for c in beat["cuts"] if c.get("fill")]
        if fixed > length - 0.8 * len(fills):
            common.die(f"beat line {beat.get('line')}: fixed cuts {fixed:.1f}s exceed beat {length:.1f}s")
        cuts, ct = [], t
        for c in beat["cuts"]:
            dur = (length - fixed) / len(fills) if c.get("fill") else c["dur"]
            cuts.append({**c, "dur": round(dur, 3), "start": round(ct, 3)})
            ct += dur
        caps = [{**cap, "t0": t + cap.get("at", 0.0),
                 "t1": t + (cap["to"] if cap.get("to") is not None else length)}
                for cap in beat.get("captions", [])]
        beats.append({**beat, "start": round(t, 3), "dur": round(length, 3), "cuts": cuts,
                      "caps": caps, "vo": vo, "vo_at": t + lead, "vo_len": vo_len})
        t += length
    if title_at_end(job):
        t += job.get("title_dur", 2.0)
    return beats, round(t, 3)


def title_at_end(job):
    return job.get("title_at", "start") == "end"


def title_start(job, total):
    return total - job.get("title_dur", 2.0) if title_at_end(job) else 0.0


def cmd_plan(args):
    jdir, job = load_job(args.job)
    beats, total = timeline(jdir, job)
    for b in beats:
        flag = "" if b["vo"] else " (VO missing, guessed)"
        print(f"beat line {b.get('line')}: {b['start']:.2f}-{b['start'] + b['dur']:.2f}s  "
              f"VO {b['vo_len']:.2f}s{flag}")
        for c in b["cuts"]:
            print(f"   {c['start']:6.2f}s  {c['dur']:.2f}s  {c['clip']} @{c['a']}s x{c.get('speed', 1.0)}")
    ts = title_start(job, total)
    print(f"title card {ts:.2f}-{ts + job.get('title_dur', 2.0):.2f}s")
    print(f"total {total:.2f}s (cap {job.get('max_len', 45)}s)")
    if total > job.get("max_len", 45) + 0.05:
        print("WARNING: over the length cap; trim leads/tails or tighten the VO tempo")


# ---------- voice-over ----------

def voice_chain(job):
    """Extra treatment on top of the saved voice preset (tts.TONY_VOICE is already applied by
    tts.narrate). Off by default: vo_pitch < 1 drops the pitch further, vo_eq adds the EQ again."""
    pitch = job.get("vo_pitch", 1.0)
    chain = ["aresample=48000"]
    if pitch != 1.0:
        chain += [f"asetrate={int(48000 * pitch)}", "aresample=48000", f"atempo={1 / pitch:.4f}"]
    if job.get("vo_eq", False):
        chain += ["highpass=f=70", "equalizer=f=120:t=o:w=1:g=3", "equalizer=f=320:t=o:w=1:g=-2.5",
                  "equalizer=f=3500:t=o:w=1.2:g=2.5", "deesser=i=0.4",
                  "acompressor=threshold=-20dB:ratio=3:attack=8:release=120:makeup=2"]
    return chain


def shape_vo(job, raw, out):
    """Cap the clone's long pauses at vo_pause seconds, apply vo_tempo (pitch kept), then the
    voice chain."""
    pause, tempo = job.get("vo_pause", 0.35), job.get("vo_tempo", 1.0)
    af = [f"silenceremove=stop_periods=-1:stop_duration={pause}:stop_threshold=-40dB:"
          f"stop_silence={pause}"] + voice_chain(job)
    if tempo != 1.0:
        af.append(f"atempo={tempo}")
    run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", ",".join(af), "-ar", "48000", str(out)])


def cmd_vo(args):
    import tts
    jdir, job = load_job(args.job)
    cfg = common.load_config()
    out_dir = jdir / "work" / "vo"
    out_dir.mkdir(parents=True, exist_ok=True)
    for n, text in enumerate(job["lines"], 1):
        if args.only and n not in args.only:
            continue
        raw = out_dir / f"line{n}_raw.wav"
        if args.reshape and raw.exists():
            pass                                   # keep the take, only re-shape it
        else:
            audio, ext, used = tts.narrate(cfg, text, job.get("voice", "tony"), "tim")
            raw.write_bytes(audio)
        shape_vo(job, raw, out_dir / f"line{n}.wav")
        print(f"[vo] line {n}: {duration(raw):.2f}s raw, {duration(out_dir / f'line{n}.wav'):.2f}s shaped")


# ---------- captions and cards ----------

def text_png(lines, path, size, y_frac, fg="white", shadow=True, bg=None):
    img = Image.new("RGBA", (W, H), bg or (0, 0, 0, 0))
    probe = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, size)
    while max(probe.textlength(s, font=font) for s in lines) > W * 0.8:   # clear of right-edge buttons
        size -= 4
        font = ImageFont.truetype(FONT, size)
    gap = int(size * 1.25)
    y0 = int(H * y_frac - gap * len(lines) / 2)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    for i, s in enumerate(lines):
        x = (W - probe.textlength(s, font=font)) / 2
        draw.text((x, y0 + i * gap), s, font=font, fill=fg)
    if shadow:
        alpha = layer.split()[3]
        shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        shade.putalpha(alpha.point(lambda v: int(v * 0.75)))
        shade = shade.filter(ImageFilter.GaussianBlur(size * 0.12))
        img.alpha_composite(shade, (3, 5))
    img.alpha_composite(layer)
    img.save(path)


def caption_pngs(jdir, job, beats):
    cap_dir = jdir / "work" / "captions"
    cap_dir.mkdir(parents=True, exist_ok=True)
    pngs = []
    for b in beats:
        for k, cap in enumerate(b["caps"]):
            path = cap_dir / f"cap_{b['start']:06.2f}_{k}.png"
            text_png(cap["lines"], path, cap.get("size", 76), cap.get("y", job.get("caption_y", 0.40)))
            pngs.append((path, cap))
    title = cap_dir / "title.png"
    text_png([job.get("title", "RLTW")], title, job.get("title_size", 300), 0.45,
             fg=job.get("title_fg", "black"), shadow=False, bg=job.get("title_bg", "white"))
    return title, pngs


# ---------- render ----------

def cut_span(beat, cut, dissolve, last_in_beat):
    return cut["dur"] + (dissolve if last_in_beat else 0) + 0.1


def blurred(jdir, job, beat, cut, dissolve, last):
    """The face-blurred clip for a cut. Every cut renders at least RAW_MIN seconds of source,
    so VO timing changes reuse the cached face pass instead of re-detecting."""
    src = jdir / job["clips"][cut["clip"]]
    need = cut_span(beat, cut, dissolve, last)
    have = (duration(src) - cut["a"]) / cut.get("speed", 1.0)
    if have < need - 0.1:
        common.die(f"cut {cut['clip']} @{cut['a']}s needs {need:.2f}s but the source has {have:.2f}s")
    span = round(min(have - 0.05, max(math.ceil(need + 0.5), RAW_MIN)), 2)
    return tribute_blur.prep_cut(jdir, src, cut, span)


def cut_filter(idx, cut, dur):
    push = cut.get("push", 0.04)
    return (f"[{idx}:v]trim=0:{dur:.3f},setpts=PTS-STARTPTS,{GRADE},"
            f"scale=w='trunc({W}*(1+{push}*t/{dur:.3f})/2)*2':h=-2:eval=frame,"
            f"crop={W}:{H},setsar=1,fps={FPS},settb=1/{FPS},format=yuv420p")


def video_graph(jdir, job, beats, total, title, caps, clean):
    d = job.get("dissolve", 0.2)
    inputs = ["-loop", "1", "-t", f"{job.get('title_dur', 2.0) + d}", "-i", str(title)]
    parts = [f"[0:v]format=yuv420p,fps={FPS},settb=1/{FPS},setsar=1[seg0]"]
    end = title_at_end(job)
    n = 1
    for bi, b in enumerate(beats):
        labels = []
        for ci, c in enumerate(b["cuts"]):
            last = ci == len(b["cuts"]) - 1
            dur = c["dur"] + (d if last and (bi < len(beats) - 1 or end) else 0)
            if c["clip"] == BLACK:              # story told over black: text and VO only
                inputs += ["-f", "lavfi", "-t", f"{dur + 0.1:.3f}", "-i", f"color=c=black:s={W}x{H}:r={FPS}"]
                parts.append(f"[{n}:v]trim=0:{dur:.3f},setpts=PTS-STARTPTS,fps={FPS},settb=1/{FPS},setsar=1,format=yuv420p[c{n}]")
            else:
                inputs += ["-i", str(blurred(jdir, job, b, c, d, last))]
                parts.append(cut_filter(n, c, dur) + f"[c{n}]")
            labels.append(f"[c{n}]")
            n += 1
        parts.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0,settb=1/{FPS}[seg{bi + 1}]")
    order = [(f"[seg{bi + 1}]", b["start"]) for bi, b in enumerate(beats)]
    order = order + [("[seg0]", title_start(job, total))] if end else [("[seg0]", 0.0)] + order
    acc = order[0][0]
    for k, (label, start) in enumerate(order[1:]):
        parts.append(f"{acc}{label}xfade=transition=fade:duration={d}:offset={start - d:.3f},settb=1/{FPS}[x{k}]")
        acc = f"[x{k}]"
    if not clean:
        for path, cap in caps:
            fade = cap.get("fade", 0.35)
            fade_in = cap.get("fade_in", fade)    # 0 = on screen from its first frame (hooks)
            span = cap["t1"] - cap["t0"]
            inputs += ["-loop", "1", "-t", f"{span:.3f}", "-i", str(path)]
            fin = f"fade=t=in:st=0:d={fade_in}:alpha=1," if fade_in > 0 else ""
            parts.append(f"[{n}:v]format=rgba,{fin}"
                         f"fade=t=out:st={span - fade:.3f}:d={fade}:alpha=1,"
                         f"setpts=PTS+{cap['t0']:.3f}/TB[cap{n}]")
            parts.append(f"{acc}[cap{n}]overlay=0:0:eof_action=pass[o{n}]")
            acc = f"[o{n}]"
            n += 1
    fade = job.get("end_fade", 1.2)
    parts.append(f"{acc}trim=0:{total:.3f},fade=t=out:st={total - fade:.3f}:d={fade}[vout]")
    return inputs, parts, n


def music_volume(job, beats):
    """Volume curve: each beat sets a music level in dB, reached with a linear ramp from the
    previous level; null is a hard stop (e.g. under the casualty line)."""
    ramp = job.get("music_ramp", 1.0)
    keys, prev = [], 0.0
    for b in beats:
        db = b.get("music_db")
        level = 0.0 if db is None else 10 ** (db / 20)
        keys.append((b["start"], prev if db is not None else 0.0, level))
        prev = level
    expr = "0"
    for t, frm, to in keys:                # later keys wrap earlier ones, so they win
        seg = f"({frm:.4f}+({to - frm:.4f})*min(1,(t-{t:.3f})/{ramp}))"
        expr = f"if(gte(t,{t:.3f}),{seg},{expr})"
    return expr


def audio_graph(jdir, job, beats, total, first_input):
    inputs, parts, labels, n = [], [], [], first_input
    for b in beats:
        if b["vo"]:
            ms = int(b["vo_at"] * 1000)
            inputs += ["-i", str(b["vo"])]
            parts.append(f"[{n}:a]aresample=48000,volume={job.get('vo_db', 0)}dB,adelay={ms}:all=1[a{n}]")
            labels.append(f"[a{n}]")
            n += 1
        for c in b["cuts"]:
            if c.get("audio_db") is None or c.get("speed", 1.0) != 1.0:
                continue
            src = jdir / job["clips"][c["clip"]]
            inputs += ["-ss", str(c["a"]), "-t", f"{c['dur']:.3f}", "-i", str(src)]
            ms = int(c["start"] * 1000)
            parts.append(f"[{n}:a]aresample=48000,volume={c['audio_db']}dB,"
                         f"afade=t=in:d=0.15,afade=t=out:st={c['dur'] - 0.25:.3f}:d=0.25,adelay={ms}:all=1[a{n}]")
            labels.append(f"[a{n}]")
            n += 1
    ta = job.get("title_audio")
    if ta:
        src = jdir / job["clips"][ta["clip"]]
        inputs += ["-ss", str(ta["a"]), "-t", str(job.get("title_dur", 2.0) + 0.3), "-i", str(src)]
        ms = int(title_start(job, total) * 1000)
        parts.append(f"[{n}:a]aresample=48000,volume={ta['db']}dB,afade=t=in:d=0.4,"
                     f"afade=t=out:st=1.8:d=0.5,adelay={ms}:all=1[a{n}]")
        labels.append(f"[a{n}]")
        n += 1
    m = job["music"]
    inputs += ["-ss", str(m.get("offset", 0)), "-i", str(jdir / m["file"])]
    lp = m.get("lowpass")
    muffle = f"lowpass=f={lp}," if lp else ""
    parts.append(f"[{n}:a]aresample=48000,{muffle}volume='{music_volume(job, beats)}':eval=frame[a{n}]")
    labels.append(f"[a{n}]")
    parts.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:duration=longest,"
                 f"atrim=0:{total:.3f},afade=t=out:st={total - 1.0:.3f}:d=1.0,"
                 f"loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    return inputs, parts


def write_srt(jdir, job, beats):
    def ts(t):
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    rows, k = [], 1
    for b in beats:
        if not b.get("line"):
            continue
        words = job["lines"][b["line"] - 1].split()
        chunks = [words[i:i + 8] for i in range(0, len(words), 8)]
        t = b["vo_at"]
        for ch in chunks:
            span = b["vo_len"] * len(ch) / len(words)
            rows.append(f"{k}\n{ts(t)} --> {ts(t + span)}\n{' '.join(ch)}\n")
            t += span
            k += 1
    path = jdir / "out" / "voiceover.srt"
    path.write_text("\n".join(rows))
    return path


def render(jdir, job, clean):
    beats, total = timeline(jdir, job)
    title, caps = caption_pngs(jdir, job, beats)
    vin, vparts, n = video_graph(jdir, job, beats, total, title, caps, clean)
    ain, aparts = audio_graph(jdir, job, beats, total, n)
    out = jdir / "out" / ("final_9x16_clean.mp4" if clean else "final_9x16.mp4")
    out.parent.mkdir(exist_ok=True)
    graph = ";".join(vparts + aparts)
    (jdir / "work" / f"graph{'_clean' if clean else ''}.txt").write_text(graph)
    run(["ffmpeg", "-v", "error", "-y", *vin, *ain, "-filter_complex", graph, "-map", "[vout]",
         "-map", "[aout]", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-profile:v", "high",
         "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
         "-movflags", "+faststart", str(out)])
    print(f"[render] {out} ({duration(out):.2f}s)")
    return out


def cmd_render(args):
    jdir, job = load_job(args.job)
    render(jdir, job, clean=False)
    render(jdir, job, clean=True)
    beats, _ = timeline(jdir, job)
    print(f"[render] {write_srt(jdir, job, beats)}")


def cmd_blur(args):
    jdir, job = load_job(args.job)
    beats, _ = timeline(jdir, job)
    d = job.get("dissolve", 0.2)
    from concurrent.futures import ThreadPoolExecutor
    todo = [(b, c, ci == len(b["cuts"]) - 1) for b in beats for ci, c in enumerate(b["cuts"])
            if c["clip"] != BLACK]
    with ThreadPoolExecutor(args.jobs) as pool:   # the detector is single-threaded
        clips = list(pool.map(lambda x: blurred(jdir, job, x[0], x[1], d, x[2]), todo))
    faces_sheet(jdir, [(c, clip) for (_, c, _), clip in zip(todo, clips)])


def faces_sheet(jdir, rows):
    """8 frames per cut, evenly spaced, so a missed face anywhere in a cut is visible."""
    tiles = []
    for c, clip in rows:
        length = duration(clip)
        frames = []
        for k in range(8):
            t = length * (k + 0.5) / 8
            raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", str(clip),
                                  "-frames:v", "1", "-vf", "scale=270:480", "-f", "image2pipe",
                                  "-vcodec", "png", "-"], capture_output=True, check=True).stdout
            frames.append(Image.open(__import__("io").BytesIO(raw)).convert("RGB"))
        row = Image.new("RGB", (270 * 8, 480 + 40), "black")
        for k, f in enumerate(frames):
            row.paste(f, (k * 270, 40))
        ImageDraw.Draw(row).text((10, 8), f"{c['clip']} @{c['a']}s  ({c['start']:.1f}s in video)",
                                 fill="white", font=ImageFont.truetype(FONT, 22))
        tiles.append(row)
    sheet = Image.new("RGB", (270 * 8, len(tiles) * 520), "black")
    for i, r in enumerate(tiles):
        sheet.paste(r, (0, i * 520))
    path = jdir / "work" / "faces_qa.jpg"
    sheet.save(path, quality=85)
    print(f"[blur] faces QA sheet: {path}")


def cmd_sheet(args):
    jdir, job = load_job(args.job)
    beats, total = timeline(jdir, job)
    title, caps = caption_pngs(jdir, job, beats)
    d = job.get("dissolve", 0.2)
    card = (Image.open(title).convert("RGB"), f"{title_start(job, total):.1f}s  title card")
    tiles = [] if title_at_end(job) else [card]
    for b in beats:
        for ci, c in enumerate(b["cuts"]):
            mid = c["dur"] / 2
            if c["clip"] == BLACK:
                frame = Image.new("RGBA", (W, H), "black")
            else:
                clip = blurred(jdir, job, b, c, d, ci == len(b["cuts"]) - 1)
                raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{mid:.3f}", "-i", str(clip),
                                      "-frames:v", "1", "-vf", GRADE, "-f", "image2pipe", "-vcodec", "png", "-"],
                                     capture_output=True, check=True).stdout
                frame = Image.open(__import__("io").BytesIO(raw)).convert("RGBA")
            t = c["start"] + mid
            for path, cap in caps:
                if cap["t0"] <= t <= cap["t1"]:
                    frame.alpha_composite(Image.open(path))
            tiles.append((frame.convert("RGB"), f"{c['start']:.1f}s  line {b.get('line')}  {c['clip']}"))
    if title_at_end(job):
        tiles.append(card)
    tw, th, cols = 270, 480, 6
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (tw * cols, (th + 36) * rows), "black")
    font = ImageFont.truetype(FONT, 18)
    for i, (img, label) in enumerate(tiles):
        x, y = (i % cols) * tw, (i // cols) * (th + 36)
        sheet.paste(img.resize((tw, th)), (x, y + 36))
        ImageDraw.Draw(sheet).text((x + 6, y + 8), label, fill="white", font=font)
    path = jdir / "work" / "contact_sheet_9x16.jpg"
    sheet.save(path, quality=88)
    print(f"[sheet] {path}  (total {total:.2f}s)")


def cmd_upload(args):
    import upload
    cfg = common.load_config()
    out = common.job_dir(args.job) / "out"
    for name in ("final_9x16.mp4", "final_9x16_clean.mp4", "voiceover.srt", "posts.md"):
        if (out / name).exists():
            print(upload.put_file(cfg, out / name, f"faceless/{args.job}/{name}"))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name, fn in (("vo", cmd_vo), ("plan", cmd_plan), ("blur", cmd_blur), ("sheet", cmd_sheet),
                     ("render", cmd_render), ("upload", cmd_upload)):
        s = sub.add_parser(name)
        s.add_argument("job")
        if name == "vo":
            s.add_argument("--only", nargs="+", type=int, help="regenerate just these line numbers")
            s.add_argument("--reshape", action="store_true", help="keep the takes, redo pause cap + tempo")
        if name == "blur":
            s.add_argument("--jobs", type=int, default=4)
        s.set_defaults(fn=fn)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
