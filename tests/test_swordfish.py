"""Stickman Swordfish (theme swordfish, docs/swordfish.md): doodle graphics on white,
figure outfits, shot overlays (tag, note), landscape-free captions, drift pacing and
shot timing weighted by each shot's line."""
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "characters" / "stickman"))

import assemble  # noqa: E402
import captions  # noqa: E402
import common  # noqa: E402
import composite  # noqa: E402
import doodle  # noqa: E402
import doodle_draw  # noqa: E402
import outfits  # noqa: E402

LAND, PORT = doodle.FINAL_LANDSCAPE, doodle.FINAL_PORTRAIT
FRAME = (1280, 720)

GOOD = {
    "icon": ({"type": "icon", "mark": "x", "label": "No bones"}, "a fish skeleton"),
    "icon_plain": ({"type": "icon"}, "a grilled steak on a plate"),
    "pair": ({"type": "pair", "join": "vs", "items": [
        {"prompt": "a", "mark": "check", "label": "Midwest"},
        {"prompt": "b", "mark": "x", "label": "California"}]}, ""),
    "pair_updown": ({"type": "pair", "join": "updown", "items": [
        {"prompt": "a", "label": "Cold"}, {"prompt": "b", "label": "Up to 15"}]}, ""),
    "chain": ({"type": "chain", "items": [
        {"prompt": "a", "label": "Rain"}, {"prompt": "b"}, {"prompt": "c", "label": "Plate"}]}, ""),
    "chain5": ({"type": "chain", "items": [{"prompt": p} for p in "abcde"]}, ""),
    "cycle": ({"type": "cycle", "items": [{"prompt": "a"}, {"prompt": "b"}, {"prompt": "c"}]}, ""),
    "bars": ({"type": "bars", "callout": "Dozens x", "bars": [
        {"label": "Sardine", "value": 1}, {"label": "Salmon", "value": 3},
        {"label": "Swordfish", "value": 40}]}, ""),
    "line": ({"type": "line", "points": [9, 8, 6, 3], "x_label": "Time",
              "y_label": "Performance", "notes": [{"at": 2, "text": "Memory"}],
              "circle": 4}, ""),
    "meter": ({"type": "meter", "value": 94, "tone": "good"}, "a small swordfish"),
    "meter_plain": ({"type": "meter", "value": 12, "tone": "bad", "text": "12 percent"}, ""),
    "words": ({"type": "words", "text": "Dozens|of times", "accent": 2}, ""),
}


def _pics(graphic, prompt):
    """Stand-ins for FLUX output: an off-white page with one coloured object on it."""
    pics = []
    for i, (_, _, size, _) in enumerate(doodle.pictures(graphic, prompt, FRAME)):
        pic = Image.new("RGB", size, (247, 247, 244))
        w, h = size
        ImageDraw.Draw(pic).ellipse([w * 0.3, h * 0.3, w * 0.7, h * 0.7],
                                    fill=(60 + 40 * i, 110, 170), outline=(15, 15, 15), width=6)
        pics.append(pic)
    return pics


def _render(name, size=LAND, seed=3):
    graphic, prompt = GOOD[name]
    return doodle.render(graphic, size, None, _pics(graphic, prompt), seed=seed)


# ---- doodle layouts ----------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(GOOD))
@pytest.mark.parametrize("size", [LAND, PORT])
def test_every_layout_renders_at_the_final_size(name, size):
    graphic, prompt = GOOD[name]
    doodle.validate(graphic, prompt)
    img = _render(name, size)
    assert img.size == size and img.mode == "RGB"


@pytest.mark.parametrize("name", sorted(GOOD))
def test_canvas_is_white_paper(name):
    img = _render(name)
    for corner in ((4, 4), (LAND[0] - 5, 4), (4, LAND[1] - 5), (LAND[0] - 5, LAND[1] - 5)):
        assert min(img.getpixel(corner)) >= 245


def test_rendering_is_deterministic_so_restage_redraws_the_same_frame():
    assert _render("bars", seed=5).tobytes() == _render("bars", seed=5).tobytes()
    assert _render("pair", seed=5).tobytes() == _render("pair", seed=5).tobytes()


