#!/usr/bin/env python3
"""Storyboard reel: a 9:16 YourShop shirt ad drawn from Tony's hand-drawn storyboard
and his renders. Logo, figure cutouts on a generated plate, a Kling start/end clip, a
glow that blows out to white, the design fading in on the blank tee, the product card.
Music + sfx, no narration. Recipe: ~/.claude/skills/storyboard-reel/SKILL.md.

  storyboard_reel.py new <product-url> <images-folder> [--word W] [--title T]
  storyboard_reel.py check <job>                    validate job.json, print the timeline
  storyboard_reel.py cutouts <job> [--force]        rembg the figure renders, then the feet repairs
  storyboard_reel.py plate <job> [--n 3] [--model flux] [--seed S]   plate candidates on Tim (free)
  storyboard_reel.py stills <job>                   key frames + work/contact_sheet_9x16.jpg (the gate)
  storyboard_reel.py approve <job>                  record Tony's go (only after he says so)
  storyboard_reel.py kling-frames <job>             start/end frames + prompt per clip shot
  storyboard_reel.py prep-clip <job> <kling.mp4> [--shot ID]
  storyboard_reel.py preview <job> [--from S] [--to S]   the clip stretch with sound
  storyboard_reel.py render <job> [--no-preview] [--clean] [--out PATH]   blocked until approved
  storyboard_reel.py kit <job> [--out-dir DIR]      rewrite out/post.txt + out/posts.md
  storyboard_reel.py upload <job>                   Bunny: finals, cover, post kit (new names on re-upload)
"""
import argparse
import json
import shutil
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

import approval
import common
import loudness
import sr_lib
import sr_matte
import sr_media
import sr_post
import sr_vhs
from sr_shots import FPS, Assets, frame_at, pose_stage

KIND = "storyboard-reel"
ROOT = common.ROOT
TEMPLATE = ROOT / "skills" / "storyboard-reel" / "job_template.json"
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}
KLING_COST = ("Kling 3.0 pro start+end frame on OpenArt: 105 credits at 3 s, 140 at 4 s (2026-10-17). "
              "Quote with openart_model_cost and get Tony's go before generating.")


@dataclass(frozen=True)
class Ctx:
    job_id: str
    jdir: Path
    job: dict
    resolve: Callable
    rows: list
    total: float

    def assets(self, vhs=True):
        """The shot assets, with the job's VHS pass unless vhs=False (a clean cut)."""
        tape = sr_vhs.make(sr_lib.vhs_config(self.job, self.rows)) if vhs else None
        return Assets(self.jdir, self.job, self.rows, self.resolve, tape)


def resolver(jdir):
    """job.json paths: absolute, else under the job folder, else under the pipeline root."""
    def resolve(p):
        path = Path(p).expanduser()
        if path.is_absolute():
            return path
        for base in (jdir, ROOT):
            if (base / p).exists():
                return base / p
        return jdir / p
    return resolve


def clip_len(resolve):
    return lambda shot: sr_media.probe_seconds(resolve(shot["clip"])) if shot.get("clip") else None


def load(job_id):
    jdir = common.job_dir(job_id)
    path = jdir / "job.json"
    if not path.exists():
        common.die(f"job {job_id} has no job.json (is it a storyboard-reel job?)")
    return jdir, json.loads(path.read_text())


def checked(job_id):
    jdir, job = load(job_id)
    resolve = resolver(jdir)
    problems = sr_lib.validate(job, clip_len(resolve), exists=lambda p: resolve(p).exists())
    if problems:
        common.die("[sr] job.json problems:\n  - " + "\n  - ".join(problems))
    rows, total = sr_lib.timeline(job, clip_len(resolve))
    return Ctx(job_id, jdir, job, resolve, rows, total)


# ---------- new ----------

