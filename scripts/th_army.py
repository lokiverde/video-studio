"""Army style for the talking-head wrapper: Tony's own footage in the Army format
(docs/army.md, "With Tony on camera"). Pure logic, no I/O; th_army_build.py draws.

A job sets "style": "army" and lists `beats` in SOURCE seconds. Each beat names its layout:

  split    THE MAIN ONE (Tony, 2026-10-17: "similar to the split frame with this kind of
           background"). The quiz tips split on the Army canvas: Tony in his own panel with
           a light-blue frame, an Army graphic in a navy card beside him (above him in 9:16).
           Graphics in a run pan sideways, a big number sweeps across before a trading card.
  full     Tony full frame (also what plays between beats)
  inset    Tony shrinks into the frame box at the top of the navy canvas, a punch line
           in white + light blue Anton under him
  graphic  a full-screen Army graphic (frame, trading, words, stamp, agenda, tiles) drawn
           by army.py as a still, Tony's audio keeps playing

Beats close together, or joined only by full-screen graphics, form one run: Tony holds his
place (panel or box) across it instead of flying out and back. The template gets the runs,
the stills and the geometry from render_props(), so none of it is duplicated in TypeScript."""

LAYOUTS = ("full", "split", "inset", "graphic")
CLIP_RATES = (0.25, 4.0)
CARD_LAYOUTS = ("split", "graphic")    # beats that carry an army.py graphic block
RUN_GAP_S = 0.8          # beats this close read as one run (same as the board's span gap)
MIN_BEAT_S = 0.5         # anything shorter flickers
ASPECTS = {"16x9": (1920, 1080), "9x16": (1080, 1920)}
ASSET_DIR = "army"       # under the job's public/, rebuilt by every sheet
RISER_S = 1.6            # same as th_lib.RISER_S: the riser ends as the number lands
TEXT_SHEET_S = 1.0       # the sheet shows an inset once its punch line has landed
GRAPHIC_SHEET_S = 0.6


def is_army(job):
    return job.get("style") == "army"


def sorted_beats(job):
    return sorted(job.get("beats", []), key=lambda b: b["from"])


def _span_problem(job, start, end):
    cuts = job.get("cuts", [])
    if not 0 <= start < end <= job["srcEnd"]:
        return f"bad range [{start}, {end}] (video ends at {job['srcEnd']})"
    # a beat may hold across a jump cut (the card stays up while Tony cuts), but its edges
    # must land on footage that plays
    if any(a <= start < b or a < end < b for a, b in cuts):
        return f"[{start}, {end}] starts or ends inside a cut"
    return None


def _beat_problems(job, n, beat):
    import army   # lazy: Pillow, only needed for army jobs
    layout = beat.get("layout")
    name = f"beat {n} ({layout})"
    if layout not in LAYOUTS:
        return [f"beat {n}: layout {layout!r} unknown, use one of {', '.join(LAYOUTS)}"]
    if not all(isinstance(beat.get(k), (int, float)) for k in ("from", "to")):
        return [f"{name}: needs numeric from and to (source seconds)"]
    problems = []
    span = _span_problem(job, beat["from"], beat["to"])
    if span:
        problems.append(f"{name}: {span}")
    elif beat["to"] - beat["from"] < MIN_BEAT_S:
        problems.append(f"{name}: {beat['to'] - beat['from']:.2f}s is too short, at least {MIN_BEAT_S}s")
    if layout not in CARD_LAYOUTS and beat.get("graphic") is not None:
        problems.append(f"{name}: has a graphic block, set layout to 'split' or 'graphic'")
    if layout != "split" and beat.get("clip") is not None:
        problems.append(f"{name}: a screen recording ('clip') only plays in a split beat")
    if layout != "split" and beat.get("shot") is not None:
        problems.append(f"{name}: an article shot ('shot') only shows in a split beat")
    media = layout == "split" and (beat.get("clip") is not None or beat.get("shot") is not None)
    if layout in ("full", "split") and not media and str(beat.get("text") or "").strip():
        problems.append(f"{name}: text only shows on inset beats and as a clip's or shot's label (a split beat takes a 'words' graphic)")
    if media and beat.get("clip") is not None and beat.get("shot") is not None:
        problems.append(f"{name}: give a clip or a shot, not both")
    elif media and beat.get("clip") is not None:
        problems += [f"{name}: {p}" for p in _clip_problems(beat)]
    elif media:
        problems += [f"{name}: {p}" for p in _shot_problems(beat)]
    elif layout in CARD_LAYOUTS:
        problems += [f"{name}: {p}" for p in _image_problems(beat)]
        try:
            # a card image stands in for the picture a prompt would draw
            army.validate(beat.get("graphic"), beat.get("prompt") or ("image" if card_images(beat) else ""))
        except ValueError as err:
            problems.append(f"{name}: {err}")
    accent = beat.get("accent")
    if accent is not None and not all(isinstance(a, int) for a in (accent if isinstance(accent, list) else [accent])):
        problems.append(f"{name}: accent is a line number or a list of them (1-based)")
    return problems


