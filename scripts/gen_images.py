"""Render one FLUX still per scene on Tim, plus a contact sheet for the preview gate."""
import argparse
import io
import random

import clips
import common
import mograph
import photos

DEV_GUIDANCE = 3.5
# A washed-out frame (soft edges, no black outlines, the whole thing out of focus) was
# flux-dev inheriting schnell's "simple" scheduler; tim-media now puts dev on "beta" and
# the failure is gone. This gate stays as a tripwire: the check costs nothing and the
# same symptom from any future cause would otherwise sail through a contact sheet.
# A clean 1920x1088 frame of this style measures 2 and up even on a plain background;
# the washed ones measured 0.2 to 0.6.
SOFT_HF_STD = 1.5
SOFT_RETRIES = 2


def compose_prompt(theme, scene, inject_character=True):
    """Action first (FLUX weights early tokens most), then character spec only
    when the recurring hero is in the shot, then the style tail.
    inject_character=False is the figure-block path: the character is drawn and
    composited after generation, so nothing about him may reach the sampler."""
    prompt = scene["image_prompt"]
    character = theme.get("character_desc", "")
    hero_in_shot = inject_character and "main character" in prompt.lower()
    parts = [prompt]
    if character and hero_in_shot:
        parts.append(character)
    parts += [theme.get("style_prefix", ""), theme.get("style_suffix", "")]
    text = ". ".join(p.strip().rstrip(",").rstrip(".") for p in parts if p.strip())
    # A LoRA only fires on its trigger word, and only in shots the hero is actually in.
    trigger = theme.get("lora_trigger", "")
    if trigger and hero_in_shot:
        text = f"{trigger}, {text}"
    return text


def shot_files(work, scene_id, count):
    """Filenames for a scene's shots: scene_NN.png, then scene_NN_2.png etc."""
    names = [work / f"scene_{scene_id:02d}.png"]
    names += [work / f"scene_{scene_id:02d}_{k}.png" for k in range(2, count + 1)]
    return names


def pick_model(cfg, hero):
    """schnell (model "flux") is a 4-step distilled model. It draws scenery fine, but
    it returns a structurally broken figure -- detached head, third hand, missing leg --
    in roughly 3 hero shots out of 10, no matter how good the prompt or the reference
    is. dev is undistilled and comes out whole, at about 5x the render time. So: dev
    wherever the character appears, schnell everywhere else. Set IMG_MODEL=flux in
    config.env to force the cheap model for a draft pass."""
    forced = cfg.get("IMG_MODEL", "")
    if forced:
        return forced
    return "flux-dev" if hero else "flux"


def sharpness(png_bytes):
    """How much the frame changes under a small blur. Flat vector art has hard edges,
    so a washed-out render scores near zero while a clean one scores well above 2."""
    from PIL import Image, ImageChops, ImageFilter, ImageStat
    image = Image.open(io.BytesIO(png_bytes)).convert("L")
    diff = ImageChops.difference(image, image.filter(ImageFilter.GaussianBlur(2)))
    return ImageStat.Stat(diff).stddev[0]


LETTERBOX_DARK = 24      # a row whose brightest pixel is below this is a bar
LETTERBOX_MIN_ROWS = 4   # ignore a stray dark line; real bars are 15-40 rows at 720p


def trim_letterbox(img):
    """FLUX sometimes paints cinema bars into the frame (seen 2026-09-16, 20 rows top and
    bottom on a 720p still). They survive every later crop and show up as black bands in
    the video. Cut them off and cover-scale back to the canvas. Returns (image, rows cut)."""
    from PIL import Image
    grey = img.convert("L")
    w, h = grey.size

    def dark(y):
        return grey.crop((0, y, w, y + 1)).getextrema()[1] < LETTERBOX_DARK

    limit = h // 6
    top = next((y for y in range(limit) if not dark(y)), limit)
    bottom = next((y for y in range(limit) if not dark(h - 1 - y)), limit)
    if top < LETTERBOX_MIN_ROWS and bottom < LETTERBOX_MIN_ROWS:
        return img, 0
    cut = max(top, bottom) + 2
    inner = img.crop((0, cut, w, h - cut))
    scaled = inner.resize((round(w * h / inner.height), h), Image.LANCZOS)
    left = (scaled.width - w) // 2
    return scaled.crop((left, 0, left + w, h)), cut


