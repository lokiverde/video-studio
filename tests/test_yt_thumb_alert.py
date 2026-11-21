"""Alert style thumbnail: our own homeowner alert lower third (Brokerage navy headline bar,
light-blue label strip, EXAMPLE REALTY mark) over the subject photo, from the Epic Real
Estate breakdown (a breakdown note). Never a network lookalike. These tests
pin the copy rules, the bar geometry and how the style rides the A/B/C Test & compare set."""
import json
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import common  # noqa: E402
import yt_thumb  # noqa: E402

TORRANCE = ["NO RENT CONTROL IN TORRANCE", "STATE CAP STILL APPLIES"]


def person(size=(600, 900), color=(200, 60, 60)):
    """A stand-in cutout: head and shoulders on a transparent background."""
    cut = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(cut)
    w, h = size
    draw.ellipse([w * 0.3, h * 0.05, w * 0.7, h * 0.45], fill=color + (255,))
    draw.rectangle([w * 0.1, h * 0.45, w * 0.9, h], fill=color + (255,))
    return cut


def photo(color=(90, 120, 160)):
    return Image.new("RGB", (1920, 1088), color)


def near(px, hex_color, tol=10):
    target = tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return all(abs(a - b) <= tol for a, b in zip(px[:3], target))


def is_red(px):
    return px[0] > 150 and px[1] < 100 and px[2] < 100


# --- copy rules -------------------------------------------------------------------

def test_seven_word_headline_is_the_ceiling():
    assert yt_thumb.lint_alert(["FBI WARNING ABOUT FREE AND CLEAR HOMES"]) == []


def test_eight_words_warns():
    warnings = yt_thumb.lint_alert(["NO RENT CONTROL IN TORRANCE", "STATE CAP APPLIES NOW"])
    assert any("9 words" in w for w in warnings)


def test_two_words_is_too_thin_for_an_alert():
    assert any("2 words" in w for w in yt_thumb.lint_alert(["RENT CAPPED"]))


@pytest.mark.parametrize("label", ["EPIC NEWS ALERT", "FOX HOMEOWNER ALERT", "CNN ALERT",
                                   "NBC NEWS"])
def test_network_lookalike_label_warns(label):
    warnings = yt_thumb.lint_alert(["DEED THEFT TARGETS PAID OFF HOMES"], label)
    assert any("network" in w for w in warnings)


def test_default_label_is_our_own_and_clean():
    assert "NEWS" not in yt_thumb.ALERT_LABEL
    assert yt_thumb.lint_alert(TORRANCE[:1] + ["STATE CAP"], yt_thumb.ALERT_LABEL) == []


def test_bill_number_warns_in_an_alert_too():
    warnings = yt_thumb.lint_alert(["AB 1482 STILL CAPS YOUR RENT"])
    assert any("bill number" in w for w in warnings)


# --- layout -----------------------------------------------------------------------

def test_bar_spans_the_bottom_inside_the_canvas():
    image, boxes = yt_thumb.render_alert(photo(), TORRANCE)
    left, top, right, bottom = boxes["bar"]
    assert image.size == (yt_thumb.W, yt_thumb.H)
    assert left > 0 and right < yt_thumb.W and bottom < yt_thumb.H
    assert top > yt_thumb.H * 0.4, "the bar should leave the photo the top of the frame"
    assert right - left > yt_thumb.W * 0.9


def test_headline_lines_fit_inside_the_bar():
    _, boxes = yt_thumb.render_alert(photo(), TORRANCE)
    bl, bt, br, bb = boxes["bar"]
    assert len(boxes["lines"]) == 2
    for left, top, right, bottom in boxes["lines"]:
        assert bl < left and right < br and bt < top and bottom < bb


def test_label_strip_sits_on_the_bar_at_its_left_edge():
    _, boxes = yt_thumb.render_alert(photo(), TORRANCE)
    ll, lt, lr, lb = boxes["label"]
    bl, bt, _, _ = boxes["bar"]
    assert lb == bt and ll == bl and lt > 0 and lr > ll