def _clip_problems(beat):
    """A split beat that plays a screen recording in the card instead of a graphic."""
    problems = []
    if beat.get("graphic") is not None:
        problems.append("give a clip or a graphic, not both")
    if not isinstance(beat["clip"], str) or not beat["clip"].strip():
        problems.append("clip is a file name in public/")
    start, rate, zoom = beat.get("start", 0), beat.get("rate", 1), beat.get("zoom", 1)
    if not isinstance(start, (int, float)) or start < 0:
        problems.append(f"clip start {start!r} must be seconds into the clip, 0 or more")
    if not isinstance(rate, (int, float)) or not CLIP_RATES[0] <= rate <= CLIP_RATES[1]:
        problems.append(f"clip rate {rate!r} must be {CLIP_RATES[0]} to {CLIP_RATES[1]}")
    if not isinstance(zoom, (int, float)) or zoom < 1:
        problems.append(f"clip zoom {zoom!r} must be 1 or more")
    focus = beat.get("focus", [0.5, 0.5])
    if not (isinstance(focus, list) and len(focus) == 2 and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in focus)):
        problems.append(f"clip focus {focus!r} must be [x, y], fractions of the clip")
    wide = beat.get("wide")
    if wide is not None and (isinstance(wide, bool) or not isinstance(wide, (int, float)) or not 1 <= wide <= 3):
        problems.append(f"clip wide {wide!r} must be the recording's width/height, 1 to 3 (1.5 for a laptop screen)")
    return problems


def _box_problem(box, what):
    if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) and v >= 0 for v in box)
            and box[0] < box[2] and box[1] < box[3]):
        return f"{what} {box!r} must be [x0, y0, x1, y1] in the image's pixels"
    return None


def _shot_problems(beat):
    """A split beat that shows a still (an article snapshot) framed in the card: optional
    crop to the lines that matter and highlighter boxes over the key phrase."""
    problems = []
    if beat.get("graphic") is not None:
        problems.append("give a shot or a graphic, not both")
    if not isinstance(beat["shot"], str) or not beat["shot"].strip():
        problems.append("shot is an image file in public/")
    portrait = beat.get("portraitShot")
    if portrait is not None and (not isinstance(portrait, str) or not portrait.strip()):
        problems.append("portraitShot is an image file in public/ for the 9:16 card")
    for key in ("crop", "portraitCrop"):
        if beat.get(key) is not None:
            problems.append(_box_problem(beat[key], key))
    for key in ("highlight", "portraitHighlight"):
        marks = beat.get(key, [])
        if not isinstance(marks, list):
            problems.append(f"{key} is a list of [x0, y0, x1, y1] boxes")
        else:
            problems += [_box_problem(m, f"{key} box") for m in marks]
    return [p for p in problems if p]


def is_clip(beat):
    return beat["layout"] == "split" and beat.get("clip") is not None


def is_shot(beat):
    return beat["layout"] == "split" and beat.get("shot") is not None


def is_media(beat):
    return is_clip(beat) or is_shot(beat)


def card_images(beat):
    """A trading card's logo files in public/ (one, or two side by side), [] without any."""
    image = beat.get("image")
    if isinstance(image, str):
        return [image]
    return list(image) if isinstance(image, list) else []


def _image_problems(beat):
    """A trading card that shows official logo files instead of a FLUX picture."""
    if beat.get("image") is None:
        return []
    problems = []
    if (beat.get("graphic") or {}).get("type") != "trading":
        problems.append("an 'image' only replaces a trading card's picture")
    files = card_images(beat)
    if not 1 <= len(files) <= 2 or not all(isinstance(f, str) and f.strip() for f in files):
        problems.append("'image' is one or two files in public/")
    return problems


def media_files(job):
    """Screen recordings, article shots (and their 9:16 captures) and card logos the beats
    read from public/."""
    names = []
    for b in sorted_beats(job):
        if is_media(b):
            names += [f for f in (b.get("clip") or b.get("shot"), is_shot(b) and b.get("portraitShot"))
                      if isinstance(f, str)]
        names += [f for f in card_images(b) if isinstance(f, str) and f.strip()]
    return names