PUNCH_RANGE = (1.0, 2.0)   # past 2x a 720p background turns to mush


def punch_in(img, factor, x=0.5):
    """Crop toward (x, vertical centre) and scale back to the canvas: the cheap camera
    move. A held background punched to 1.4 under a close-up reads as a new angle."""
    lo, hi = PUNCH_RANGE
    if not lo <= factor <= hi:
        raise ValueError(f"punch must be from {lo} to {hi}, got {factor!r}")
    if factor == 1.0:
        return img
    from PIL import Image
    w, h = img.size
    cw, ch = w / factor, h / factor
    left = min(max(x * w - cw / 2, 0), w - cw)
    top = (h - ch) * 0.42          # slightly above centre: floors are less interesting
    return img.crop((round(left), round(top), round(left + cw), round(top + ch))) \
              .resize((w, h), Image.LANCZOS)


def bg_path(out_path):
    """Where a shot's bare background (no figure pasted) is kept, so a later shot can
    hold on it. Its own folder, so the contact-sheet globs never see it."""
    return out_path.parent / "bg" / out_path.name


def hold_sources(data, work, prefix=""):
    """{shot file: background file it holds on}. A hold always reaches back to the last
    GENERATED background, so a run of holds all punch from the same clean original."""
    sources, last = {}, None
    graphics = common.graphics_module(data.get("theme", "sketch"))
    for scene in data["scenes"]:
        specs = common.shot_specs(scene)
        for spec, out in zip(specs, shot_files(work, scene["id"], len(specs))):
            out = out.with_name(prefix + out.name)
            if spec.get("hold"):
                sources[out] = last
            elif scene.get("mograph") is not None:
                continue   # drawn by Remotion, no background to hold on
            elif not spec.get("photo") and spec.get("card") is None and (
                    spec.get("graphic") is None
                    or graphics.has_backdrop(spec["graphic"], spec.get("prompt", ""))):
                last = bg_path(out)
    return sources


def card_one(theme, spec, out_path, size):
    """A number card shot: drawn by cards.py, no FLUX call."""
    import cards
    try:
        cards.render(spec["card"], size, theme.get("card_style")).save(out_path)
    except ValueError as err:
        raise RuntimeError(f"{out_path.name}: {err}")
    print(f"[gen_images] {out_path.name}: card {cards.parse(spec['card'])[0]}")
    return {"seed": 0, "model": "card", "gen_s": 0.0}




def has_overlay(spec):
    return spec.get("tag") is not None or spec.get("note") is not None


def stamp_overlays(out_path, spec, theme):
    """Draw a shot's date tag and corner note (docs/swordfish.md) over its finished still."""
    if not has_overlay(spec):
        return
    import doodle
    from PIL import Image
    doodle.overlay(Image.open(out_path), spec.get("tag"), spec.get("note"),
                   theme.get("graphic_style")).save(out_path)


def flux_picture(cfg, theme, prompt, size, seed=None):
    """One FLUX picture at size for a graphic. Never the hero path: graphics carry no
    drawn character, so schnell unless the theme or config asks for dev.
    Returns (PIL image, seed, gen seconds)."""
    from PIL import Image
    model = cfg.get("IMG_MODEL") or theme.get("image_model") or "flux"
    payload = {"prompt": compose_prompt(theme, {"image_prompt": prompt}, inject_character=False),
               "model": model, "width": int(size[0]), "height": int(size[1]),
               "seed": seed if seed is not None else random.randint(1, 2**31)}
    if model == "flux-dev":
        payload["guidance"] = float(cfg.get("IMG_GUIDANCE", DEV_GUIDANCE))
    data, headers = common.http_json(f"{cfg['TIM_MEDIA_URL']}/image", payload,
                                     timeout=900, with_headers=True)
    if len(data) < 1000:
        raise RuntimeError(f"suspiciously small image ({len(data)} bytes) for: {prompt[:60]}")
    frame, _ = trim_letterbox(Image.open(io.BytesIO(data)).convert("RGB"))
    return frame, payload["seed"], float(headers.get("x-gen-seconds", 0) or 0)


