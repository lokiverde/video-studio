"""First-frame rules for Shorts (Tony, 2026-11-14: "my first frames all look the same").

In the Shorts feed frame 1 autoplays and decides the swipe; on the channel grid and in
search it is the thumbnail. So each Short can open on its own payoff (a number card, a
photo, a receipt) instead of the shared template, and `lint` flags the habits that make
every Short look alike."""
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import shorts_opener as so  # noqa: E402


def test_number_opener_is_a_full_frame_card(tmp_path):
    png = so.opener_png({"type": "number", "text": "100,000,000\nSQ FT", "sub": "PLANNED"},
                        tmp_path, tmp_path / "o.png", accent="#F97316")
    image = Image.open(png).convert("RGB")
    assert image.size == (so.W, so.H)
    assert image.getpixel((10, 10)) == so.hex_rgb(so.CARD_BG)
    assert any(image.getpixel((x, y)) == (255, 255, 255)
               for x in range(0, so.W, 6) for y in range(500, 1400, 6))      # the white number


def test_photo_opener_cover_crops_to_nine_by_sixteen(tmp_path):
    Image.new("RGB", (2000, 1000), "red").save(tmp_path / "wide.jpg")
    png = so.opener_png({"type": "photo", "image": "wide.jpg"}, tmp_path, tmp_path / "o.png")
    image = Image.open(png).convert("RGB")
    assert image.size == (so.W, so.H)
    r, g, b = image.getpixel((so.W // 2, so.H // 2))
    assert r > 200 and g < 40 and b < 40


def test_blur_fit_keeps_the_whole_photo(tmp_path):
    Image.new("RGB", (2000, 1000), "blue").save(tmp_path / "wide.jpg")
    png = so.opener_png({"type": "photo", "image": "wide.jpg", "fit": "blur"}, tmp_path, tmp_path / "o.png")
    assert Image.open(png).size == (so.W, so.H)


def test_tony_openers_need_no_card(tmp_path):
    for kind in ("location", "closeup"):
        assert so.opener_png({"type": kind}, tmp_path, tmp_path / "o.png") is None
    assert so.opener_png(None, tmp_path, tmp_path / "o.png") is None


def test_missing_image_or_unknown_type_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        so.opener_png({"type": "photo", "image": "nope.jpg"}, tmp_path, tmp_path / "o.png")
    with pytest.raises(ValueError, match="unknown opener type"):
        so.opener_png({"type": "gif"}, tmp_path, tmp_path / "o.png")
    with pytest.raises(ValueError, match="needs text"):
        so.opener_png({"type": "number"}, tmp_path, tmp_path / "o.png")


def test_opener_seconds_default_and_clamp():
    assert so.opener_seconds({"type": "number", "text": "X"}) == so.OPENER_SECONDS
    assert so.opener_seconds({"type": "number", "text": "X", "seconds": 9}) == so.MAX_OPENER_S
    assert so.opener_seconds({"type": "number", "text": "X", "seconds": 0.1}) == so.MIN_OPENER_S
    assert so.opener_seconds({"type": "location"}) == 0
    assert so.opener_seconds(None) == 0


def test_banner_follows_short_then_job_then_layout():
    assert so.banner_name({}, {}) == "default"
    assert so.banner_name({}, {"layout": "split"}) == "brokerage"
    assert so.banner_name({}, {"shorts_banner": "orange"}) == "orange"
    assert so.banner_name({"banner": "red"}, {"shorts_banner": "orange"}) == "red"


def test_a_card_that_carries_text_drops_the_banner():
    # the card is the hook; a banner on top would be two headlines in frame 1
    assert so.banner_name({"opener": {"type": "number", "text": "36 HOURS"}}, {}) == "none"
    assert so.banner_name({"opener": {"type": "photo", "image": "x.jpg"}}, {}) == "default"
    assert so.banner_name({"opener": {"type": "number", "text": "X"}, "banner": "red"}, {}) == "red"


def test_lint_flags_filler_starts_long_hooks_and_missing_openers():
    shorts = [{"start": "So the way it works", "end": "x", "hook": "ONE TWO THREE FOUR FIVE SIX SEVEN"}]
    warnings = " | ".join(m for _, m in so.lint(shorts))
    assert "lead-in" in warnings and "'so'" in warnings
    assert "7 words" in warnings
    assert "no opener" in warnings


def test_lint_flags_neighbors_that_open_the_same_way():
    card = {"type": "number", "text": "X"}
    shorts = [{"start": "Railroads were", "end": "x", "hook": "A", "opener": card},
              {"start": "Space is cold", "end": "x", "hook": "B", "opener": card},
              {"start": "My AI", "end": "x", "hook": "C", "opener": {"type": "location"}}]
    hits = [(n, m) for n, m in so.lint(shorts) if "same way" in m]
    assert hits == [(2, "opens the same way as #1 (number): rotate the opener type")]


def test_clean_shorts_pass_lint():
    shorts = [{"start": "Railroads were", "end": "x", "hook": "63% OF THE MARKET",
               "opener": {"type": "archive", "image": "a.jpg"}},
              {"start": "Space is cold", "end": "x", "hook": "",
               "opener": {"type": "number", "text": "4 COURTS"}}]
    assert so.lint(shorts) == []


def test_cover_name():
    assert so.cover_name(3) == "short_3_cover.jpg"


def test_words_on_a_photo_sit_on_a_dark_band(tmp_path):
    Image.new("RGB", (1080, 1920), (240, 240, 240)).save(tmp_path / "white.jpg")
    png = so.opener_png({"type": "photo", "image": "white.jpg", "text": "1900"}, tmp_path, tmp_path / "o.png")
    image = Image.open(png).convert("RGB")
    assert image.getpixel((8, so.CENTER_Y))[0] < 140        # shaded behind the words, edge to edge
    assert image.getpixel((8, 100)) == (240, 240, 240)      # the rest of the photo untouched
