"""YouTube thumbnail: full-bleed subject photo, 2 to 4 words in two sizes, one accent
banner, the brand mark in the same corner every time (California Insider case,
2026-09-27), plus Tony cut out on the right when the block has a face (thumbnail review,
2026-10-19). These tests pin the text rules and the layout so nothing runs off canvas."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import common  # noqa: E402
import yt_thumb  # noqa: E402
import yt_thumb_face  # noqa: E402
import yt_thumb_layers  # noqa: E402


def person(size=(600, 900), color=(200, 60, 60)):
    """A stand-in cutout: head and shoulders on a transparent background."""
    cut = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(cut)
    w, h = size
    draw.ellipse([w * 0.3, h * 0.05, w * 0.7, h * 0.45], fill=color + (255,))
    draw.rectangle([w * 0.1, h * 0.45, w * 0.9, h], fill=color + (255,))
    return cut


def is_red(px):
    return px[0] > 150 and px[1] < 100 and px[2] < 100


# --- text rules -------------------------------------------------------------------

def test_word_count_in_range_has_no_warnings():
    assert yt_thumb.lint(["LA COUNTY", "RENT CAPPED"]) == []


def test_too_many_words_warns():
    warnings = yt_thumb.lint(["CALIFORNIA LANDLORDS NEED", "A WRITTEN PET POLICY NOW"])
    assert any("words" in w for w in warnings)


def test_five_words_warns():
    warnings = yt_thumb.lint(["HERMOSA", "AIRBNB BAN", "STRUCK DOWN"])
    assert any("5 words" in w for w in warnings)


def test_four_words_is_the_ceiling():
    assert yt_thumb.lint(["HERMOSA", "AIRBNB BAN", "GONE"]) == []


def test_long_banner_line_warns():
    warnings = yt_thumb.lint(["HERMOSA BEACH", "RENTAL BAN STRUCK DOWN"], accent=1)
    assert any("banner" in w for w in warnings)


def test_two_word_banner_is_fine():
    assert yt_thumb.lint(["HERMOSA", "AIRBNB BAN"], accent=1) == []


def test_bill_number_warns():
    warnings = yt_thumb.lint(["PET POLICY", "SB 1296"])
    assert any("bill number" in w for w in warnings)


def test_acronym_bill_forms_all_caught():
    for text in ("AB 1684", "SB1296", "ab-956"):
        assert yt_thumb.lint(["NEW RULE", text]), text


def test_normalize_uppercases_and_keeps_input_untouched():
    lines = ["your hoa", "can't say no"]
    assert yt_thumb.normalize(lines) == ["YOUR HOA", "CAN'T SAY NO"]
    assert lines == ["your hoa", "can't say no"]


# --- type -------------------------------------------------------------------------

def test_last_line_is_big_by_default():
    plan = yt_thumb.plan_sizes(["OGDENVILLE", "RENT CONTROL", "IS HERE"], accent=1)
    assert plan[-1] > plan[0]
    assert plan[0] == plan[1]


def test_anton_is_the_default_font():
    assert yt_thumb.DEFAULT_FONT == "anton"
    assert Path(yt_thumb.font(80).path).name == "Anton-Regular.ttf"
    assert Path(yt_thumb.font(80, "dejavu").path).name == "DejaVuSans-Bold.ttf"


def test_unknown_font_is_refused():
    with pytest.raises(ValueError):
        yt_thumb.font(80, "comic")


def test_anton_renders_bigger_lines_than_dejavu_in_the_same_column():
    bg = Image.new("RGB", (1920, 1088), (90, 120, 160))
    lines = ["HERMOSA BEACH", "AIRBNB BAN"]
    _, anton = yt_thumb.render(bg, lines, accent=1)
    _, dejavu = yt_thumb.render(bg, lines, accent=1, family="dejavu")
    for a, d in zip(anton, dejavu):
        assert a[3] - a[1] > d[3] - d[1]


# --- layout -----------------------------------------------------------------------

def test_cover_fit_fills_canvas_without_distortion():
    wide = Image.new("RGB", (2000, 800), "red")
    out = yt_thumb.cover(wide, (1280, 720))
    assert out.size == (1280, 720)


@pytest.mark.parametrize("family", ["anton", "dejavu"])
def test_render_fits_every_line_inside_text_column(family):
    bg = Image.new("RGB", (1920, 1088), (90, 120, 160))
    lines = ["UNINCORPORATED", "LA COUNTY RENTS", "CAPPED"]
    image, boxes = yt_thumb.render(bg, lines, accent=1, family=family)
    assert image.size == (1280, 720)
    for left, top, right, bottom in boxes:
        assert left >= 0 and right <= yt_thumb.TEXT_MAX_X
        assert top >= 0 and bottom <= yt_thumb.H


def test_render_rejects_bad_accent_index():
    bg = Image.new("RGB", (1280, 720))
    with pytest.raises(ValueError):
        yt_thumb.render(bg, ["ONE", "TWO"], accent=5)


def test_face_confines_text_to_the_left_55_percent():
    bg = Image.new("RGB", (1920, 1088), (90, 120, 160))
    image, boxes = yt_thumb.render(bg, ["HERMOSA BEACH", "AIRBNB BAN", "STRUCK DOWN"],
                                   accent=1, face=person())
    assert yt_thumb.FACE_TEXT_MAX_X == round(yt_thumb.W * 0.55)
    for left, top, right, bottom in boxes:
        assert right <= yt_thumb.FACE_TEXT_MAX_X


def test_face_lands_on_the_right():
    bg = Image.new("RGB", (1280, 720), (0, 0, 255))
    image, _ = yt_thumb.render(bg, ["LA COUNTY", "CAPPED"], accent=1, face=person())
    red = [x for x in range(0, yt_thumb.W, 8)
           if is_red(image.getpixel((x, 300)))]
    assert red, "the cutout never reached the canvas"
    assert min(red) > yt_thumb.W * 0.55


# --- the sticker look -------------------------------------------------------------

def test_sticker_adds_a_white_outline_and_a_soft_shadow():
    cut = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    ImageDraw.Draw(cut).rectangle([80, 80, 120, 120], fill=(200, 0, 0, 255))
    out = yt_thumb_face.sticker(cut, outline=10)
    ox, oy = out.width // 2, out.height // 2
    assert out.getpixel((ox, oy))[:3] == (200, 0, 0)
    assert out.getpixel((ox + 26, oy))[:3] == (255, 255, 255)        # outline ring
    shadow = out.getpixel((ox + 40, oy))
    assert 0 < shadow[3] < 255 and shadow[:3] == (0, 0, 0)            # shadow fades out


def test_sticker_keeps_the_outline_at_the_cutout_edge():
    cut = Image.new("RGBA", (100, 100), (200, 0, 0, 255))              # touches every edge
    out = yt_thumb_face.sticker(cut, outline=10)
    assert out.width > 100 + 20 and out.height > 100 + 20
    assert out.getpixel((out.width // 2, yt_thumb_face.pad_for(10) - 5))[:3] == (255, 255, 255)


def test_head_center_follows_the_top_of_the_cutout():
    cut = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    draw = ImageDraw.Draw(cut)
    draw.ellipse([250, 10, 330, 100], fill=(255, 0, 0, 255))           # head off to the right
    draw.rectangle([0, 100, 400, 400], fill=(255, 0, 0, 255))          # wide shoulders
    assert 280 <= yt_thumb_face.head_center_x(cut) <= 300


# --- getting the face -------------------------------------------------------------

def test_parse_face_reads_seconds_or_a_path():
    assert yt_thumb_face.parse_face(8.8) == 8.8
    assert yt_thumb_face.parse_face("8.8") == 8.8
    assert yt_thumb_face.parse_face("public/tony.png") == "public/tony.png"
    with pytest.raises(ValueError):
        yt_thumb_face.parse_face(-1)


def test_png_with_transparency_is_used_without_segmenting(tmp_path, monkeypatch):
    path = tmp_path / "tony.png"
    person().save(path)
    monkeypatch.setattr(yt_thumb_face, "cutout",
                        lambda *_: pytest.fail("segmented a ready cutout"))
    face = yt_thumb_face.load_face(str(path), base=tmp_path, footage=None, work=tmp_path)
    assert face.mode == "RGBA" and face.getbbox() is not None


def test_timestamp_grabs_the_footage_frame_then_cuts_it_out(tmp_path, monkeypatch):
    calls = {}

    def fake_grab(footage, seconds, dest):
        calls["grab"] = (footage, seconds)
        Image.new("RGB", (320, 180), "gray").save(dest)
        return dest

    monkeypatch.setattr(yt_thumb_face, "grab_frame", fake_grab)
    monkeypatch.setattr(yt_thumb_face, "cutout", lambda frame: person())
    footage = tmp_path / "public" / "footage.mp4"
    face = yt_thumb_face.load_face(8.8, base=tmp_path, footage=footage, work=tmp_path)
    assert calls["grab"] == (footage, 8.8)
    assert face.size == person().size


def test_no_cutout_tool_falls_back_to_a_framed_card(tmp_path, monkeypatch):
    monkeypatch.setattr(yt_thumb_face.vision, "subject_cutout", lambda src, dst: (False, "no tool"))
    frame = tmp_path / "frame.png"
    Image.new("RGB", (1600, 900), (10, 200, 10)).save(frame)
    assert yt_thumb_face.cutout(frame) is None
    face = yt_thumb_face.load_face(str(frame), base=tmp_path, footage=None, work=tmp_path)
    assert face.mode == "RGBA"
    assert face.height == 900 and face.width < face.height             # portrait card
    assert face.getpixel((face.width // 2, 450))[:3] == (10, 200, 10)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="needs ffmpeg")
def test_grab_frame_writes_a_png(tmp_path):
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "testsrc=size=320x180:rate=10:duration=2", str(clip)], check=True)
    out = yt_thumb_face.grab_frame(clip, 1.2, tmp_path / "frame.png")
    assert Image.open(out).size == (320, 180)


def test_grab_frame_past_the_end_is_an_error(tmp_path):
    if shutil.which("ffmpeg") is None:
        pytest.skip("needs ffmpeg")
    clip = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                    "testsrc=size=320x180:rate=10:duration=1", str(clip)], check=True)
    with pytest.raises(RuntimeError):
        yt_thumb_face.grab_frame(clip, 30, tmp_path / "frame.png")


# --- variants and the phone check -------------------------------------------------

def test_no_variants_means_one_thumbnail():
    block = {"lines": ["LA COUNTY", "CAPPED"], "accent": 1}
    assert yt_thumb.variant_blocks(block) == [("", block)]


def test_variants_override_the_base_block():
    block = {"lines": ["HERMOSA", "AIRBNB BAN", "GONE"], "accent": 1, "bg": "public/s.png",
             "variants": [{}, {"face": 8.8}, {"lines": ["HERMOSA", "NOW LEGAL?"]}]}
    out = yt_thumb.variant_blocks(block)
    assert [letter for letter, _ in out] == ["A", "B", "C"]
    assert all("variants" not in b for _, b in out)
    assert out[0][1]["lines"] == ["HERMOSA", "AIRBNB BAN", "GONE"]
    assert out[1][1]["face"] == 8.8 and out[1][1]["bg"] == "public/s.png"
    assert out[2][1]["lines"] == ["HERMOSA", "NOW LEGAL?"] and "face" not in out[2][1]
    assert block["variants"][0] == {}                                  # input untouched


def test_a_variant_must_be_an_object():
    with pytest.raises(ValueError):
        yt_thumb.variant_blocks({"lines": ["A", "B"], "variants": ["face"]})


def test_empty_cutout_png_is_refused(tmp_path):
    Image.new("RGBA", (50, 50), (0, 0, 0, 0)).save(tmp_path / "empty.png")
    with pytest.raises(RuntimeError):
        yt_thumb_face.load_face("empty.png", base=tmp_path, footage=None, work=tmp_path)


def test_more_than_three_variants_is_refused():
    block = {"lines": ["A", "B"], "variants": [{}, {}, {}, {}]}
    with pytest.raises(ValueError):
        yt_thumb.variant_blocks(block)


def test_phone_sheet_shows_each_thumbnail_at_360_and_168_wide():
    thumbs = [("A", Image.new("RGB", (1280, 720), "red")),
              ("B", Image.new("RGB", (1280, 720), "blue"))]
    sheet, slots = yt_thumb.phone_sheet(thumbs)
    assert len(slots) == 2
    for (big, small), color in zip(slots, [(255, 0, 0), (0, 0, 255)]):
        assert big[2] - big[0] == 360 and small[2] - small[0] == 168
        for left, top, right, bottom in (big, small):
            px = sheet.getpixel(((left + right) // 2, (top + bottom) // 2))
            assert all(abs(a - b) < 8 for a, b in zip(px, color))


def make_job(tmp_path, monkeypatch, block, name="job.json"):
    monkeypatch.setattr(common, "JOBS_DIR", tmp_path)
    jdir = tmp_path / "job1"
    (jdir / "public").mkdir(parents=True)
    (jdir / "out").mkdir()
    Image.new("RGB", (1920, 1088), (90, 120, 160)).save(jdir / "public" / "bg.png")
    person().save(jdir / "public" / "tony.png")
    data = {"thumbnail": block} if name == "job.json" else block
    (jdir / name).write_text(json.dumps(data))
    return jdir


def test_job_without_a_face_writes_one_thumbnail_and_the_phone_check(tmp_path, monkeypatch):
    jdir = make_job(tmp_path, monkeypatch,
                    {"lines": ["LA COUNTY", "CAPPED"], "accent": 1, "bg": "public/bg.png"})
    yt_thumb.from_job("job1")
    assert Image.open(jdir / "out" / "thumbnail.jpg").size == (1280, 720)
    assert (jdir / "out" / "thumb_variants" / "phone_sizes.jpg").exists()
    assert not (jdir / "out" / "thumb_variants" / "thumbnail_A.jpg").exists()


def test_job_with_a_face_writes_the_standard_a_b_c_set(tmp_path, monkeypatch):
    jdir = make_job(tmp_path, monkeypatch, {
        "lines": ["AI CHATS", "NOT PRIVATE"], "accent": 1, "bg": "public/bg.png",
        "face": "public/tony.png",
        "layers": [{"type": "stamp", "text": "EVIDENCE", "x": 250, "y": 470}],
        "plain": {"lines": ["YOUR CHATBOT", "ISN'T YOUR LAWYER"]}})
    yt_thumb.from_job("job1")
    sets = jdir / "out" / "thumb_variants"
    for letter in "ABC":
        assert Image.open(sets / f"thumbnail_{letter}.jpg").size == (1280, 720)
    assert (jdir / "out" / "thumbnail.jpg").read_bytes() == (sets / "thumbnail_A.jpg").read_bytes()
    assert Image.open(sets / "phone_sizes.jpg").height > 3 * 94


def test_rendering_leaves_hand_made_files_in_thumb_variants_alone(tmp_path, monkeypatch):
    jdir = make_job(tmp_path, monkeypatch,
                    {"lines": ["LA COUNTY", "CAPPED"], "accent": 1, "bg": "public/bg.png"})
    sets = jdir / "out" / "thumb_variants"
    sets.mkdir()
    (sets / "lawyer_A_face.jpg").write_bytes(b"hand made")
    (sets / "thumbnail_C.jpg").write_bytes(b"stale")
    yt_thumb.from_job("job1")
    assert (sets / "lawyer_A_face.jpg").read_bytes() == b"hand made"
    assert not (sets / "thumbnail_C.jpg").exists()


def test_thumbnail_json_works_for_jobs_without_job_json(tmp_path, monkeypatch):
    jdir = make_job(tmp_path, monkeypatch,
                    {"lines": ["LA COUNTY", "CAPPED"], "accent": 1, "bg": "public/bg.png"},
                    name="thumbnail.json")
    yt_thumb.from_job("job1")
    assert (jdir / "out" / "thumbnail.jpg").exists()


# --- the standard Test & compare set -----------------------------------------------

def test_a_face_block_becomes_face_same_layout_without_face_and_plain():
    block = {"lines": ["AI CHATS", "NOT PRIVATE"], "accent": 1, "bg": "work/bg.jpg",
             "mark": "TECH TONY", "face": 2.6, "face_height": 660, "text_y": 40,
             "layers": [{"type": "stamp", "text": "EVIDENCE"}],
             "plain": {"lines": ["YOUR CHATBOT", "ISN'T YOUR LAWYER"]}}
    (la, a), (lb, b), (lc, c) = yt_thumb.variant_blocks(block)
    assert (la, lb, lc) == ("A", "B", "C")
    assert a["face"] == 2.6 and a["layers"] == block["layers"]
    assert b["face"] is False                                         # face slot kept empty
    assert {k: v for k, v in b.items() if k != "face"} == {k: v for k, v in a.items() if k != "face"}
    assert "face" not in c and "layers" not in c and "text_y" not in c
    assert c["lines"] == ["YOUR CHATBOT", "ISN'T YOUR LAWYER"]
    assert c["mark"] == "TECH TONY" and c["bg"] == "work/bg.jpg"
    assert all("plain" not in v for _, v in [(la, a), (lb, b), (lc, c)])


def test_plain_defaults_to_the_same_words():
    out = yt_thumb.variant_blocks({"lines": ["HERMOSA", "AIRBNB BAN", "GONE"], "face": 8.8})
    assert out[2][1]["lines"] == ["HERMOSA", "AIRBNB BAN", "GONE"]


def test_face_false_keeps_the_face_layout_without_the_face():
    bg = Image.new("RGB", (1280, 720), (0, 0, 255))
    lines = ["HERMOSA BEACH", "AIRBNB BAN", "STRUCK DOWN"]
    with_face, boxes_a = yt_thumb.render(bg, lines, 1, face=person())
    without, boxes_b = yt_thumb.render(bg, lines, 1, face=False)
    assert boxes_a == boxes_b
    assert with_face.crop((0, 0, 500, 720)).tobytes() == without.crop((0, 0, 500, 720)).tobytes()
    assert not any(is_red(without.getpixel((x, 300))) for x in range(0, 1280, 8))


def test_text_y_puts_the_stack_where_asked():
    bg = Image.new("RGB", (1280, 720), (0, 0, 255))
    _, boxes = yt_thumb.render(bg, ["AI CHATS", "NOT PRIVATE"], 1, text_top=40)
    assert boxes[0][1] == 40


def test_face_height_sets_the_subject_size():
    canvas = Image.new("RGBA", (1280, 720), (0, 0, 255, 255))
    box = yt_thumb_face.place(canvas, person(), 660, 1024, 100)
    assert box[3] - box[1] == 660


def test_layers_are_drawn_above_the_face():
    bg = Image.new("RGB", (1280, 720), (0, 0, 255))
    layer = {"type": "stamp", "text": "EVIDENCE", "x": 900, "y": 500, "size": 90,
             "angle": 0, "color": "#00C800"}
    image, _ = yt_thumb.render(bg, ["LA COUNTY", "CAPPED"], 1, face=person(), layers=[layer])
    stamp = yt_thumb_layers.make_layer(layer, Path("."))
    border = image.getpixel((900 + 4, 500 + stamp.height // 2))          # over Tony's chest
    assert border[1] > 150 and border[0] < 100, border


# --- layers ------------------------------------------------------------------------

def test_stamp_is_a_rotated_bordered_word():
    flat = yt_thumb_layers.make_layer({"type": "stamp", "text": "EVIDENCE", "angle": 0}, Path("."))
    tilted = yt_thumb_layers.make_layer({"type": "stamp", "text": "EVIDENCE"}, Path("."))
    assert flat.width > flat.height
    assert tilted.height > flat.height                                   # default tilt


def test_chat_window_fits_its_message():
    card = yt_thumb_layers.make_layer(
        {"type": "chat", "text": "Here's what really happened in that meeting last week...",
         "width": 520, "angle": 0}, Path("."))
    assert card.width == 520 and card.mode == "RGBA"


def test_image_layer_scales_a_png_with_an_outline(tmp_path):
    person().save(tmp_path / "lease.png")
    out = yt_thumb_layers.make_layer({"type": "image", "path": "lease.png", "height": 300,
                                      "angle": 0}, tmp_path)
    assert out.height >= 300


def test_unknown_layer_type_is_refused():
    with pytest.raises(ValueError):
        yt_thumb_layers.make_layer({"type": "sparkle"}, Path("."))


def test_layers_hanging_off_the_canvas_are_clipped_not_refused():
    canvas = Image.new("RGBA", (1280, 720), (0, 0, 255, 255))
    yt_thumb_layers.draw_layers(canvas, [{"type": "stamp", "text": "NO", "x": -80, "y": 650}],
                                Path("."))


# --- the kit check -------------------------------------------------------------------

def test_kit_flags_a_missing_block(tmp_path):
    (tmp_path / "out").mkdir()
    assert any("thumbnail block" in p for p in yt_thumb.kit_problems(tmp_path, {}))


def test_kit_flags_a_block_without_a_face(tmp_path):
    problems = yt_thumb.kit_problems(tmp_path, {"lines": ["A", "B"]})
    assert any("face" in p for p in problems)


def test_kit_flags_an_unrendered_set_and_passes_a_rendered_one(tmp_path):
    block = {"lines": ["A", "B"], "face": 2.6}
    assert any("yt_thumb.py --job" in p for p in yt_thumb.kit_problems(tmp_path, block))
    sets = tmp_path / "out" / "thumb_variants"
    sets.mkdir(parents=True)
    for name in ("thumbnail_A.jpg", "thumbnail_B.jpg", "thumbnail_C.jpg", "phone_sizes.jpg"):
        (sets / name).write_bytes(b"x")
    assert yt_thumb.kit_problems(tmp_path, block) == []


def test_face_png_resolves_against_the_repo_for_the_pose_library(tmp_path, monkeypatch):
    lib = tmp_path / "repo" / "assets" / "faces"
    lib.mkdir(parents=True)
    person().save(lib / "stare.png")
    monkeypatch.setattr(yt_thumb_face.common, "ROOT", tmp_path / "repo")
    face = yt_thumb_face.load_face("assets/faces/stare.png", base=tmp_path / "job",
                                   footage=None, work=tmp_path)
    assert face.mode == "RGBA"


def test_faceless_finish_keeps_variant_a_as_the_thumbnail(tmp_path, monkeypatch):
    import thumbnail
    monkeypatch.setattr(common, "JOBS_DIR", tmp_path)
    sets = tmp_path / "job1" / "out" / "thumb_variants"
    sets.mkdir(parents=True)
    (sets / "thumbnail_A.jpg").write_bytes(b"A")
    (tmp_path / "job1" / "out" / "thumbnail.jpg").write_bytes(b"A")
    monkeypatch.setattr(thumbnail, "resolve", lambda *_: pytest.fail("redrew the thumbnail"))
    assert thumbnail.run("job1").read_bytes() == b"A"