def subject_cutout(picture_path):
    """The stamp subject lifted off its picture (macOS Vision, else rembg; vision.subject_cutout),
    cached beside the picture. None where neither is installed or nothing is found;
    army then draws the stamp with the picture framed under the type."""
    from PIL import Image
    import vision
    cut = picture_path.with_name(picture_path.stem + "_cut.png")
    if not cut.exists() or cut.stat().st_mtime < picture_path.stat().st_mtime:
        ok, why = vision.subject_cutout(picture_path, cut)
        if not ok:
            print(f"[gen_images] {picture_path.name}: no cutout ({why}), stamp drawn without cutout")
            return None
    return Image.open(cut).convert("RGBA")


def graphic_one(cfg, theme, spec, out_path, final_size, seed=None, regen="all"):
    """A graphic shot: Army (docs/army.md) or doodle (docs/swordfish.md), whichever the
    theme draws with. FLUX renders the pictures the layout needs, the module draws the
    frame at the final video resolution. Pictures are cached in
    work/graphic/: card art and tiles are shared by both cuts, canvas-shaped backdrops
    are rendered per cut. regen: "all" rerolls every picture, "own" only this cut's
    backdrop, "none" draws from the cache alone (restage). Returns timing info, or
    None when regen="none" finds a picture missing."""
    from PIL import Image
    graphics = common.graphics_module(theme)
    graphic, prompt = spec["graphic"], spec.get("prompt", "")
    canvas = (int(cfg["IMG_W"]), int(cfg["IMG_H"]))
    cache = out_path.parent / "graphic"
    cache.mkdir(exist_ok=True)
    stem = out_path.stem
    shared_stem = stem[2:] if stem.startswith("p_") else stem
    pics, paths, first_seed, gen_s = [], [], seed, 0.0
    for i, (name, pic_prompt, size, shared) in enumerate(graphics.pictures(graphic, prompt, canvas)):
        path = cache / f"{shared_stem if shared else stem}_{name}.png"
        fresh = regen == "all" or (regen == "own" and not shared)
        if fresh or not path.exists():
            if regen == "none":
                print(f"[gen_images] {out_path.name}: {path.name} not rendered yet, skipped")
                return None
            image, used, took = flux_picture(cfg, theme, pic_prompt, size,
                                             None if seed is None else seed + i)
            image.save(path)
            first_seed = used if first_seed is None else first_seed
            gen_s += took
        pics.append(Image.open(path).convert("RGB"))
        paths.append(path)
    cutout = subject_cutout(paths[0]) if graphic["type"] == "stamp" else None
    style = theme.get("graphic_style", theme.get("army_style"))
    graphics.render(graphic, final_size, style, pics, cutout,
                    seed=sum(map(ord, shared_stem))).save(out_path)
    if graphics.has_backdrop(graphic, prompt):
        bg_path(out_path).parent.mkdir(exist_ok=True)
        pics[0].save(bg_path(out_path))
    print(f"[gen_images] {out_path.name}: graphic {graphic['type']} "
          f"({len(pics)} picture{'s' * (len(pics) != 1)}, gen={gen_s:.0f}s)")
    return {"seed": first_seed or 0, "model": f"graphic:{graphic['type']}", "gen_s": gen_s}


def hold_one(source, out_path, spec, figure):
    """A held shot: no FLUX call. The earlier background, optionally punched in, with
    this shot's own figure (new pose, new mood, new framing) pasted on."""
    from PIL import Image
    import composite
    if source is None or not source.exists():
        raise RuntimeError(f"{out_path.name}: nothing to hold on ({source}); render the "
                           f"shot before it first")
    try:
        frame = punch_in(Image.open(source).convert("RGB"), float(spec.get("punch", 1.0)),
                         float(spec.get("punch_x", 0.5)))
    except ValueError as err:
        raise RuntimeError(f"{out_path.name}: {err}")
    if figure is not None:
        frame = composite.place(frame, figure)
    frame.save(out_path, quality=95)
    print(f"[gen_images] {out_path.name}: held on {source.name} punch={spec.get('punch', 1.0)}")
    return {"seed": 0, "model": "hold", "gen_s": 0.0}