def test_bar_is_brokerage_navy_and_the_label_is_light_blue():
    image, boxes = yt_thumb.render_alert(photo(), TORRANCE)
    _, _, br, bb = boxes["bar"]
    _, lt, lr, lb = boxes["label"]
    assert near(image.getpixel((br - 6, bb - 6)), yt_thumb.NAVY)
    assert near(image.getpixel((lr - 6, (lt + lb) // 2)), yt_thumb.LIGHT_BLUE)


def test_a_long_headline_shrinks_to_fit_one_line():
    _, boxes = yt_thumb.render_alert(photo(), ["CALIFORNIA PARENTS WITH PAID OFF HOMES"])
    bl, bt, br, bb = boxes["bar"]
    (left, _, right, _), = boxes["lines"]
    assert right < br
    assert bb - bt <= yt_thumb.ALERT_MAX_BAR_H


def test_two_lines_share_one_size():
    _, boxes = yt_thumb.render_alert(photo(), ["DEED THEFT", "TARGETS PAID OFF HOMES"])
    heights = [bottom - top for _, top, _, bottom in boxes["lines"]]
    assert abs(heights[0] - heights[1]) <= 4


def test_the_face_stands_behind_the_bar():
    image, boxes = yt_thumb.render_alert(photo((0, 0, 255)), TORRANCE, face=person())
    _, bar_top, _, bar_bottom = boxes["bar"]
    x = yt_thumb.FACE_CENTER_X
    assert is_red(image.getpixel((x, bar_top - 40))), "the face should show above the bar"
    assert near(image.getpixel((x, bar_bottom - 6)), yt_thumb.NAVY)


def test_the_whole_head_clears_the_bar_and_the_mark():
    """The classic face size (820) left only eyes and forehead above the bar."""
    image, boxes = yt_thumb.render_alert(photo((0, 0, 255)), TORRANCE, face=person())
    x = yt_thumb.FACE_CENTER_X
    red_rows = [y for y in range(0, boxes["bar"][1]) if is_red(image.getpixel((x, y)))]
    head_top = min(red_rows)
    head_bottom = yt_thumb.ALERT_FACE_TOP + 0.45 * yt_thumb.ALERT_FACE_HEIGHT   # person()'s chin
    assert head_top >= 70, "the head should clear the EXAMPLE REALTY mark"
    assert head_bottom < boxes["bar"][1], "the chin should land above the bar"


def test_more_than_two_headline_lines_is_refused():
    with pytest.raises(ValueError):
        yt_thumb.render_alert(photo(), ["ONE TWO", "THREE FOUR", "FIVE SIX"])


# --- the Test & compare set -------------------------------------------------------

def test_unknown_style_is_refused(tmp_path):
    photo().save(tmp_path / "bg.png")
    spec = {"style": "neon", "lines": TORRANCE, "bg": "bg.png"}
    with pytest.raises(ValueError):
        yt_thumb.build(spec, tmp_path / "t.jpg", tmp_path, tmp_path / "work")


def test_alert_face_block_without_plain_is_a_and_b_only():
    block = {"style": "alert", "lines": TORRANCE, "bg": "x.png", "face": 2.0}
    sets = yt_thumb.variant_blocks(block)
    assert [letter for letter, _ in sets] == ["A", "B"]
    assert sets[1][1]["face"] is False
    assert all(spec["style"] == "alert" for _, spec in sets)


def test_alert_plain_override_makes_a_classic_c():
    block = {"style": "alert", "lines": TORRANCE, "bg": "x.png", "face": 2.0,
             "plain": {"style": "classic", "lines": ["TORRANCE", "RENT CAPPED"], "accent": 1}}
    sets = dict(yt_thumb.variant_blocks(block))
    assert list(sets) == ["A", "B", "C"]
    assert sets["C"]["style"] == "classic" and "face" not in sets["C"]
    assert sets["A"]["style"] == "alert"


def test_kit_expects_two_files_for_an_alert_pair():
    block = {"style": "alert", "lines": TORRANCE, "bg": "x.png", "face": 2.0}
    assert yt_thumb.set_files(block) == ["thumbnail_A.jpg", "thumbnail_B.jpg",
                                         "phone_sizes.jpg"]


def make_job(tmp_path, monkeypatch, block):
    monkeypatch.setattr(common, "JOBS_DIR", tmp_path)
    jdir = tmp_path / "job1"
    (jdir / "public").mkdir(parents=True)
    (jdir / "out").mkdir()
    photo().save(jdir / "public" / "bg.png")
    person().save(jdir / "public" / "tony.png")
    (jdir / "job.json").write_text(json.dumps({"thumbnail": block}))
    return jdir


def test_job_renders_alert_a_b_and_classic_c(tmp_path, monkeypatch):
    jdir = make_job(tmp_path, monkeypatch, {
        "style": "alert", "lines": TORRANCE, "bg": "public/bg.png", "face": "public/tony.png",
        "plain": {"style": "classic", "lines": ["TORRANCE", "RENT CAPPED"], "accent": 1}})
    yt_thumb.from_job("job1")
    sets = jdir / "out" / "thumb_variants"
    for letter in "ABC":
        assert Image.open(sets / f"thumbnail_{letter}.jpg").size == (1280, 720)
    assert (sets / "thumbnail_A.jpg").read_bytes() != (sets / "thumbnail_B.jpg").read_bytes()
    assert (sets / "phone_sizes.jpg").exists()
    assert yt_thumb.kit_problems(jdir) == []


def test_alert_job_without_a_face_writes_one_thumbnail(tmp_path, monkeypatch):
    jdir = make_job(tmp_path, monkeypatch,
                    {"style": "alert", "lines": TORRANCE, "bg": "public/bg.png"})
    yt_thumb.from_job("job1")
    assert Image.open(jdir / "out" / "thumbnail.jpg").size == (1280, 720)
    assert not (jdir / "out" / "thumb_variants" / "thumbnail_A.jpg").exists()