def test_off_white_picture_background_blends_into_the_page():
    """FLUX's "white" comes back a shade off; pasted as is it shows as a grey box."""
    graphic, prompt = GOOD["icon_plain"]
    img = doodle.render(graphic, LAND, None, _pics(graphic, prompt), seed=1)
    grey = img.convert("L")
    assert grey.getextrema()[1] == 255
    # well inside the picture box but outside the drawn object: pure white
    assert grey.getpixel((LAND[0] // 2, round(LAND[1] * 0.09))) == 255


def test_whiten_clips_near_white_and_keeps_colour():
    pic = Image.new("RGB", (40, 20), (246, 245, 243))
    ImageDraw.Draw(pic).rectangle([20, 0, 39, 19], fill=(200, 40, 30))
    out = doodle_draw.whiten(pic)
    assert out.getpixel((5, 5)) == (255, 255, 255)
    assert out.getpixel((30, 10)) == (200, 40, 30)


def test_trim_finds_the_object_on_the_page():
    pic = Image.new("RGB", (400, 400), (255, 255, 255))
    ImageDraw.Draw(pic).rectangle([300, 40, 360, 120], fill=(0, 0, 0))
    left, top, right, bottom = doodle_draw.content_box(pic)
    assert 280 <= left <= 300 and 20 <= top <= 40 and 360 <= right <= 380 and 120 <= bottom <= 140


def test_label_is_drawn_under_the_picture():
    graphic, prompt = GOOD["icon"]
    pics = _pics(graphic, prompt)
    with_label = doodle.render(graphic, LAND, None, pics, seed=1)
    without = doodle.render({**graphic, "label": ""}, LAND, None, pics, seed=1)
    band = (0, round(LAND[1] * 0.75), LAND[0], LAND[1])
    assert with_label.crop(band).tobytes() != without.crop(band).tobytes()


@pytest.mark.parametrize("mark", doodle.MARKS)
def test_every_mark_changes_the_icon(mark):
    graphic, prompt = {"type": "icon", "mark": mark}, "a plate"
    pics = _pics(graphic, prompt)
    plain = doodle.render({"type": "icon"}, LAND, None, pics, seed=1)
    marked = doodle.render(graphic, LAND, None, pics, seed=1)
    assert plain.tobytes() != marked.tobytes()


def test_x_mark_is_red():
    img = _render("icon")
    reds = [p for p in img.resize((192, 108)).getdata() if p[0] > 180 and p[1] < 90 and p[2] < 90]
    assert len(reds) > 40


def test_bar_callout_and_values_change_the_chart():
    graphic = GOOD["bars"][0]
    base = doodle.render(graphic, LAND, seed=1)
    assert base.tobytes() != doodle.render({**graphic, "callout": ""}, LAND, seed=1).tobytes()
    taller = {**graphic, "bars": [{**b, "value": b["value"] * (3 if i == 0 else 1)}
                                  for i, b in enumerate(graphic["bars"])]}
    assert base.tobytes() != doodle.render(taller, LAND, seed=1).tobytes()


def test_meter_fill_follows_the_value():
    lo = doodle.render({"type": "meter", "value": 10}, LAND, seed=1)
    hi = doodle.render({"type": "meter", "value": 90}, LAND, seed=1)
    def green(img):
        return sum(1 for p in img.resize((192, 108)).getdata()
                   if p[1] > 130 and p[0] < 120 and p[2] < 120)
    assert green(hi) > green(lo) * 3


@pytest.mark.parametrize("name", sorted(GOOD))
def test_portrait_content_stays_above_the_platform_strip(name):
    img = _render(name, PORT)
    strip = img.crop((0, round(PORT[1] * doodle.PORTRAIT_SAFE) + 4, PORT[0], PORT[1]))
    assert min(strip.convert("L").getdata()) >= 245


@pytest.mark.parametrize("graphic,prompt", [
    ({"type": "poster"}, "x"),
    ({"type": "icon"}, ""),
    ({"type": "icon", "mark": "sparkle"}, "x"),
    ({"type": "icon", "label": "a label far too long to read on a card"}, "x"),
    ({"type": "pair", "items": [{"prompt": "a"}]}, ""),
    ({"type": "pair", "items": [{"prompt": "a"}, {"label": "no prompt"}]}, ""),
    ({"type": "pair", "join": "maybe", "items": [{"prompt": "a"}, {"prompt": "b"}]}, ""),
    ({"type": "chain", "items": [{"prompt": "a"}]}, ""),
    ({"type": "chain", "items": [{"prompt": p} for p in "abcdef"]}, ""),
    ({"type": "cycle", "items": [{"prompt": "a"}, {"prompt": "b"}]}, ""),
    ({"type": "bars", "bars": [{"label": "only", "value": 1}]}, ""),
    ({"type": "bars", "bars": [{"label": "a", "value": 0}, {"label": "b", "value": 0}]}, ""),
    ({"type": "bars", "bars": [{"label": "a", "value": -1}, {"label": "b", "value": 2}]}, ""),
    ({"type": "bars", "highlight": 4, "bars": [{"label": "a", "value": 1},
                                               {"label": "b", "value": 2}]}, ""),
    ({"type": "line", "points": [3]}, ""),
    ({"type": "line", "points": [3, 2], "circle": 3}, ""),
    ({"type": "line", "points": [3, 2], "notes": [{"at": 5, "text": "x"}]}, ""),
    ({"type": "meter", "value": 140}, ""),
    ({"type": "meter", "value": 50, "tone": "purple"}, ""),
    ({"type": "words"}, ""),
    ("icon", "x"),
])
def test_bad_graphics_are_rejected(graphic, prompt):
    with pytest.raises(ValueError):
        doodle.validate(graphic, prompt)


def test_pictures_are_isolated_objects_shared_by_both_cuts():
    icon = doodle.pictures(*GOOD["icon"], FRAME)
    assert len(icon) == 1
    name, prompt, size, shared = icon[0]
    assert name == "icon" and size == doodle.ICON_PICTURE and shared is True
    assert prompt.startswith("a fish skeleton") and "white background" in prompt
    assert [p[0] for p in doodle.pictures(*GOOD["pair"], FRAME)] == ["item1", "item2"]
    assert [p[0] for p in doodle.pictures(*GOOD["chain5"], FRAME)] == [f"item{i}" for i in range(1, 6)]
    assert doodle.pictures(*GOOD["bars"], FRAME) == []
    assert doodle.pictures(*GOOD["meter_plain"], FRAME) == []
    assert len(doodle.pictures(*GOOD["meter"], FRAME)) == 1


@pytest.mark.parametrize("name", sorted(GOOD))
def test_no_doodle_leaves_a_backdrop_to_hold_on(name):
    assert doodle.has_backdrop(*GOOD[name]) is False


# ---- overlays: date tags and corner notes on any shot --------------------------------

def test_tag_lands_in_the_top_right_and_note_in_the_top_left():
    base = Image.new("RGB", LAND, (90, 140, 200))
    tagged = doodle.overlay(base, tag="Jan 1998")
    noted = doodle.overlay(base, note="This video is for education only.")
    right = (LAND[0] // 2, 0, LAND[0], LAND[1] // 3)
    left = (0, 0, LAND[0] // 2, LAND[1] // 3)
    assert tagged.crop(right).tobytes() != base.crop(right).tobytes()
    assert tagged.crop(left).tobytes() == base.crop(left).tobytes()
    assert noted.crop(left).tobytes() != base.crop(left).tobytes()
    assert base.getpixel((5, 5)) == (90, 140, 200)        # original untouched
    assert doodle.overlay(base).tobytes() == base.tobytes()


def test_overlay_works_on_a_portrait_frame():
    base = Image.new("RGB", PORT, (255, 255, 255))
    out = doodle.overlay(base, tag="2005", note="Animations are illustrative.")
    assert out.size == PORT and out.tobytes() != base.tobytes()


@pytest.mark.parametrize("spec", [
    {"tag": "A date tag that is far too long"},
    {"tag": 1998},
    {"note": "x" * 400},
])
def test_bad_overlays_are_rejected(spec):
    with pytest.raises(ValueError):
        doodle.validate_overlays(spec)


# ---- theme wiring ------------------------------------------------------------------

def test_graphics_module_follows_the_theme():
    import army
    assert common.graphics_module({"graphics": "doodle"}) is doodle
    assert common.graphics_module({}) is army
    assert common.graphics_module("swordfish") is doodle
    assert common.graphics_module("army") is army


def test_swordfish_theme_sets_the_format():
    theme = common.load_theme("swordfish")
    assert theme["graphics"] == "doodle"
    assert theme["captions"] == "portrait"
    assert theme["pacing"] == "drift"
    assert theme["character"] == "stick-man" and theme["character_desc"]


def _scenes(theme, shots):
    return {"theme": theme, "scenes": [
        {"id": i, "narration": "Words here.", "caption": "Cap", "shots": shots}
        for i in (1, 2, 3)]}


def test_validate_scenes_checks_graphics_with_the_theme_module():
    first = {"prompt": "a kitchen", "figure": {"pose": "stand", "outfit": "chef"}}
    icon = {"prompt": "a steak", "graphic": {"type": "icon", "mark": "check"}, "tag": "2005"}
    common.validate_scenes(_scenes("swordfish", [first, icon]))
    trading = {"prompt": "x", "graphic": {"type": "trading", "number": 1, "title": "T"}}
    with pytest.raises(SystemExit):
        common.validate_scenes(_scenes("swordfish", [first, trading]))
    with pytest.raises(SystemExit):
        common.validate_scenes(_scenes("swordfish", [first, {"prompt": "x", "tag": 12}]))


def test_shot_specs_carry_tag_note_and_line():
    scene = {"shots": [{"prompt": "p", "tag": "2005", "note": "n", "line": "It sizzles."}, "q"]}
    specs = common.shot_specs(scene)
    assert (specs[0]["tag"], specs[0]["note"], specs[0]["line"]) == ("2005", "n", "It sizzles.")
    assert (specs[1]["tag"], specs[1]["note"], specs[1]["line"]) == (None, None, None)
    single = common.shot_specs({"image_prompt": "p", "tag": "1971"})
    assert single[0]["tag"] == "1971"


# ---- figure outfits ----------------------------------------------------------------

def _art(**spec):
    art, _ = composite.render_figure({"pose": "stand", **spec}, FRAME)
    return art


def test_the_outfit_library_has_the_starter_set():
    assert {"chef", "lab", "suit", "farmer", "builder", "glasses"} <= set(outfits.names())


@pytest.mark.parametrize("name", sorted(outfits.names()))
def test_every_outfit_changes_the_drawing(name):
    assert _art(outfit=name).tobytes() != _art().tobytes()


@pytest.mark.parametrize("name", sorted(outfits.names()))
def test_every_outfit_draws_flipped_and_with_a_prop(name):
    assert _art(outfit=name, flip=True, prop="phone", pose="hold").size[0] > 0


def test_outfits_combine_as_a_list():
    assert _art(outfit=["suit", "glasses"]).tobytes() != _art(outfit="suit").tobytes()


def test_unknown_outfit_is_rejected():
    with pytest.raises(ValueError):
        _art(outfit="tuxedo")
    with pytest.raises(ValueError):
        outfits.resolve(["chef", 3])


def test_white_coat_turns_the_torso_white():
    plain, coat = _art(), _art(outfit="lab")
    centre = (plain.width // 2 + 3, round(plain.height * 0.55))   # below the lapels
    assert sum(plain.getpixel(centre)[:3]) < 200
    assert sum(coat.getpixel(centre)[:3]) > 600


# ---- captions per cut, drift pacing, weighted shot timing ---------------------------

def test_blank_caption_is_fully_transparent(tmp_path):
    out = tmp_path / "cap.png"
    captions.caption_png("", out, 1920, 1080, {"size": 64})
    assert Image.open(out).getextrema()[3] == (0, 0)


@pytest.mark.parametrize("mode,landscape,portrait", [
    (None, "Cap", "Cap"), ("both", "Cap", "Cap"), ("portrait", "", "Cap"),
    ("landscape", "Cap", ""), ("none", "", "")])
def test_caption_text_per_cut(mode, landscape, portrait):
    theme = {} if mode is None else {"captions": mode}
    scene = {"caption": "Cap"}
    assert assemble.caption_text(scene, theme, vertical=False) == landscape
    assert assemble.caption_text(scene, theme, vertical=True) == portrait


def test_unknown_caption_mode_is_rejected():
    with pytest.raises(ValueError):
        assemble.caption_text({"caption": "x"}, {"captions": "sometimes"}, vertical=False)


def test_shot_durations_follow_each_shots_line():
    scene = {"shots": [{"prompt": "a", "line": "Two words."},
                       {"prompt": "b", "line": "Six words in this one here."}]}
    durs = assemble.shot_durations(scene, 8.0)
    assert durs == pytest.approx([2.0, 6.0])


def test_shot_durations_split_evenly_without_lines():
    assert assemble.shot_durations({"shots": ["a", {"prompt": "b", "line": "x y"}, "c"]}, 9.0) \
        == pytest.approx([3.0, 3.0, 3.0])
    assert assemble.shot_durations({"image_prompt": "a"}, 4.0) == pytest.approx([4.0])


def test_drift_moves_every_shot_and_alternates_direction():
    a = assemble.drift_filter(0, 1920, 1080, 75, 30)
    b = assemble.drift_filter(1, 1920, 1080, 75, 30)
    assert "zoompan" in a and ":d=75:" in a and "s=1920x1080" in a
    assert a != b


def test_drift_inputs_are_single_frames_and_cuts_inputs_loop():
    drift = assemble.still_inputs(["a.png", "b.png"], [2.0, 3.0], 30, "drift")
    cuts = assemble.still_inputs(["a.png", "b.png"], [2.0, 3.0], 30, "cuts")
    assert "-loop" not in drift and drift.count("-i") == 2
    assert cuts.count("-loop") == 2 and "3.000" in cuts


def test_drift_clip_renders_with_ffmpeg(tmp_path):
    for k, colour in enumerate(((240, 80, 60), (60, 120, 220)), 1):
        name = "scene_01.png" if k == 1 else f"scene_01_{k}.png"
        Image.new("RGB", (640, 360), colour).save(tmp_path / name)
    captions.caption_png("", tmp_path / "caption_01.png", 1920, 1080, {})
    scene = {"id": 1, "shots": [{"prompt": "a", "line": "one"}, {"prompt": "b", "line": "two three"}]}
    assemble.cuts_clip(tmp_path, scene, 1.5, 30, pacing="drift")
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", str(tmp_path / "clip_01.mp4")],
                         capture_output=True, text=True, check=True)
    assert float(out.stdout) == pytest.approx(1.5, abs=0.1)


def test_graphic_shots_never_trip_the_missing_character_warning():
    scenes = [{"id": 1, "shots": [
        {"prompt": "a house with the basement under the ground", "graphic": {"type": "icon"}},
        "a man walking past the house"]}]
    assert common.check_character_refs(scenes, "the main character") == \
        [(1, 2, "a man walking past the house")]


def test_chain_labels_share_one_baseline_on_16x9():
    """Objects of different heights still get their labels on one line."""
    graphic = {"type": "chain", "items": [{"prompt": "a", "label": "Freeze"},
                                          {"prompt": "b", "label": "Crack"}]}
    tall = Image.new("RGB", (768, 768), (255, 255, 255))
    ImageDraw.Draw(tall).rectangle([300, 100, 460, 660], fill=(40, 90, 160))
    flat = Image.new("RGB", (768, 768), (255, 255, 255))
    ImageDraw.Draw(flat).rectangle([100, 340, 660, 420], fill=(40, 90, 160))
    img = doodle.render(graphic, LAND, None, [tall, flat], seed=1)
    ink_rows = []
    for x0, x1 in ((0, LAND[0] // 2 - 60), (LAND[0] // 2 + 60, LAND[0])):
        band = img.crop((x0, LAND[1] // 2, x1, LAND[1])).convert("L")
        rows = [y for y in range(band.height)
                if min(band.crop((0, y, band.width, y + 1)).getdata()) < 60]
        ink_rows.append(rows[-1])
    assert abs(ink_rows[0] - ink_rows[1]) <= 4
