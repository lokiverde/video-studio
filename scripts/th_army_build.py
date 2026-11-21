"""Draws an army-style talking-head job's stills into public/army/ (th_army.asset_files):
the navy grain canvas, each inset's punch line on a transparent layer, each graphic beat
through army.py, and the end card. Run by `th.py sheet`, never by render, so what Tony
approved is exactly what renders.

FLUX pictures (frame and stamp backdrops, card art, tiles) are cached in work/graphic/
under a hash of prompt, size and seed: editing any on-screen text redraws in seconds,
editing a prompt or setting a beat's "seed" renders a new picture."""
import hashlib
import shutil

import army
import army_draw as d
import common
import th_army

FLUX_LANDSCAPE = (1280, 720)   # FLUX canvas for full-frame backdrops, same as faceless
WIPE_FONT_PX = 900
CLIP_TAIL_S = 1.0              # a recording keeps playing while the card pans away


def _seed(prompt, beat):
    if isinstance(beat.get("seed"), int):
        return beat["seed"]
    return int(hashlib.sha1(prompt.encode()).hexdigest()[:8], 16) % 2**31


def _picture(cache, cfg, theme, prompt, size, seed):
    """One cached FLUX picture: work/graphic/<hash>.png. Returns its path."""
    import gen_images   # lazy: only when a beat needs a picture
    key = hashlib.sha1(f"{prompt}|{size[0]}x{size[1]}|{seed}".encode()).hexdigest()[:16]
    path = cache / f"{key}.png"
    if not path.exists():
        image, _, took = gen_images.flux_picture(cfg, theme, prompt, size, seed)
        image.save(path)
        print(f"[th] FLUX {size[0]}x{size[1]} {took:.0f}s: {prompt[:60]}")
    return path


def _graphic(beat, size, style, ctx, seed):
    """One army.py graphic drawn at size. Split cards are wider than tall in both cuts, so
    they share the landscape FLUX pictures with the 16:9 full-screen graphics."""
    from PIL import Image
    graphic, prompt = beat["graphic"], beat.get("prompt", "")
    images = th_army.card_images(beat)
    if images:
        return army.render(graphic, size, style, [_logo_art(ctx["public"], images, style)], seed=seed)
    flux = FLUX_LANDSCAPE[::-1] if size[1] > size[0] else FLUX_LANDSCAPE
    base_seed = _seed(prompt or str(graphic), beat)
    paths = [_picture(ctx["cache"], ctx["cfg"], ctx["theme"], p, s, base_seed + i)
             for i, (_, p, s, _) in enumerate(army.pictures(graphic, prompt, flux))]
    cutout = None
    if graphic["type"] == "stamp":
        import gen_images
        cutout = gen_images.subject_cutout(paths[0])
    pics = [Image.open(p).convert("RGB") for p in paths]
    return army.render(graphic, size, style, pics, cutout, seed=seed)


def _logo_art(public, files, style):
    """Card art for a brand: its official logo files exactly as provided (only transparent
    padding trimmed, never recoloured), centred on the dark navy, two side by side."""
    from PIL import Image
    w, h = army.CARD_PICTURE
    art = Image.new("RGB", (w, h), d.rgb(style["bg_deep"]))
    logos = [Image.open(public / f).convert("RGBA") for f in files]
    logos = [im.crop(im.getbbox() or (0, 0, *im.size)) for im in logos]
    gap = w * 0.08
    side = w * 0.56 if len(logos) == 1 else (w * 0.84 - gap) / 2
    logos = [im.resize((max(1, round(im.width * side / max(im.size))), max(1, round(im.height * side / max(im.size)))),
                       Image.LANCZOS) for im in logos]
    x = (w - sum(im.width for im in logos) - gap * (len(logos) - 1)) / 2
    for im in logos:
        art.paste(im, (round(x), round(h * 0.45 - im.height / 2)), im)
        x += im.width + gap
    return art


def _wipe_number(number, style):
    """The number that sweeps across before a trading card beside Tony: huge Anton in the
    light-blue gradient on a transparent layer, with a soft shadow. Same for both cuts."""
    from PIL import Image, ImageFilter
    word = d.word_image(number, d.font(WIPE_FONT_PX), style, accent=True)
    pad = WIPE_FONT_PX // 10
    out = Image.new("RGBA", (word.width + pad * 2, word.height + pad * 2), (0, 0, 0, 0))
    shade = Image.new("RGBA", word.size, d.rgb(style["bg_deep"]) + (0,))
    shade.putalpha(word.getchannel("A").point(lambda a: a * 0.7))
    out.alpha_composite(shade.filter(ImageFilter.GaussianBlur(pad // 2)), (pad, pad + pad // 2))
    out.alpha_composite(word, (pad, pad))
    return out


def _clip_card(beat, size, style, seed):
    """The card behind a screen recording: the navy grain, the label in Anton on the left
    and a shadowed plate where the template plays the recording."""
    from PIL import Image, ImageDraw, ImageFilter
    card = d.canvas(size, style, seed=seed).convert("RGBA")
    label = th_army.clip_label(beat)
    window, label_box = th_army.clip_boxes(size, bool(label), beat.get("wide"))
    x0, y0, x1, y1 = window
    pad = round(size[1] * 0.03)
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x0, y0 + pad / 2, x1, y1 + pad), th_army.CLIP_RADIUS, fill=(0, 8, 16, 150))
    card.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(pad)))
    ImageDraw.Draw(card).rounded_rectangle(window, th_army.CLIP_RADIUS, fill=d.rgb(style["bg_deep"]) + (255,))
    if label:
        army._punch_lines(card, label, label_box, style, beat.get("accent"), layer=True)
    return card.convert("RGB")