def fetch_product(url):
    req = urllib.request.Request(url + ".json", headers={"User-Agent": common.USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def product_note(facts):
    return (f"Product: {facts['title'].title()} tee, {facts['price']}, {facts['sizes']}, "
            f"{facts['colors']} colors ({', '.join(facts['color_names'])}).")


def cmd_new(args):
    folder = Path(args.images).expanduser()
    images = sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXT) if folder.is_dir() else []
    if not images:
        common.die(f"no images in {folder}")
    url = args.url.split("?")[0].rstrip("/")
    data = fetch_product(url)
    facts = sr_lib.product_facts(data, url)
    title = args.title or f"Shop {facts['title'].title()}"
    job_id, jdir = common.new_job(word=args.word, title=args.title or facts["title"])
    for sub in ("src", "product", "work/cut", "work/bg", "work/kling", "work/stills"):
        (jdir / sub).mkdir(parents=True, exist_ok=True)
    for p in images:
        shutil.copy2(p, jdir / "src" / p.name)
    for k, img in enumerate(data["product"].get("images", []), 1):
        (jdir / "product" / f"shop_{k:02d}.jpg").write_bytes(common.http_get(img["src"]))
    (jdir / "product" / "product.json").write_text(json.dumps(data, indent=2))
    job = json.loads(TEMPLATE.read_text())
    names = [p.name for p in images]

    def pick(*words):
        return next((f"src/{n}" for n in names if any(w in n.lower() for w in words)), None)

    handle = url.rsplit("/", 1)[-1]
    shirt = f"assets/photos/yourshop/{handle}-tshirt.jpg"
    shots = {s["id"]: s for s in job["shots"]}
    shots["logo"]["src"] = pick("logo") or shots["logo"]["src"]
    shots["card"]["mockup"] = pick("mockup") or "product/shop_01.jpg"
    shots["shirt"]["src"] = shirt if (ROOT / shirt).exists() else "product/shop_01.jpg"
    job.update(title=title, product=facts, storyboard=[f"src/{n}" for n in names if "board" in n.lower()])
    job["post"]["notes"] = [product_note(facts)] + job["post"]["notes"]
    (jdir / "job.json").write_text(json.dumps(job, indent=2) + "\n")
    print(f"[sr] job {job_id}\n     {jdir / 'job.json'}\n     card: {facts['title']} / {sr_lib.details(facts)}")
    print(f"     src/: {', '.join(names)}\n     product/: {len(data['product'].get('images', []))} shop images")
    print("[sr] next: read the storyboard, set figures (renders in src/), the shot list and the plate prompt,\n"
          "     then: cutouts, plate, stills (the gate)")


# ---------- prep ----------

def cmd_check(args):
    ctx = checked(args.job)
    for shot, start, end in ctx.rows:
        note = " (clip not prepared, stand-in length)" if shot["kind"] == "clip" and not ctx.resolve(shot["clip"]).exists() else ""
        print(f"  {start:6.2f} - {end:6.2f}  {shot['id']:<10} {shot['kind']}{note}")
    print(f"[sr] ok: {len(ctx.rows)} shots, {ctx.total:.3f}s")


def cmd_cutouts(args):
    jdir, job = load(args.job)
    resolve = resolver(jdir)
    cut = jdir / "work" / "cut"
    cut.mkdir(parents=True, exist_ok=True)
    figures = job.get("figures") or {}
    todo = []
    for name, fig in figures.items():
        if not fig.get("src") or not resolve(fig["src"]).exists():
            common.die(f"figure `{name}`: set src to one of the renders in src/")
        raw = cut / f"{Path(fig['src']).stem}.png"
        if args.force or not raw.exists():
            todo.append((resolve(fig["src"]), raw))
    sr_media.rembg(todo)
    checks = []
    for name, fig in figures.items():
        stem = Path(fig["src"]).stem
        raw = np.asarray(Image.open(cut / f"{stem}.png").convert("RGBA"))
        if fig.get("feet"):
            src = np.asarray(Image.open(resolve(fig["src"])).convert("RGB"))
            fixed = sr_matte.repair_feet(src, raw, fig["feet"])
            Image.fromarray(fixed).save(cut / f"{stem}_fixed.png")
            checks.append((name, raw, fixed))
        else:
            checks.append((name, raw, raw))
    sheet = sr_media.feet_sheet(checks, cut / "feet_check.jpg")
    print(f"[sr] {len(todo)} new cutouts, {sum(1 for f in figures.values() if f.get('feet'))} feet repairs\n"
          f"[sr] look at {sheet}: rembg drops pale bone on a pale floor and keeps cast shadow. Fix with\n"
          f"     figures.<name>.feet {{add|drop|rebuild: [x0, y0, x1, y1]}} in source pixels, then rerun.")


def cmd_plate(args):
    jdir, job = load(args.job)
    prompt = (job.get("plate") or {}).get("prompt")
    if not prompt:
        common.die("set plate.prompt first")
    made = [sr_media.tim_plate(prompt, jdir / "work" / "bg", args.model, args.seed) for _ in range(args.n)]
    for path in made:
        print(f"[sr] {path}")
    every = sorted((jdir / "work" / "bg").glob("*.png"))
    sheet = sr_media.contact_sheet([(Image.open(p).convert("RGB"), p.stem, 0.0) for p in every],
                                   jdir / "work" / "bg" / "plates.jpg")
    print(f"[sr] {sheet}\n[sr] set plate.src in job.json to the one Tony picks (work/bg/<name>.png)")


def cmd_stills(args):
    """Key frames and the 9:16 contact sheet. Shown to Tony BEFORE any render."""
    ctx = checked(args.job)
    a = ctx.assets()
    sdir = ctx.jdir / "work" / "stills"
    sdir.mkdir(parents=True, exist_ok=True)
    stills = []
    for t, label in sr_lib.sheet_keys(ctx.rows):
        img = Image.fromarray(frame_at(a, t)[0])
        img.save(sdir / f"t{t:05.2f}.jpg", quality=92)
        stills.append((img, label, t))
    sheet = sr_media.contact_sheet(stills, ctx.jdir / "work" / "contact_sheet_9x16.jpg")
    common.set_state(args.job, status="sheet", sheet_fingerprint=approval.fingerprint(ctx.jdir, KIND))
    for shot, _, _ in ctx.rows:
        if shot["kind"] == "clip" and not ctx.resolve(shot["clip"]).exists():
            print(f"[sr] {shot['id']}: no Kling clip yet, the sheet shows a cross-dissolve stand-in")
    print(f"[sr] {sheet}\n[sr] show Tony the sheet and wait for his go, then: storyboard_reel.py approve {args.job}")


def cmd_approve(args):
    jdir = common.job_dir(args.job)
    current = approval.fingerprint(jdir, KIND)
    problem = approval.can_approve(common.get_state(args.job), current)
    if problem:
        common.die(f"[sr] cannot approve: {problem}")
    common.set_state(args.job, approved_fingerprint=current, approved_at=time.strftime("%Y-%m-%dT%H:%M:%S"))
    print(f"[sr] approved {args.job}. Any change to the picture (shots, figures, plate, cutouts, clips) voids it.")


def cmd_kling_frames(args):
    ctx = checked(args.job)
    a = ctx.assets()
    kdir = ctx.jdir / "work" / "kling"
    kdir.mkdir(parents=True, exist_ok=True)
    for shot, start, end in ctx.rows:
        if shot["kind"] != "clip":
            continue
        for end_name in ("start", "end"):
            if sr_lib.is_still_clip(shot) and not shot.get(end_name):
                continue                      # a camera clip runs from its start frame only
            img = (np.clip(kling_frame(a, shot, end_name), 0, 1) * 255).astype(np.uint8)
            path = kdir / f"{shot['id']}_{end_name}.jpg"
            Image.fromarray(img).save(path, quality=95)
            print(f"[sr] {path}")
        print(f"[sr] {shot['id']} prompt:\n     {shot['prompt']}\n[sr] {KLING_COST}\n"
              f"[sr] then: storyboard_reel.py prep-clip {args.job} <downloaded.mp4> --shot {shot['id']}")


def kling_frame(a, shot, end_name):
    """A clip's start or end frame: the full-frame still itself (cover-fitted to 9:16), or
    the figure posed on the plate at the shared scale and centre line."""
    if sr_lib.is_still_clip(shot):
        return a.still(shot[end_name])
    return pose_stage(a, a.figure(shot["from" if end_name == "start" else "to"], "pose"))[0]


def cmd_prep_clip(args):
    jdir, job = load(args.job)
    clips = [s for s in job["shots"] if s.get("kind") == "clip" and (not args.shot or s["id"] == args.shot)]
    if len(clips) != 1:
        common.die("name the clip shot with --shot" if clips else f"no clip shot {args.shot or ''}")
    dst = resolver(jdir)(clips[0]["clip"])
    sr_media.prep_clip(Path(args.src).expanduser(), dst, lens=clips[0].get("scope") is not None)
    print(f"[sr] {dst} ({sr_media.probe_seconds(dst):.3f}s). Its length sets the clip shot; the fill shot absorbs it.")


# ---------- render ----------

def has_music(ctx):
    music = (ctx.job.get("audio") or {}).get("music")
    return bool(music) and ctx.resolve(music).exists()


def nomusic_path(final):
    """The twin without the music bed, sound effects only (Tony, 2026-10-25)."""
    return final.with_name(f"{final.stem}_nomusic{final.suffix}")


def mix(ctx, dst, with_music=True):
    audio = ctx.job.get("audio") or {}
    if not has_music(ctx):
        common.die("audio.music: generate a bed (ElevenLabs generate_music, instrumental) and set it")
    cues = [(ctx.resolve(src), at, gain) for src, at, gain in sr_lib.sfx_cues(ctx.job, ctx.rows)]
    sr_media.mix_audio(ctx.resolve(audio["music"]), audio.get("music_gain", -2), audio.get("fade_out", 1.4),
                       cues, ctx.total, dst, sr_lib.music_mutes(ctx.job, ctx.rows), with_music)
    return dst


def cmd_preview(args):
    """A stretch of the cut with its sound, for judging the clip's motion at the gate."""
    ctx = checked(args.job)
    t0, t1 = sr_lib.preview_window(ctx.rows, ctx.total)
    t0, t1 = args.t0 if args.t0 is not None else t0, args.t1 if args.t1 is not None else t1
    a = ctx.assets()
    work = ctx.jdir / "work"
    silent, out = work / "preview_silent.mp4", work / "preview_clip.mp4"
    sr_media.encode((frame_at(a, i / FPS)[0] for i in range(int(t0 * FPS), int(t1 * FPS))), silent,
                    preset="fast", crf=19)
    if has_music(ctx):
        sr_media.mux_section(silent, mix(ctx, work / "preview_audio.m4a"), out, t0, t1)
    else:
        shutil.copy(silent, out)
        print("[sr] no music bed yet, the preview is silent")
    print(f"[sr] {out} ({t0:.1f} to {t1:.1f}s)")


def cmd_render(args):
    ctx = checked(args.job)
    reason = approval.gate(common.get_state(args.job), approval.fingerprint(ctx.jdir, KIND), args.no_preview)
    if reason:
        common.die(f"[sr] BLOCKED: {reason}.\n      sheet: {ctx.jdir / 'work' / 'contact_sheet_9x16.jpg'}\n"
                   f"      after Tony says go: storyboard_reel.py approve {args.job}   (his explicit waiver only: --no-preview)")
    out = ctx.jdir / "out"
    vhs_on = sr_post.vhs_strength(ctx.job) > 0 and not args.clean
    final = Path(args.out).expanduser() if args.out else out / (sr_post.VHS_VIDEO if vhs_on else sr_post.VIDEO)
    final.parent.mkdir(parents=True, exist_ok=True)
    scratch = final.parent if args.out else ctx.jdir / "work"     # side renders keep out of the job
    a = ctx.assets(vhs=vhs_on)
    n = sr_lib.frame_count(ctx.total, FPS)

    def frames():
        for i in range(n):
            if i % 90 == 0:
                print(f"[sr] frame {i}/{n}", flush=True)
            yield frame_at(a, i / FPS)[0]

    silent = scratch / f"{final.stem}.picture.mp4"
    if a.vhs:
        sr_media.encode(frames(), silent, crf=sr_vhs.CRF, maxrate=(sr_vhs.MAXRATE, sr_vhs.BUFSIZE))
    else:
        sr_media.encode(frames(), silent)
    sr_media.mux(silent, mix(ctx, scratch / f"{final.stem}.mix.m4a"), final, ctx.total)
    loudness.normalize(final)
    print(f"[sr] {final}: {sr_media.video_summary(final)}")
    twin = nomusic_path(final)
    sr_media.mux(silent, mix(ctx, scratch / f"{twin.stem}.mix.m4a", with_music=False), twin, ctx.total)
    loudness.normalize(twin)
    print(f"[sr] {twin}: {sr_media.video_summary(twin)} (sound effects, no music)")
    if not args.out and final.name == sr_post.main_video(ctx.job):   # the deliverable writes the kit
        t = sr_lib.cover_time(ctx.job, ctx.rows)
        Image.fromarray(frame_at(a, t)[0]).save(out / sr_post.COVER, quality=92)
        print(f"[sr] {out / sr_post.COVER} ({t:.1f}s)")
        write_kit(ctx.jdir, ctx.job)
        common.set_state(args.job, status="rendered")


def write_kit(jdir, job, out_dir=None):
    """out/post.txt and out/posts.md. The copy lives in job.json `post`."""
    out_dir = Path(out_dir) if out_dir else jdir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    clean = (jdir / "out" / sr_post.VIDEO).exists()
    (out_dir / "post.txt").write_text(sr_post.post_text(job))
    (out_dir / "posts.md").write_text(sr_post.posts_md(job, clean=clean))
    print(f"[sr] {out_dir / 'post.txt'}\n[sr] {out_dir / 'posts.md'}")
    for problem in sr_post.post_problems(job):
        print(f"[sr] post copy not ready: {problem}")


def cmd_kit(args):
    jdir, job = load(args.job)
    write_kit(jdir, job, args.out_dir)


def cmd_upload(args):
    """Final + post.txt to Bunny. A re-upload goes to a NEW name (_v2, _v3): the CDN keeps
    serving the old file at a reused path, and probing a path first gets its 404 cached."""
    import upload
    jdir, job = load(args.job)
    problems = sr_post.post_problems(job)
    if problems:
        common.die("[sr] the post copy is not ready:\n  - " + "\n  - ".join(problems))
    state = common.get_state(args.job)
    done = state.get("uploads", [])
    suffix = f"_v{len(done) + 1}" if done else ""
    cfg = common.load_config()
    urls = []
    out = jdir / "out"
    for name in (sr_post.main_video(job), "post.txt", "posts.md"):
        if not (out / name).exists():
            common.die(f"{out / name} is missing, render first")
    names = (sr_post.VHS_VIDEO, sr_post.VIDEO, nomusic_path(Path(sr_post.VHS_VIDEO)).name,
             nomusic_path(Path(sr_post.VIDEO)).name, sr_post.COVER, "post.txt", "posts.md")
    for f in [out / n for n in names
              if (out / n).exists()]:
        # The folder's name, not args.job: a job given as a full path once uploaded to
        # faceless//Users/... (2026-10-25).
        url = upload.put_file(cfg, f, f"faceless/{jdir.name}/{f.stem}{suffix}{f.suffix}")
        print(f"[sr] {url}  {verify_size(url, f.stat().st_size)}")
        urls.append(url)
    common.set_state(args.job, status="uploaded", video_urls=urls,
                     uploads=done + [{"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "urls": urls}])


def verify_size(url, size):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=60) as resp:
            got = int(resp.headers.get("Content-Length", -1))
    except Exception as exc:  # the upload itself succeeded; this is only a check
        return f"(could not verify: {exc})"
    return "size ok" if got == size else f"SIZE MISMATCH: CDN {got} vs local {size}"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new")
    p.add_argument("url")
    p.add_argument("images")
    p.add_argument("--word")
    p.add_argument("--title")
    p.set_defaults(fn=cmd_new)
    for name, fn in (("check", cmd_check), ("stills", cmd_stills), ("approve", cmd_approve),
                     ("kling-frames", cmd_kling_frames), ("upload", cmd_upload)):
        p = sub.add_parser(name)
        p.add_argument("job")
        p.set_defaults(fn=fn)
    p = sub.add_parser("cutouts")
    p.add_argument("job")
    p.add_argument("--force", action="store_true", help="redo rembg even when a cutout exists")
    p.set_defaults(fn=cmd_cutouts)
    p = sub.add_parser("plate")
    p.add_argument("job")
    p.add_argument("--n", type=int, default=3)
    p.add_argument("--model", default="flux")
    p.add_argument("--seed", type=int)
    p.set_defaults(fn=cmd_plate)
    p = sub.add_parser("prep-clip")
    p.add_argument("job")
    p.add_argument("src")
    p.add_argument("--shot")
    p.set_defaults(fn=cmd_prep_clip)
    p = sub.add_parser("preview")
    p.add_argument("job")
    p.add_argument("--from", dest="t0", type=float)
    p.add_argument("--to", dest="t1", type=float)
    p.set_defaults(fn=cmd_preview)
    p = sub.add_parser("render")
    p.add_argument("job")
    p.add_argument("--no-preview", action="store_true")
    p.add_argument("--clean", action="store_true", help="no VHS pass: the clean out/final_9x16.mp4")
    p.add_argument("--out", help="write the final here instead of out/ (no post kit, no status change)")
    p.set_defaults(fn=cmd_render)
    p = sub.add_parser("kit")
    p.add_argument("job")
    p.add_argument("--out-dir")
    p.set_defaults(fn=cmd_kit)
    args = parser.parse_args()
    try:
        args.fn(args)
    except (RuntimeError, FileNotFoundError, ValueError) as err:
        common.die(f"[sr] {err}")


if __name__ == "__main__":
    main()