def validate(job):
    """Problems with an army job's beats, as plain sentences. Empty when it can render."""
    problems = []
    if job.get("beats") and not is_army(job):
        problems.append("beats are an army style feature, set style to 'army'")
    if not is_army(job):
        return problems
    if job.get("sections"):
        problems.append("army style uses beats, not sections: move each section to a beat")
    beats = sorted_beats(job)
    for n, beat in enumerate(beats, 1):
        problems += _beat_problems(job, n, beat)
    for n, (a, b) in enumerate(zip(beats, beats[1:]), 1):
        if b["from"] < a["to"] - 1e-6:
            problems.append(f"beats {n} and {n + 1} overlap ([{a['from']}, {a['to']}] and [{b['from']}, {b['to']}])")
    return problems


def chains(job):
    """Runs of inset and graphic beats with no full beat between them and no gap over
    RUN_GAP_S on the output timeline (a cut can make two beats adjacent). A full beat, or
    Tony alone on screen for longer than that, ends a chain."""
    from th_lib import to_output   # th_lib imports this module, so import at call time
    cuts = job.get("cuts", [])
    found, cur = [], []
    for beat in sorted_beats(job):
        if beat["layout"] == "full":
            found, cur = (found + [cur]) if cur else found, []
            continue
        if cur and to_output(beat["from"], cuts) - to_output(cur[-1]["to"], cuts) > RUN_GAP_S:
            found, cur = found + [cur], []
        cur = cur + [beat]
    return found + ([cur] if cur else [])


def _places(chain):
    """Where Tony is during each beat of a chain: "split" (his panel), "inset" (the box) or
    "full". A full-screen graphic hides him, so he takes the place of the next beat that
    shows him (already there when the graphic cuts away) or, at the end of the chain,
    springs back to full frame behind it."""
    places = [b["layout"] if b["layout"] in ("split", "inset") else None for b in chain]
    nxt = "full"
    for i in range(len(places) - 1, -1, -1):
        places[i] = places[i] or nxt
        nxt = places[i]
    return places


def runs(job):
    """{"split": [(from, to)], "inset": [(from, to)]} source seconds Tony holds each place."""
    found = {"split": [], "inset": []}
    for chain in chains(job):
        start, place, end = None, None, None
        for beat, here in zip(chain, _places(chain)):
            if here != place:
                if place in found:
                    found[place].append((start, end))
                start, place = beat["from"], here
            end = beat["to"]
        if place in found:
            found[place].append((start, end))
    return found


def inset_runs(job):
    """[(from, to)] source seconds Tony sits in the inset box (see runs())."""
    return runs(job)["inset"]


def split_runs(job):
    return runs(job)["split"]


def asset_name(kind, aspect, n=None):
    """Published path under public/ of a drawn asset. kind: canvas, end, beat, text, wipe
    (n is the number, one image for both cuts)."""
    if kind in ("canvas", "end"):
        return f"{ASSET_DIR}/{kind}_{aspect}.png"
    if kind == "wipe":
        return f"{ASSET_DIR}/wipe_{n}.png"
    suffix = "_text" if kind == "text" else ""
    return f"{ASSET_DIR}/beat{n:02d}{suffix}_{aspect}.png"


def has_text(beat):
    """An inset's punch line (a clip's label is drawn into its card instead)."""
    return beat["layout"] == "inset" and bool(str(beat.get("text") or "").strip())


def clip_label(beat):
    """The Anton label beside a screen recording or above an article shot."""
    return str(beat.get("text") or "").strip() if is_media(beat) else ""


def end_headline(job):
    return str((job.get("endCard") or {}).get("headline") or "").strip()


def wipes(job):
    """[(source seconds, "5")]: a big number sweeps across before every trading card in a
    split beat, like the quiz tips number wipe. "wipe": false in job.json turns it off."""
    if job.get("wipe") is False:
        return []
    return [(b["from"], str(b["graphic"]["number"]).strip()) for b in sorted_beats(job)
            if b["layout"] == "split" and not is_media(b) and b["graphic"].get("type") == "trading"]


def asset_files(job, aspect):
    """Every file th_army_build draws for one cut, in a stable order."""
    names = [asset_name("canvas", aspect)]
    for n, beat in enumerate(sorted_beats(job), 1):
        if beat["layout"] in CARD_LAYOUTS:
            names.append(asset_name("beat", aspect, n))
        elif has_text(beat):
            names.append(asset_name("text", aspect, n))
    names += sorted({asset_name("wipe", aspect, number) for _, number in wipes(job)})
    if end_headline(job):
        names.append(asset_name("end", aspect))
    return names