def _highlighted(img, marks, origin, style):
    """Highlighter boxes over an article shot, multiplied in so black type stays black.
    marks are [x0, y0, x1, y1] in the uncropped image's pixels; origin is the crop corner."""
    from PIL import Image, ImageChops, ImageDraw
    if not marks:
        return img
    ink = Image.new("RGB", img.size, (255, 255, 255))
    draw = ImageDraw.Draw(ink)
    ox, oy = origin
    for x0, y0, x1, y1 in marks:
        draw.rounded_rectangle((x0 - ox, y0 - oy, x1 - ox, y1 - oy), 6, fill=d.rgb(style["accent_hi"]))
    return ImageChops.multiply(img, ink)


def _shot_card(jdir, beat, size, style, seed, portrait):
    """The card behind an article shot: the navy grain, the label in Anton above and the
    snapshot (cropped for this cut, highlighted) framed under it with a light-blue rule."""
    from PIL import Image, ImageDraw, ImageFilter
    card = d.canvas(size, style, seed=seed).convert("RGBA")
    label = th_army.clip_label(beat)
    shot = Image.open(jdir / "public" / th_army.shot_image(beat, portrait)).convert("RGB")
    crop = th_army.shot_crop(beat, portrait) or [0, 0, shot.width, shot.height]
    shot = _highlighted(shot.crop(tuple(crop)), th_army.shot_marks(beat, portrait), crop[:2], style)
    (x0, y0, x1, y1), label_box = th_army.shot_layout(size, bool(label), shot.width / shot.height)
    shot = shot.resize((round(x1 - x0), round(y1 - y0)), Image.LANCZOS)
    x, y = round(x0), round(y0)
    r, rule = th_army.CLIP_RADIUS, th_army.CLIP_RULE
    pad = round(size[1] * 0.03)
    shadow = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((x, y + pad / 2, x + shot.width, y + shot.height + pad), r, fill=(0, 8, 16, 150))
    card.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(pad)))
    mask = Image.new("L", shot.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, shot.width - 1, shot.height - 1), r, fill=255)
    card.paste(shot, (x, y), mask)
    ImageDraw.Draw(card).rounded_rectangle((x, y, x + shot.width - 1, y + shot.height - 1), r,
                                           outline=d.rgb(style["accent"]) + (255,), width=rule)
    if label:
        army._punch_lines(card, label, label_box, style, beat.get("accent"), layer=True)
    return card.convert("RGB")


def _check_clips(jdir, job):
    """Each recording must run long enough to cover its beat, or the card would freeze."""
    import subprocess
    import th_lib
    cuts = job.get("cuts", [])
    for beat in th_army.sorted_beats(job):
        if not th_army.is_clip(beat):
            continue
        path = jdir / "public" / beat["clip"]
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                             capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if out.returncode != 0:
            common.die(f"can't read {beat['clip']} in public/: {out.stderr.strip()}")
        shown = th_lib.to_output(beat["to"], cuts) - th_lib.to_output(beat["from"], cuts) + CLIP_TAIL_S
        need = beat.get("start", 0) + shown * beat.get("rate", 1)
        if need > float(out.stdout.strip()):
            common.die(f"{beat['clip']} is {float(out.stdout):.1f}s, the beat at {beat['from']}s needs {need:.1f}s: "
                       "lower its start or raise its rate")


def build(job_id, job):
    """Redraw every asset for both cuts. Returns the list of files written."""
    jdir = common.job_dir(job_id)
    out = jdir / "public" / th_army.ASSET_DIR
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    cache = jdir / "work" / "graphic"
    cache.mkdir(parents=True, exist_ok=True)
    theme = common.load_theme("army")
    style = d.style_of(theme.get("army_style"))
    ctx = {"cache": cache, "cfg": common.load_config(), "theme": theme, "public": jdir / "public"}
    beats = th_army.sorted_beats(job)
    _check_clips(jdir, job)
    written = []
    for aspect, size in th_army.ASPECTS.items():
        def save(img, kind, n=None):
            name = th_army.asset_name(kind, aspect, n)
            img.save(jdir / "public" / name)
            written.append(name)

        save(d.canvas(size, style, seed=7), "canvas")
        for n, beat in enumerate(beats, 1):
            if beat["layout"] == "graphic":
                save(_graphic(beat, size, style, ctx, seed=n), "beat", n)
            elif th_army.is_clip(beat):
                save(_clip_card(beat, th_army.card_size(aspect), style, seed=n), "beat", n)
            elif th_army.is_shot(beat):
                save(_shot_card(jdir, beat, th_army.card_size(aspect), style, seed=n, portrait=aspect == "9x16"), "beat", n)
            elif beat["layout"] == "split":
                save(_graphic(beat, th_army.card_size(aspect), style, ctx, seed=n), "beat", n)
            elif th_army.has_text(beat):
                save(army.punch_overlay(beat["text"], size, style, beat.get("accent")), "text", n)
        for _, number in th_army.wipes(job):
            save(_wipe_number(number, style), "wipe", number)
        headline = th_army.end_headline(job)
        if headline:
            save(army.render({"type": "words", "text": headline}, size, style, seed=11), "end")
    print(f"[th] army: drew {len(written)} stills into {out}")
    return written