def gen_one(cfg, theme, scene, out_path, seed=None, figure=None):
    """Render one still. With a figure block the sampler only ever sees the
    background: the character is drawn by composite.py and pasted on afterwards,
    so the shot runs on schnell with no reference, no LoRA, and no injection.
    Returns {"seed": int, "model": str, "gen_s": float}."""
    hero = figure is None and "main character" in scene["image_prompt"].lower()
    payload = {
        "prompt": compose_prompt(theme, scene, inject_character=figure is None),
        "model": pick_model(cfg, hero),
        "width": int(cfg["IMG_W"]),
        "height": int(cfg["IMG_H"]),
        "seed": seed if seed is not None else random.randint(1, 2**31),
    }
    if payload["model"] == "flux-dev":
        payload["guidance"] = float(cfg.get("IMG_GUIDANCE", DEV_GUIDANCE))
    if theme.get("reference_file") and hero:
        payload["reference"] = theme["reference_file"]
        payload["reference_strength"] = theme.get("reference_strength", 0.2)
        payload["reference_mode"] = theme.get("reference_mode", "attn_bias")
    # Only sent when the character's LoRA is marked deployable. tim-media leaves the
    # workflow graph untouched when lora is absent, so every other caller is unaffected.
    if theme.get("lora_file") and hero:
        payload["lora"] = theme["lora_file"]
        payload["lora_strength"] = theme.get("lora_strength", 1.0)
    # dev spends 130-150s on a 1920x1088 frame, so the old 180s ceiling would time out
    # the moment two jobs queued behind each other on Tim.
    for attempt in range(SOFT_RETRIES + 1):
        data, resp_headers = common.http_json(f"{cfg['TIM_MEDIA_URL']}/image", payload,
                                              timeout=900, with_headers=True)
        if len(data) < 1000:
            raise RuntimeError(
                f"suspiciously small image ({len(data)} bytes) for scene {scene['id']}")
        hf = sharpness(data)
        # A washed-out frame is worth catching here rather than at review time: the
        # check is free, and a caller that only looks at a contact sheet will not see it.
        if hf >= SOFT_HF_STD or payload["model"] != "flux-dev" or attempt == SOFT_RETRIES:
            break
        payload["seed"] = random.randint(1, 2**31)
        print(f"[gen_images] scene {scene['id']}: washed out (hf={hf:.2f}), "
              f"reroll seed={payload['seed']}")
    import io
    from PIL import Image
    frame, cut = trim_letterbox(Image.open(io.BytesIO(data)))
    if cut:
        print(f"[gen_images] scene {scene['id']}: trimmed {cut}px letterbox bars FLUX painted in")
    bg_path(out_path).parent.mkdir(exist_ok=True)
    frame.save(bg_path(out_path))
    if figure is not None:
        import composite
        frame = composite.place(frame, figure)
    if figure is not None or cut:
        frame.save(out_path, quality=95)
    else:
        out_path.write_bytes(data)
    gen_s = float(resp_headers.get("x-gen-seconds", 0) or 0)
    print(f"[gen_images] scene {scene['id']}: {out_path.name} "
          f"model={payload['model']} seed={payload['seed']} hf={hf:.2f} gen={gen_s:.0f}s"
          + (f" figure={'+'.join(m.get('pose', '?') for m in composite.cast(figure))}"
             if figure else ""))
    return {"seed": payload["seed"], "model": payload["model"], "gen_s": gen_s}