# Split geometry on the output frame. 16:9: graphics card left, Tony's panel right, both
# full height inside a 44px margin. 9:16: card on top, Tony under it, clear of the platform
# UI (about 200px at the top, 340px at the bottom).
SPLIT = {
    "16x9": {"card": (44, 44, 1212, 992), "tony": (1300, 44, 576, 992)},
    "9x16": {"card": (40, 200, 1000, 880), "tony": (40, 1110, 1000, 470)},
}
SPLIT_RADIUS = 30
SPLIT_RULE = 6           # Tony's light-blue frame; the card gets a fainter, thinner rule
CAPTION_BAND = 0.77      # army.py leaves the bottom quarter of a graphic for captions


def split_rects(aspect):
    """The card and Tony's panel as {x, y, w, h, r, border}, plus where captions sit."""
    def rect(x, y, w, h):
        return {"x": x, "y": y, "w": w, "h": h, "r": SPLIT_RADIUS, "border": SPLIT_RULE}
    card, tony = (rect(*SPLIT[aspect][k]) for k in ("card", "tony"))
    caption = {"x": card["x"], "y": round(card["y"] + card["h"] * CAPTION_BAND), "w": card["w"]}
    return {"card": card, "tony": tony, "caption": caption}


def card_size(aspect):
    """Pixel size a split beat's graphic is drawn at: the card."""
    _, _, w, h = SPLIT[aspect]["card"]
    return (w, h)


CLIP_RADIUS = 22
CLIP_RULE = 4


def clip_boxes(size, labeled, wide=None):
    """Inside a split card that plays a screen recording: (window, label) boxes as
    (x0, y0, x1, y1) card pixels. Labeled, the Anton label takes the left half and the
    recording a tall window on the right; unlabeled, the window sits centred. Both stay
    above the caption band. The recordings are tall browser captures, so tall windows.
    `wide` (the recording's width/height) is a whole-screen capture instead: the window
    takes the card's width at that shape and the label runs above it, like a shot."""
    if wide:
        return shot_layout(size, labeled, wide)
    w, h = size
    top, bottom = h * 0.045, h * (CAPTION_BAND - 0.025)
    if labeled:
        return (w * 0.5, top, w * 0.955, bottom), (w * 0.045, h * 0.08, w * 0.47, h * 0.7)
    return (w * 0.22, top, w * 0.78, bottom), None


SHOT_LABEL_H = 0.26      # of the card height: the Anton label above an article shot
SHOT_GAP = 0.035


def shot_layout(size, labeled, aspect):
    """Inside a split card that shows an article shot of the given width/height aspect:
    (image, label) boxes as card pixels. Snapshots are wide paragraphs, so the shot takes
    the card's width (less if it is tall), the label runs above it, and the pair sits
    centred between the top of the card and the caption band."""
    w, h = size
    top, bottom = h * 0.04, h * (CAPTION_BAND - 0.025)
    head = h * (SHOT_LABEL_H + SHOT_GAP) if labeled else 0
    img_w = min(w * 0.94, (bottom - top - head) * aspect)
    img_h = img_w / aspect
    y0 = top + (bottom - top - head - img_h) / 2
    label = (w * 0.05, y0, w * 0.95, y0 + h * SHOT_LABEL_H) if labeled else None
    return ((w - img_w) / 2, y0 + head, (w + img_w) / 2, y0 + head + img_h), label


def shot_image(beat, portrait):
    """The snapshot a cut frames. `portraitShot` is the same passage captured at phone width
    (tools/article_strip.mjs): cropping a wide snapshot for the narrow 9:16 card slices
    words at the edge, a phone-width capture shows whole lines in big type."""
    return (beat.get("portraitShot") if portrait else None) or beat["shot"]


def shot_crop(beat, portrait):
    """The part of the snapshot a cut shows: in 9:16 `portraitCrop` (of `portraitShot` when
    there is one, never the wide `crop`), otherwise `crop`, otherwise the whole image."""
    if portrait and beat.get("portraitShot"):
        return beat.get("portraitCrop")
    return (beat.get("portraitCrop") if portrait else None) or beat.get("crop")


def shot_marks(beat, portrait):
    """Highlighter boxes in the pixels of the image this cut frames."""
    if portrait and (beat.get("portraitShot") or beat.get("portraitHighlight") is not None):
        return beat.get("portraitHighlight")
    return beat.get("highlight")


def clip_window(aspect, labeled, wide=None):
    """The recording's window in card pixels, for the template."""
    (x0, y0, x1, y1), _ = clip_boxes(card_size(aspect), labeled, wide)
    x0, y0, x1, y1 = (round(v) for v in (x0, y0, x1, y1))
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0, "r": CLIP_RADIUS, "border": CLIP_RULE}


