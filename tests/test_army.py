"""Army format (theme army, docs/army.md): graphic shots drawn around FLUX pictures."""
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import army  # noqa: E402
import army_draw  # noqa: E402
import common  # noqa: E402
import gen_images  # noqa: E402

LAND, PORT = army.FINAL_LANDSCAPE, army.FINAL_PORTRAIT

GOOD = {
    "frame": ({"type": "frame", "text": "Your boss|won't tell you"}, "a quiet office at night"),
    "trading": ({"type": "trading", "number": 3, "of": 5, "title": "Claude Code",
                 "headline": "AI tools nobody shows you"}, "a laptop glowing in a dark room"),
    "words": ({"type": "words", "text": "A job in|their head"}, ""),
    "stamp": ({"type": "stamp", "text": "3 years"}, "an engineer standing, plain backdrop"),
    "agenda": ({"type": "agenda", "lines": ["What it does", "What it costs", "Who it is for"],
                "show": 2, "title": "In this video"}, ""),
    "tiles": ({"type": "tiles", "result": "Hired", "items": [
        {"prompt": "a", "label": "Learn"}, {"prompt": "b", "label": "Build"},
        {"prompt": "c", "label": "Ship"}]}, ""),
    "tree": ({"type": "tiles", "layout": "tree", "items": [
        {"prompt": "a", "label": "Claude"}, {"prompt": "b", "label": "Write"},
        {"prompt": "c", "label": "Code"}, {"prompt": "d", "label": "Research"}]}, ""),
}


def _pics(graphic, prompt):
    return [Image.new("RGB", size, (90 + 20 * i, 120, 160))
            for i, (_, _, size, _) in enumerate(army.pictures(graphic, prompt, (1280, 720)))]


@pytest.mark.parametrize("name", sorted(GOOD))
@pytest.mark.parametrize("size", [LAND, PORT])
def test_every_layout_renders_at_the_final_size(name, size):
    graphic, prompt = GOOD[name]
    army.validate(graphic, prompt)
    img = army.render(graphic, size, None, _pics(graphic, prompt), seed=3)
    assert img.size == size and img.mode == "RGB"


def test_rendering_is_deterministic_so_restage_redraws_the_same_frame():
    graphic, prompt = GOOD["trading"]
    a = army.render(graphic, LAND, None, _pics(graphic, prompt), seed=5)
    b = army.render(graphic, LAND, None, _pics(graphic, prompt), seed=5)
    assert a.tobytes() == b.tobytes()


def test_canvas_is_brokerage_navy():
    img = army.render(*[GOOD["words"][0], LAND], seed=1)
    r, g, b = img.resize((48, 27)).getpixel((2, 25))
    assert b > r and b > 25 and r < 30   # navy: blue dominant, dark


def test_army_style_overrides_the_palette():
    plain = army.render(GOOD["agenda"][0], LAND, seed=2)
    red = army.render(GOOD["agenda"][0], LAND, {"bg": "#5a0000", "bg_deep": "#200000"}, seed=2)
    r, _, b = red.resize((48, 27)).getpixel((24, 24))
    assert r > b and plain.tobytes() != red.tobytes()


def test_agenda_builds_line_by_line():
    graphic = GOOD["agenda"][0]
    one = army.render({**graphic, "show": 1}, LAND, seed=1)
    three = army.render({**graphic, "show": 3}, LAND, seed=1)
    assert one.tobytes() != three.tobytes()


def test_sibling_cards_appear_only_with_a_count():
    graphic, prompt = GOOD["trading"]
    pics = _pics(graphic, prompt)
    alone = {k: v for k, v in graphic.items() if k != "of"}
    assert army.render(graphic, LAND, None, pics, seed=1).tobytes() != \
        army.render(alone, LAND, None, pics, seed=1).tobytes()