def _sheet(files, out_path, thumb_w, max_cols, guide=None):
    from PIL import Image, ImageDraw
    if not files:
        return None
    thumbs = []
    for f in files:
        img = Image.open(f).convert("RGB")
        ratio = thumb_w / img.width
        thumb = img.resize((thumb_w, round(img.height * ratio)))
        if guide:
            guide(ImageDraw.Draw(thumb, "RGBA"), thumb.size)
        thumbs.append(thumb)
    cols = min(max_cols, len(thumbs))
    rows = (len(thumbs) + cols - 1) // cols
    cell_h = max(t.height for t in thumbs)
    pad = 6
    sheet = Image.new("RGB", (cols * (thumb_w + pad) + pad, rows * (cell_h + pad) + pad), "white")
    for i, t in enumerate(thumbs):
        sheet.paste(t, (pad + (i % cols) * (thumb_w + pad), pad + (i // cols) * (cell_h + pad)))
    sheet.save(out_path, quality=88)
    return out_path


def _shot_order(path):
    """scene_02_10 sorts after scene_02_2. A plain string sort put shot 10 before shot 2
    the first time a scene had ten shots, and the sheet read out of story order."""
    import re
    return [int(n) for n in re.findall(r"\d+", path.stem)]


def contact_sheet(work):
    """Tile every landscape still (all shots) into one preview jpg (3 columns)."""
    return _sheet(sorted(work.glob("scene_*.png"), key=_shot_order), work / "contact_sheet.jpg", 480, 3)


def _vertical_guides(draw, size):
    """Shade what the viewer will not see clearly on a phone: the caption band and the
    platform UI strip under it. Anything important must sit above the upper line."""
    w, h = size
    draw.rectangle([0, round(h * 0.76), w, round(h * 0.83)], fill=(60, 50, 110, 70))
    draw.rectangle([0, round(h * 0.83), w, h], fill=(0, 0, 0, 60))


def contact_sheet_portrait(work):
    """The 9:16 preview: every p_ still side by side, caption band and UI strip shaded."""
    return _sheet(sorted(work.glob("p_scene_*.png"), key=_shot_order), work / "contact_sheet_9x16.jpg",
                  270, 6, guide=_vertical_guides)


PORTRAIT_FIGURE_HINT = ("tall vertical composition, the main subject sits small in the upper "
                        "third of the frame, the lower two thirds is wide open empty ground, "
                        "artwork runs edge to edge to all four sides")


def run_portrait(job_id, only_scene=None, only_shot=None, seed=None, prompt_override=None):
    """Second pass: portrait-native renders (1088x1920) of every shot, reusing
    each shot's landscape seed so subject and style carry over. Files get a
    p_ prefix; assemble's vertical cut prefers them over cropped landscape.

    Portrait is a fresh generation pass, so it re-rolls the skin-tone drift the
    landscape set was curated past. Pass only_scene/only_shot to fix one frame
    without re-rendering the whole video."""
    cfg = common.load_config()
    data = common.load_scenes(job_id)
    theme = common.load_theme(data.get("theme", "sketch"))
    work = common.job_dir(job_id) / "work"
    seeds = common.get_state(job_id).get("seeds", {})
    holds = hold_sources(data, work, prefix="p_")
    cfg_p = {**cfg, "IMG_W": cfg["IMG_H"], "IMG_H": cfg["IMG_W"]}
    for scene in data["scenes"]:
        if only_scene is not None and scene["id"] != only_scene:
            continue
        specs = common.shot_specs(scene)
        for k, (spec, out) in enumerate(
                zip(specs, shot_files(work, scene["id"], len(specs))), 1):
            if only_shot is not None and k != only_shot:
                continue
            import composite
            p_out = out.with_name("p_" + out.name)
            if scene.get("clip"):
                clips.still(scene, clips.resolve(work.parent, scene["clip"]), p_out,
                            int(cfg_p["IMG_W"]), int(cfg_p["IMG_H"]))
                continue
            if scene.get("mograph") is not None:
                mograph.still(scene, theme, p_out, int(cfg_p["IMG_W"]), int(cfg_p["IMG_H"]),
                              portrait=True, fps=int(cfg["FPS"]))
                continue
            if spec.get("photo"):
                # Re-crop from the ORIGINAL, not from the landscape frame: cropping
                # a crop throws away the sides a 9:16 frame still has room for.
                photos.ingest(spec["photo"], p_out, int(cfg_p["IMG_W"]),
                              int(cfg_p["IMG_H"]), spec.get("focus", "auto"))
                stamp_overlays(p_out, spec, theme)
                continue
            if spec.get("card") is not None:
                card_one(theme, spec, p_out, (int(cfg_p["IMG_W"]), int(cfg_p["IMG_H"])))
                stamp_overlays(p_out, spec, theme)
                continue
            if spec.get("graphic") is not None:
                # The backdrop keeps the landscape seed so both cuts show the same scene;
                # a targeted reroll rolls fresh, like every other shot below.
                g_seed = seed if seed is not None else (
                    None if only_scene is not None else seeds.get(f"{scene['id']}.{k}"))
                graphic_one(cfg_p, theme, spec, p_out, common.graphics_module(theme).FINAL_PORTRAIT,
                            g_seed, regen="own")
                stamp_overlays(p_out, spec, theme)
                continue
            if spec.get("hold"):
                hold_one(holds.get(p_out), p_out, spec, composite.portrait_figure(spec["figure"]))
                stamp_overlays(p_out, spec, theme)
                continue
            prompt = prompt_override if (prompt_override and only_shot == k) else spec["prompt"]
            if spec["figure"] is not None:
                # FLUX centres the subject, which in a tall frame is exactly where the
                # pasted figure stands. Send the subject up and keep the floor clear.
                # Phrased positively: FLUX ignores negations (docs/leg-watch.md).
                lead = composite.cast(composite.portrait_figure(spec["figure"]))[0]
                fig_x = float(lead.get("x", 0.5))
                side = "right" if fig_x < 0.5 else "left"
                prompt = (f"{prompt}, {PORTRAIT_FIGURE_HINT}, the main subject is placed "
                          f"on the {side} side of the frame")
            shot_scene = {**scene, "image_prompt": prompt}
            # A targeted reroll wants a NEW roll, not the landscape seed that already failed.
            use_seed = seed if seed is not None else (
                None if only_scene is not None
                else seeds.get(f"{scene['id']}.{k}") or seeds.get(str(scene["id"])))
            gen_one(cfg_p, theme, shot_scene, p_out, seed=use_seed,
                    figure=composite.portrait_figure(spec["figure"]))
            stamp_overlays(p_out, spec, theme)
    sheet = contact_sheet_portrait(work)
    if only_scene is None:
        common.set_state(job_id, portrait=True)
        print("[gen_images] portrait set complete")
    if sheet:
        print(f"[gen_images] 9:16 contact sheet: {sheet}")


def restage(job_id):
    """Re-paste every figure onto its stored background, both cuts, no FLUX calls. Edit a
    pose, mood, framing or cast member in scenes.json, run this, and the stills update in
    a second or two. Shots rendered before backgrounds were kept are left alone."""
    import composite
    from PIL import Image
    data = common.load_scenes(job_id)
    theme = common.load_theme(data.get("theme", "sketch"))
    graphics = common.graphics_module(theme)
    work = common.job_dir(job_id) / "work"
    done = 0
    for prefix, adapt in (("", lambda f: f), ("p_", composite.portrait_figure)):
        holds = hold_sources(data, work, prefix)
        for scene in data["scenes"]:
            specs = common.shot_specs(scene)
            for spec, out in zip(specs, shot_files(work, scene["id"], len(specs))):
                out = out.with_name(prefix + out.name)
                if spec.get("photo") or not out.exists():
                    continue
                if spec.get("card") is not None:
                    card_one(theme, spec, out, Image.open(out).size)
                    stamp_overlays(out, spec, theme)
                    done += 1
                    continue
                if spec.get("graphic") is not None:
                    cfg = common.load_config()
                    if prefix:
                        cfg = {**cfg, "IMG_W": cfg["IMG_H"], "IMG_H": cfg["IMG_W"]}
                    final = graphics.FINAL_PORTRAIT if prefix else graphics.FINAL_LANDSCAPE
                    if graphic_one(cfg, theme, spec, out, final, regen="none"):
                        stamp_overlays(out, spec, theme)
                        done += 1
                    continue
                if spec.get("hold"):
                    hold_one(holds.get(out), out, spec, adapt(spec["figure"]))
                    stamp_overlays(out, spec, theme)
                    done += 1
                elif bg_path(out).exists() and (spec["figure"] is not None or has_overlay(spec)):
                    frame = Image.open(bg_path(out))
                    if spec["figure"] is not None:
                        frame = composite.place(frame, adapt(spec["figure"]))
                    frame.convert("RGB").save(out, quality=95)
                    stamp_overlays(out, spec, theme)
                    done += 1
    contact_sheet(work)
    contact_sheet_portrait(work)
    print(f"[gen_images] restaged {done} shots, contact sheets rebuilt")


def apply_prompt_override(data, scene, only_shot, prompt_override, job_id):
    """Replace one shot's prompt in scenes.json, keeping its figure block if it has one."""
    import json
    idx = max(0, only_shot - 1)
    raw = scene.get("shots")
    if raw:
        old = raw[idx]
        raw[idx] = {**old, "prompt": prompt_override} if isinstance(old, dict) \
            else prompt_override
    else:
        scene["image_prompt"] = prompt_override
    (common.job_dir(job_id) / "scenes.json").write_text(json.dumps(data, indent=2))


def run(job_id, only_scene=None, seed=None, prompt_override=None, only_shot=1):
    cfg = common.load_config()
    data = common.load_scenes(job_id)
    theme = common.load_theme(data.get("theme", "sketch"))
    work = common.job_dir(job_id) / "work"
    state = common.get_state(job_id)
    seeds = state.get("seeds", {})
    timings = state.get("timings", {})
    holds = hold_sources(data, work)

    for scene in data["scenes"]:
        if only_scene is not None and scene["id"] != only_scene:
            continue
        if prompt_override and scene["id"] == only_scene:
            apply_prompt_override(data, scene, only_shot, prompt_override, job_id)
        specs = common.shot_specs(scene)
        files = shot_files(work, scene["id"], len(specs))
        for k, (spec, out) in enumerate(zip(specs, files), 1):
            if only_scene is not None and only_shot and k != only_shot:
                continue
            key = f"{scene['id']}.{k}"
            if scene.get("clip"):
                clips.still(scene, clips.resolve(work.parent, scene["clip"]), out,
                            int(cfg["IMG_W"]), int(cfg["IMG_H"]))
                timings[key] = {"model": "clip", "gen_s": 0.0}
            elif scene.get("mograph") is not None:
                mograph.still(scene, theme, out, int(cfg["IMG_W"]), int(cfg["IMG_H"]),
                              portrait=False, fps=int(cfg["FPS"]))
                timings[key] = {"model": "mograph", "gen_s": 0.0}
            elif spec.get("photo"):
                photos.stash(job_id, spec["photo"])
                photos.ingest(spec["photo"], out, int(cfg["IMG_W"]), int(cfg["IMG_H"]),
                              spec.get("focus", "auto"))
                timings[key] = {"model": "photo", "gen_s": 0.0}
            elif spec.get("card") is not None:
                card_one(theme, spec, out, (int(cfg["IMG_W"]), int(cfg["IMG_H"])))
                timings[key] = {"model": "card", "gen_s": 0.0}
            elif spec.get("graphic") is not None:
                result = graphic_one(cfg, theme, spec, out,
                                     common.graphics_module(theme).FINAL_LANDSCAPE, seed)
                seeds[key] = result["seed"]
                timings[key] = {"model": result["model"], "gen_s": result["gen_s"]}
            elif spec.get("hold"):
                hold_one(holds.get(out), out, spec, spec["figure"])
                timings[key] = {"model": "hold", "gen_s": 0.0}
            else:
                shot_scene = {**scene, "image_prompt": spec["prompt"]}
                result = gen_one(cfg, theme, shot_scene, out, seed, figure=spec["figure"])
                seeds[key] = result["seed"]
                timings[key] = {"model": result["model"], "gen_s": result["gen_s"]}
            stamp_overlays(out, spec, theme)

    contact_sheet(work)
    common.set_state(job_id, status="imaged", seeds=seeds, timings=timings)
    print(f"[gen_images] contact sheet: {work / 'contact_sheet.jpg'}")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--job", required=True)
    p.add_argument("--scene", type=int, help="regen just this scene id")
    p.add_argument("--shot", type=int, default=1, help="which shot of the scene (1-based)")
    p.add_argument("--seed", type=int)
    p.add_argument("--prompt", help="replacement image_prompt when regenerating one scene")
    a = p.parse_args()
    run(a.job, a.scene, a.seed, a.prompt, a.shot)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as err:
        common.die(str(err))