def inset_rect(size):
    """Tony's inset box on the output frame: army's frame box with a punch line, its corner
    radius and the light-blue rule, the same numbers army_draw.framed uses."""
    import army
    (x0, y0, x1, y1), _ = army.frame_boxes(size, True)
    x0, y0, x1, y1 = (round(v) for v in (x0, y0, x1, y1))
    w, h = x1 - x0, y1 - y0
    return {"x": x0, "y": y0, "w": w, "h": h, "r": round(min(w, h) * 0.05),
            "border": max(3, round(min(w, h) * 0.012))}


def render_props(job, portrait):
    """What the Remotion template needs for one cut: drawn files and the inset geometry.
    th.py puts it in the props as job["army"]."""
    aspect = "9x16" if portrait else "16x9"
    beats = []
    for n, beat in enumerate(sorted_beats(job), 1):
        item = {"from": beat["from"], "to": beat["to"], "layout": beat["layout"]}
        if is_clip(beat):
            item.update(file=asset_name("beat", aspect, n), kind="clip", clip=beat["clip"],
                        start=beat.get("start", 0), rate=beat.get("rate", 1), zoom=beat.get("zoom", 1),
                        focus=beat.get("focus", [0.5, 0.5]),
                        window=clip_window(aspect, bool(clip_label(beat)), beat.get("wide")))
        elif is_shot(beat):
            item.update(file=asset_name("beat", aspect, n), kind="shot")
        elif beat["layout"] in CARD_LAYOUTS:
            item.update(file=asset_name("beat", aspect, n), kind=beat["graphic"]["type"])
        if has_text(beat):
            item["textFile"] = asset_name("text", aspect, n)
        beats.append(item)
    return {"canvas": asset_name("canvas", aspect),
            "end": asset_name("end", aspect) if end_headline(job) else None,
            "inset": inset_rect(ASPECTS[aspect]),
            "split": split_rects(aspect),
            "runs": {place: [list(r) for r in spans] for place, spans in runs(job).items()},
            "wipes": [{"at": at, "file": asset_name("wipe", aspect, number)} for at, number in wipes(job)],
            "beats": beats}


# ---- what the sheet, the pacing check, the timeline and the SFX layer see ----------

WIPE_SHEET_S = 0.25      # mid-sweep (the wipe starts 0.35 s before its card)
WIPE_CLEAR_S = 1.6       # the card is clear of the sweep and its trail


def sheet_moments(job):
    """Source seconds the contact sheet shows: each inset once its line is up, each graphic
    a beat after it cuts in (a trading card once the number has swept past, plus the sweep
    itself), each full beat a moment in."""
    out = []
    swept = {at for at, _ in wipes(job)}
    for beat in sorted_beats(job):
        lead = {"inset": TEXT_SHEET_S, "graphic": GRAPHIC_SHEET_S, "split": GRAPHIC_SHEET_S}.get(beat["layout"], 0.5)
        if beat["from"] in swept:
            lead = WIPE_CLEAR_S
            out.append(round(beat["from"] + WIPE_SHEET_S, 3))
        out.append(round(min(beat["from"] + lead, beat["to"] - 0.1), 3))
    return out


def visual_events(job):
    return sorted({t for b in sorted_beats(job) for t in (b["from"], b["to"])})


def chapter_marks(job):
    """A trading card opens a countdown item: (source seconds, "#3 Title")."""
    marks = []
    for beat in sorted_beats(job):
        g = beat.get("graphic") or {}
        if beat["layout"] in CARD_LAYOUTS and g.get("type") == "trading":
            title = " ".join(str(g["title"]).replace("|", " ").split())
            marks.append((beat["from"], f"#{g['number']} {title}"))
    return marks


def sfx(job):
    """(source seconds, kind): a whoosh where a chain starts (Tony leaves full frame), a pop
    on each later graphic and each punch line, an impact on the number one card, a riser
    into each number wipe."""
    raw = [(at - RISER_S, "riser") for at, _ in wipes(job)]
    for chain in chains(job):
        for i, beat in enumerate(chain):
            g = beat.get("graphic") or {}
            if g.get("type") == "trading" and str(g.get("number")).strip() == "1":
                raw.append((beat["from"], "impact"))
            elif i == 0:
                raw.append((beat["from"], "whoosh"))
            elif beat["layout"] in CARD_LAYOUTS:
                raw.append((beat["from"], "whoosh" if beat["from"] in {at for at, _ in wipes(job)} else "pop"))
            if has_text(beat):
                raw.append((beat["from"] + 0.15, "pop"))
    return raw