def test_stamp_puts_the_subject_over_the_type():
    graphic, prompt = GOOD["stamp"]
    cut = Image.new("RGBA", (400, 800), (0, 0, 0, 0))
    ImageDraw.Draw(cut).rectangle([100, 0, 300, 800], fill=(255, 0, 0, 255))
    img = army.render(graphic, LAND, None, _pics(graphic, prompt), cutout=cut, seed=1)
    assert img.getpixel((LAND[0] // 2, LAND[1] // 3))[0] > 200   # red subject in front
    without = army.render(graphic, LAND, None, _pics(graphic, prompt), cutout=None, seed=1)
    assert without.size == LAND and without.tobytes() != img.tobytes()


@pytest.mark.parametrize("graphic,prompt", [
    ({"type": "poster"}, "x"),
    ({"type": "frame"}, ""),
    ({"type": "words"}, ""),
    ({"type": "stamp", "text": "3 years"}, ""),
    ({"type": "trading", "number": 2}, "x"),
    ({"type": "trading", "title": "No number"}, "x"),
    ({"type": "agenda", "lines": []}, ""),
    ({"type": "agenda", "lines": ["a", "b"], "show": 3}, ""),
    ({"type": "tiles", "items": [{"prompt": "a"}]}, ""),
    ({"type": "tiles", "items": [{"prompt": "a"}, {"label": "no prompt"}]}, ""),
    ({"type": "tiles", "layout": "tree", "items": [{"prompt": "a"}, {"prompt": "b"}]}, ""),
    ("frame", "x"),
])
def test_bad_graphics_are_rejected(graphic, prompt):
    with pytest.raises(ValueError):
        army.validate(graphic, prompt)


def test_pictures_split_shared_art_from_per_cut_backdrops():
    canvas = (1280, 720)
    assert army.pictures(*GOOD["frame"], canvas) == [("bg", GOOD["frame"][1], canvas, False)]
    assert army.pictures(*GOOD["trading"], canvas)[0][2:] == (army.CARD_PICTURE, True)
    assert [p[0] for p in army.pictures(*GOOD["tiles"], canvas)] == ["tile1", "tile2", "tile3"]
    assert army.pictures(*GOOD["words"], canvas) == []
    assert army.pictures(GOOD["words"][0], "a city at night", canvas)[0][3] is False
    assert army.pictures(*GOOD["agenda"], canvas) == []


def test_only_full_canvas_pictures_can_be_held_on():
    assert army.has_backdrop(*GOOD["frame"]) and army.has_backdrop(*GOOD["stamp"])
    assert not army.has_backdrop(*GOOD["trading"]) and not army.has_backdrop(*GOOD["agenda"])
    assert not army.has_backdrop(*GOOD["words"])
    assert army.has_backdrop(GOOD["words"][0], "a city at night")


def test_split_lines_honours_bars_and_never_splits_a_word():
    assert army_draw.split_lines("a job in|their head", 20) == ["A JOB IN", "THEIR HEAD"]
    lines = army_draw.split_lines("the extraordinarily long word stays whole", 8)
    assert "EXTRAORDINARILY" in lines and all(" " not in l or len(l) <= 8 for l in lines)


def _scenes(shots):
    return {"scenes": [{"id": i, "narration": "n", "caption": "c",
                        "shots": shots if i == 1 else ["a room"]} for i in (1, 2, 3)]}


def test_graphic_shots_validate_without_prompts_where_drawn():
    common.validate_scenes(_scenes([{"graphic": GOOD["words"][0]},
                                    {"graphic": GOOD["agenda"][0]},
                                    {"prompt": "a desk", "graphic": GOOD["frame"][0]}]))
    spec = common.shot_specs({"id": 1, "shots": [{"graphic": GOOD["words"][0]}]})[0]
    assert spec["graphic"]["type"] == "words"


@pytest.mark.parametrize("shot", [
    {"graphic": {"type": "frame"}},                                    # no prompt
    {"prompt": "x", "graphic": GOOD["frame"][0], "figure": {"pose": "stand"}},
    {"graphic": GOOD["words"][0], "hold": True},
])
def test_bad_graphic_shots_stop_validation(shot):
    with pytest.raises(SystemExit):
        common.validate_scenes(_scenes([{"prompt": "a room"}, shot]))


def test_a_hold_reaches_back_over_drawn_graphics(tmp_path):
    data = _scenes([{"prompt": "a desk", "graphic": GOOD["frame"][0]},
                    {"graphic": GOOD["agenda"][0]},
                    {"hold": True, "punch": 1.3}])
    holds = gen_images.hold_sources(data, tmp_path)
    assert holds[tmp_path / "scene_01_3.png"] == tmp_path / "bg" / "scene_01.png"


@pytest.fixture
def fake_flux(monkeypatch):
    calls = []

    def flux(cfg, theme, prompt, size, seed=None):
        calls.append((prompt, size))
        return Image.new("RGB", size, (100, 140, 180)), seed or 11, 0.5
    monkeypatch.setattr(gen_images, "flux_picture", flux)
    monkeypatch.setattr(gen_images, "subject_cutout", lambda path: None)
    return calls


CFG = {"IMG_W": "1280", "IMG_H": "720"}
CFG_P = {"IMG_W": "720", "IMG_H": "1280"}


def test_card_art_is_rendered_once_for_both_cuts(tmp_path, fake_flux):
    graphic, prompt = GOOD["trading"]
    spec = {"graphic": graphic, "prompt": prompt}
    gen_images.graphic_one(CFG, {}, spec, tmp_path / "scene_02.png", LAND)
    gen_images.graphic_one(CFG_P, {}, spec, tmp_path / "p_scene_02.png", PORT, regen="own")
    assert len(fake_flux) == 1
    assert Image.open(tmp_path / "p_scene_02.png").size == PORT


def test_a_frame_backdrop_is_per_cut_and_kept_for_holds(tmp_path, fake_flux):
    spec = {"graphic": GOOD["frame"][0], "prompt": GOOD["frame"][1]}
    gen_images.graphic_one(CFG, {}, spec, tmp_path / "scene_01.png", LAND)
    gen_images.graphic_one(CFG_P, {}, spec, tmp_path / "p_scene_01.png", PORT, regen="own")
    assert [size for _, size in fake_flux] == [(1280, 720), (720, 1280)]
    assert (tmp_path / "bg" / "scene_01.png").exists()
    assert (tmp_path / "bg" / "p_scene_01.png").exists()


def test_restage_mode_never_calls_flux(tmp_path, fake_flux):
    spec = {"graphic": GOOD["tiles"][0], "prompt": ""}
    out = tmp_path / "scene_03.png"
    assert gen_images.graphic_one(CFG, {}, spec, out, LAND, regen="none") is None
    gen_images.graphic_one(CFG, {}, spec, out, LAND)
    fake_flux.clear()
    edited = {"graphic": {**GOOD["tiles"][0], "headline": "New headline"}, "prompt": ""}
    assert gen_images.graphic_one(CFG, {}, edited, out, LAND, regen="none")
    assert fake_flux == []


def test_card_titles_split_into_two_even_lines_without_dropping_words():
    assert army_draw.balanced_lines("Calls write the follow-up") == ["CALLS WRITE", "THE FOLLOW-UP"]
    assert army_draw.balanced_lines("Claude Code") == ["CLAUDE CODE"]
    assert army_draw.balanced_lines("You|approve", single_up_to=7) == ["YOU", "APPROVE"]


def test_portrait_rewraps_long_punch_lines_and_keeps_their_accent():
    lines, marks = army._rewrap(["BEFORE YOU'RE", "BACK AT YOUR DESK"], {1}, 11)
    assert lines == ["BEFORE", "YOU'RE", "BACK AT", "YOUR DESK"] and marks == {2, 3}
    assert army._rewrap(["ONLY WHAT", "YOU FEED IT"], {1}, 11)[0] == ["ONLY WHAT", "YOU FEED IT"]


@pytest.mark.parametrize("name", ["frame", "words", "trading", "agenda", "tiles", "tree"])
def test_landscape_graphics_stay_above_the_caption_band(name):
    """The 16:9 caption box starts about 76% down; type and frames must end above it."""
    graphic, prompt = GOOD[name]
    img = army.render(graphic, LAND, None, _pics(graphic, prompt), seed=3)
    band = img.crop((0, round(LAND[1] * 0.77), LAND[0], LAND[1])).resize((480, 62))
    assert max(max(px) for px in band.getdata()) < 200
