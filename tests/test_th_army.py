"""Army style for the talking-head wrapper (docs/army.md, "With Tony on camera"): Tony's
own footage on the Brokerage navy canvas, full frame, in the frame box with a punch line
under him, or cut away to a full-screen Army graphic while his audio plays. Beats are
written in SOURCE seconds and name their layout; these tests pin down validation, the
runs Tony stays in the box for, and what the sheet, timeline and SFX layer see."""
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import army  # noqa: E402
import common  # noqa: E402
import gen_images  # noqa: E402
import th_army  # noqa: E402
import th_army_build  # noqa: E402
import th_lib  # noqa: E402

CARD = {"type": "trading", "number": 5, "of": 5, "title": "The cost", "headline": "Why they came back"}


def beat(layout, start, end, **extra):
    return {"from": start, "to": end, "layout": layout, **extra}


def army_job(beats=None, **extra):
    job = {"title": "t", "source": "footage.mp4", "srcEnd": 90.0, "cuts": [[30.0, 32.0]], "style": "army",
           "sections": [], "endCard": {"seconds": 2.5, "headline": "Take the quiz"},
           "beats": beats if beats is not None else [
               beat("full", 0.0, 6.0),
               beat("inset", 6.0, 10.0, text="1,757|comments", accent=[2]),
               beat("graphic", 10.0, 13.0, graphic={"type": "agenda", "lines": ["a", "b"], "show": 1}),
               beat("inset", 13.0, 17.0, text="Same five reasons"),
               beat("graphic", 40.0, 43.0, graphic=CARD, prompt="a moving truck on a highway"),
               beat("graphic", 43.0, 46.0, graphic={"type": "words", "text": "Big|mistake"}),
           ]}
    return {**job, **extra}


# ---- validation -------------------------------------------------------------------

def test_a_clean_army_job_validates():
    assert th_lib.validate(army_job()) == []


def test_a_beat_can_hold_across_a_jump_cut():
    job = army_job([beat("split", 26.0, 36.0, graphic={"type": "words", "text": "Holds|through"})])
    assert th_lib.validate(job) == []


def test_beats_need_the_army_style():
    problems = th_lib.validate(army_job(style="studio"))
    assert any("set style to 'army'" in p for p in problems)


def test_army_jobs_use_beats_not_sections():
    job = army_job(sections=[{"evidence": [1.0, 4.0], "blocks": []}])
    assert any("beats, not sections" in p for p in th_lib.validate(job))


@pytest.mark.parametrize("bad, words", [
    (beat("sideways", 1.0, 3.0), "layout 'sideways' unknown"),
    (beat("inset", 29.0, 31.0, text="x"), "starts or ends inside a cut"),
    (beat("inset", 31.0, 34.0, text="x"), "starts or ends inside a cut"),
    (beat("inset", 80.0, 95.0, text="x"), "bad range"),
    (beat("inset", 50.0, 50.3, text="x"), "too short"),
    (beat("full", 50.0, 52.0, text="hello"), "text only shows on inset beats"),
    (beat("inset", 50.0, 52.0, graphic={"type": "words", "text": "x"}), "set layout to 'split' or 'graphic'"),
    (beat("split", 50.0, 52.0, text="hello", graphic={"type": "words", "text": "x"}), "a split beat takes a 'words' graphic"),
    (beat("split", 50.0, 52.0), "graphic must be an object"),
    (beat("graphic", 50.0, 52.0, graphic={"type": "trading", "number": 3}, prompt="p"), "needs a 'number' and a 'title'"),
    (beat("graphic", 50.0, 52.0, graphic={"type": "frame"}), "needs a 'prompt'"),
    (beat("inset", 50.0, 52.0, text="x", accent=["two"]), "accent is a line number"),
])
def test_bad_beats_are_named_in_plain_words(bad, words):
    problems = th_lib.validate(army_job([bad]))
    assert any(words in p for p in problems), problems


def test_overlapping_beats_are_rejected():
    job = army_job([beat("inset", 1.0, 5.0, text="a"), beat("graphic", 4.0, 7.0, graphic={"type": "words", "text": "b"})])
    assert any("overlap" in p for p in th_lib.validate(job))


def test_army_is_a_known_style_and_punches_at_cuts():
    assert th_lib.punch_boundaries(army_job()) == [32.0]


# ---- inset runs --------------------------------------------------------------------

def test_insets_joined_by_a_graphic_are_one_run():
    # 6-10 inset, 10-13 agenda, 13-17 inset: Tony stays in the box behind the agenda
    assert th_army.inset_runs(army_job()) == [(6.0, 17.0)]


def test_a_full_beat_or_a_long_gap_ends_a_run():
    job = army_job([beat("inset", 1.0, 4.0, text="a"), beat("full", 4.0, 4.5), beat("inset", 4.5, 8.0, text="b"),
                    beat("inset", 20.0, 24.0, text="c")])
    assert th_army.inset_runs(job) == [(1.0, 4.0), (4.5, 8.0), (20.0, 24.0)]


def test_a_short_gap_keeps_the_run_going():
    job = army_job([beat("inset", 1.0, 4.0, text="a"), beat("inset", 4.6, 8.0, text="b")])
    assert th_army.inset_runs(job) == [(1.0, 8.0)]


def test_a_cut_between_two_insets_makes_them_one_run():
    job = army_job([beat("inset", 25.0, 30.0, text="a"), beat("inset", 32.0, 36.0, text="b")])
    assert th_army.inset_runs(job) == [(25.0, 36.0)]     # the 30-32 cut joins them


def test_after_a_graphic_tony_is_already_in_the_box():
    job = army_job([beat("graphic", 1.0, 4.0, graphic={"type": "words", "text": "x"}), beat("inset", 4.0, 8.0, text="b"),
                    beat("graphic", 8.0, 10.0, graphic={"type": "words", "text": "y"})])
    # starts with the graphic (he shrinks behind it), ends with the inset (he grows back behind the next one)
    assert th_army.inset_runs(job) == [(1.0, 8.0)]


def test_graphics_alone_never_move_tony():
    job = army_job([beat("graphic", 1.0, 4.0, graphic={"type": "words", "text": "x"})])
    assert th_army.inset_runs(job) == []


# ---- split, the main layout --------------------------------------------------------

WORDS = {"type": "words", "text": "Same five|reasons"}
SPLIT_CARD = {**CARD, "type": "trading"}


def split_job(beats=None, **extra):
    return army_job(beats if beats is not None else [
        beat("full", 0.0, 5.0),
        beat("split", 5.0, 9.0, graphic=WORDS),
        beat("split", 9.0, 12.0, graphic=SPLIT_CARD, prompt="a calculator on a table"),
        beat("graphic", 12.0, 14.0, graphic={"type": "words", "text": "Big|mistake"}),
        beat("split", 14.0, 18.0, graphic=WORDS),
        beat("inset", 18.0, 22.0, text="Came back"),
    ], **extra)


def test_split_beats_validate():
    assert th_lib.validate(split_job()) == []


def test_tony_holds_his_panel_across_a_full_screen_graphic():
    places = th_army.runs(split_job())
    assert places["split"] == [(5.0, 18.0)]       # the 12-14 graphic hides him, he stays put
    assert places["inset"] == [(18.0, 22.0)]      # then moves straight from panel to box


def test_a_graphic_takes_the_place_of_the_beat_after_it():
    job = split_job([beat("inset", 1.0, 4.0, text="a"), beat("graphic", 4.0, 6.0, graphic=WORDS),
                     beat("split", 6.0, 9.0, graphic=WORDS)])
    assert th_army.runs(job) == {"inset": [(1.0, 4.0)], "split": [(4.0, 9.0)]}


def test_a_trading_card_beside_tony_gets_a_number_wipe():
    assert th_army.wipes(split_job()) == [(9.0, "5")]
    assert th_army.wipes(split_job(wipe=False)) == []
    assert th_army.wipes(army_job()) == []        # full-screen cards carry their own number


def test_split_props_carry_the_card_tony_and_the_wipe():
    props = th_army.render_props(split_job(), portrait=False)
    card, tony = props["split"]["card"], props["split"]["tony"]
    assert card["x"] + card["w"] < tony["x"]                  # card left, Tony right, no overlap
    assert tony["x"] + tony["w"] <= 1920 and card["h"] == tony["h"]
    assert props["split"]["caption"]["y"] > card["y"] + card["h"] * 0.74   # under the graphic
    assert props["wipes"] == [{"at": 9.0, "file": "army/wipe_5.png"}]
    assert props["beats"][2]["file"] == "army/beat03_16x9.png"
    assert "army/wipe_5.png" in th_army.asset_files(split_job(), "16x9")


def test_portrait_split_puts_the_card_on_top_clear_of_the_platform_ui():
    rects = th_army.split_rects("9x16")
    card, tony = rects["card"], rects["tony"]
    assert card["y"] >= 200 and card["y"] + card["h"] < tony["y"]
    assert tony["y"] + tony["h"] <= 1920 - 340


def test_the_sheet_shows_the_wipe_and_then_the_card():
    moments = th_lib.sheet_moments(split_job())
    assert 9.25 in moments and 10.6 in moments


def test_sfx_rise_into_the_wipe_and_whoosh_on_the_card():
    raw = th_army.sfx(split_job())
    assert (9.0 - th_army.RISER_S, "riser") in raw and (9.0, "whoosh") in raw


# ---- screen recordings in the card ---------------------------------------------------

def clip_beat(**extra):
    return {**beat("split", 5.0, 9.0, clip="claude-incognito.mp4"), **extra}


def test_a_split_beat_can_play_a_screen_recording_with_a_label():
    job = split_job([clip_beat(text="Claude|ghost icon", start=4.5, focus=[0.5, 0.3], zoom=1.2)])
    assert th_lib.validate(job) == []
    assert "claude-incognito.mp4" in th_lib.job_files(job)
    item = th_army.render_props(job, portrait=True)["beats"][0]
    assert item["kind"] == "clip" and item["clip"] == "claude-incognito.mp4"
    assert (item["start"], item["zoom"], item["focus"]) == (4.5, 1.2, [0.5, 0.3])
    assert item["file"] == "army/beat01_9x16.png" and "textFile" not in item
    win = item["window"]
    card_w, card_h = th_army.card_size("9x16")
    assert win["x"] >= card_w / 2 and win["y"] + win["h"] < card_h * th_army.CAPTION_BAND


def test_an_unlabeled_clip_is_centred_in_the_card():
    job = split_job([clip_beat()])
    win = th_army.render_props(job, portrait=False)["beats"][0]["window"]
    assert abs(win["x"] + win["w"] / 2 - th_army.card_size("16x9")[0] / 2) <= 1


@pytest.mark.parametrize("portrait", [False, True])
def test_a_wide_clip_gets_a_window_the_shape_of_the_recording(portrait):
    job = split_job([clip_beat(wide=1.5)])
    assert th_lib.validate(job) == []
    win = th_army.render_props(job, portrait=portrait)["beats"][0]["window"]
    card_w, card_h = th_army.card_size("9x16" if portrait else "16x9")
    assert abs(win["w"] / win["h"] - 1.5) < 0.01              # a laptop screen, not a tall crop
    assert win["w"] > card_w * 0.85                             # it takes the card's width
    assert win["y"] + win["h"] < card_h * th_army.CAPTION_BAND


def test_a_wide_clip_label_runs_above_the_window():
    job = split_job([clip_beat(wide=1.5, text="Turn this|off")])
    (wx0, wy0, wx1, wy1), label = th_army.clip_boxes(th_army.card_size("16x9"), True, wide=1.5)
    assert label is not None and label[3] <= wy0
    assert th_army.render_props(job, portrait=False)["beats"][0]["window"]["y"] == round(wy0)


@pytest.mark.parametrize("extra, words", [
    ({"graphic": WORDS}, "a clip or a graphic, not both"),
    ({"rate": 9}, "clip rate"),
    ({"start": -1}, "clip start"),
    ({"zoom": 0.5}, "clip zoom"),
    ({"focus": [0.5, 2]}, "clip focus"),
    ({"wide": 0.5}, "clip wide"),
    ({"wide": "yes"}, "clip wide"),
])
def test_bad_clips_are_named(extra, words):
    problems = th_lib.validate(split_job([clip_beat(**extra)]))
    assert any(words in p for p in problems), problems


def test_clips_only_play_in_split_beats():
    job = split_job([beat("inset", 5.0, 9.0, text="x", clip="a.mp4")])
    assert any("only plays in a split beat" in p for p in th_lib.validate(job))


def test_a_clip_card_has_its_label_left_and_a_plate_for_the_recording(built, monkeypatch):
    jdir, calls = built
    monkeypatch.setattr(th_army_build, "_check_clips", lambda jdir, job: None)
    th_army_build.build("j", split_job([clip_beat(text="Claude|ghost icon")]))
    card = Image.open(jdir / "public" / "army" / "beat01_16x9.png").convert("RGB")
    assert card.size == th_army.card_size("16x9") and calls == []
    (x0, y0, x1, y1), _ = th_army.clip_boxes(card.size, True)
    plate = card.getpixel((round((x0 + x1) / 2), round((y0 + y1) / 2)))
    assert plate == (0, 18, 31)                            # bg_deep, where the recording plays
    left = card.crop((0, 0, round(card.width * 0.47), card.height)).convert("L")
    assert left.getextrema()[1] > 240                      # white Anton in the label column


def test_a_clip_too_short_for_its_beat_stops_the_sheet(tmp_path, monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, "3.0\n", ""))
    with pytest.raises(SystemExit):
        th_army_build._check_clips(tmp_path, split_job([clip_beat(start=1.0)]))


# ---- article shots in the card -----------------------------------------------------

def shot_beat(**extra):
    return {**beat("split", 5.0, 9.0, shot="snaps/holding.png"), **extra}


def test_a_split_beat_can_show_an_article_shot():
    job = split_job([shot_beat(text="Chats with Claude:|not privileged", crop=[0, 0, 400, 120],
                               highlight=[[10, 40, 300, 70]])])
    assert th_lib.validate(job) == []
    assert "snaps/holding.png" in th_lib.job_files(job)
    item = th_army.render_props(job, portrait=False)["beats"][0]
    assert item == {"from": 5.0, "to": 9.0, "layout": "split", "file": "army/beat01_16x9.png", "kind": "shot"}
    assert th_army.wipes(job) == []


@pytest.mark.parametrize("extra, words", [
    ({"graphic": WORDS}, "a shot or a graphic, not both"),
    ({"clip": "a.mp4"}, "a clip or a shot, not both"),
    ({"crop": [10, 10, 5, 50]}, "crop"),
    ({"highlight": [[0, 0, 10]]}, "highlight box"),
    ({"portraitShot": " "}, "portraitShot"),
    ({"portraitHighlight": [[5, 0, 1, 9]]}, "portraitHighlight box"),
])
def test_bad_shots_are_named(extra, words):
    problems = th_lib.validate(split_job([shot_beat(**extra)]))
    assert any(words in p for p in problems), problems


def test_a_shot_card_crops_highlights_and_labels(built):
    jdir, calls = built
    (jdir / "public" / "snaps").mkdir(parents=True)
    Image.new("RGB", (400, 200), (255, 255, 255)).save(jdir / "public" / "snaps" / "holding.png")
    th_army_build.build("j", split_job([shot_beat(text="Not|privileged", crop=[0, 0, 400, 100],
                                                  portraitCrop=[0, 0, 200, 100], highlight=[[0, 0, 400, 100]])]))
    for aspect, crop_aspect in (("16x9", 4.0), ("9x16", 2.0)):
        card = Image.open(jdir / "public" / "army" / f"beat01_{aspect}.png").convert("RGB")
        assert card.size == th_army.card_size(aspect) and calls == []
        (x0, y0, x1, y1), (lx0, ly0, lx1, ly1) = th_army.shot_layout(card.size, True, crop_aspect)
        assert card.getpixel((round((x0 + x1) / 2), round((y0 + y1) / 2))) == army_draw_rgb("#9fe3fb")
        label = card.crop((round(lx0), round(ly0), round(lx1), round(ly1))).convert("L")
        assert label.getextrema()[1] > 240                 # white Anton above the shot
        assert y1 < card.height * th_army.CAPTION_BAND     # clear of the captions


def test_a_portrait_shot_replaces_the_snapshot_in_the_9x16_card(built):
    jdir, calls = built
    snaps = jdir / "public" / "snaps"
    snaps.mkdir(parents=True)
    Image.new("RGB", (400, 100), (255, 255, 255)).save(snaps / "holding.png")
    Image.new("RGB", (200, 100), (255, 255, 255)).save(snaps / "holding_9x16.png")
    th_army_build.build("j", split_job([shot_beat(crop=[0, 0, 400, 100], highlight=[[0, 0, 400, 100]],
                                                  portraitShot="snaps/holding_9x16.png",
                                                  portraitHighlight=[[0, 0, 100, 100]])]))
    hi, white = army_draw_rgb("#9fe3fb"), (255, 255, 255)
    for aspect, crop_aspect, left, right in (("16x9", 4.0, hi, hi), ("9x16", 2.0, hi, white)):
        card = Image.open(jdir / "public" / "army" / f"beat01_{aspect}.png").convert("RGB")
        (x0, y0, x1, y1), _ = th_army.shot_layout(card.size, False, crop_aspect)
        mid = round((y0 + y1) / 2)
        assert card.getpixel((round(x0 + (x1 - x0) * 0.25), mid)) == left
        assert card.getpixel((round(x0 + (x1 - x0) * 0.75), mid)) == right


def test_a_portrait_shot_is_read_from_public_and_ignores_the_wide_crop():
    b = shot_beat(crop=[0, 0, 400, 100], portraitShot="snaps/holding_9x16.png")
    assert th_lib.job_files(split_job([b]))[-2:] == ["snaps/holding.png", "snaps/holding_9x16.png"]
    assert th_army.shot_image(b, portrait=True) == "snaps/holding_9x16.png"
    assert th_army.shot_image(b, portrait=False) == "snaps/holding.png"
    assert th_army.shot_crop(b, portrait=True) is None
    assert th_army.shot_crop({**b, "portraitCrop": [0, 0, 50, 20]}, portrait=True) == [0, 0, 50, 20]
    assert th_army.shot_crop(b, portrait=False) == [0, 0, 400, 100]


def test_a_wide_shot_fills_the_card_width_and_its_label_sits_right_above():
    (x0, y0, x1, y1), (lx0, ly0, lx1, ly1) = th_army.shot_layout((1212, 992), True, 9.0)
    assert x1 - x0 > 1212 * 0.9 and ly1 < y0 < ly1 + 992 * 0.05


def army_draw_rgb(hex_color):
    import army_draw
    return army_draw.rgb(hex_color)


def logo_card_beat(**extra):
    return {**beat("split", 9.0, 12.0, graphic=SPLIT_CARD, image="logos/a.png"), **extra}


def test_a_trading_card_can_show_a_logo_instead_of_a_picture():
    job = split_job([logo_card_beat()])
    assert th_lib.validate(job) == []
    assert "logos/a.png" in th_lib.job_files(job)
    assert th_army.card_images(logo_card_beat(image=["logos/a.png", "logos/b.png"])) == ["logos/a.png", "logos/b.png"]


@pytest.mark.parametrize("extra, words", [
    ({"graphic": WORDS}, "only replaces a trading card's picture"),
    ({"image": ["a.png", "b.png", "c.png"]}, "one or two files"),
    ({"image": " "}, "one or two files"),
])
def test_bad_card_images_are_named(extra, words):
    problems = th_lib.validate(split_job([logo_card_beat(**extra)]))
    assert any(words in p for p in problems), problems


def test_a_logo_card_draws_the_files_unaltered_without_flux(built):
    jdir, calls = built
    (jdir / "public" / "logos").mkdir(parents=True)
    Image.new("RGBA", (100, 100), (230, 20, 20, 255)).save(jdir / "public" / "logos" / "a.png")
    Image.new("RGBA", (100, 100), (20, 200, 60, 255)).save(jdir / "public" / "logos" / "b.png")
    th_army_build.build("j", split_job([logo_card_beat(image=["logos/a.png", "logos/b.png"])]))
    assert calls == []
    for aspect in ("16x9", "9x16"):
        card = Image.open(jdir / "public" / "army" / f"beat01_{aspect}.png").convert("RGB")
        colors = {c for _, c in card.getcolors(card.width * card.height)}
        assert (230, 20, 20) in colors and (20, 200, 60) in colors   # both logos, colors kept


# ---- what the template gets -------------------------------------------------------

def test_the_inset_is_the_army_frame_box():
    rect = th_army.inset_rect((1920, 1080))
    assert (rect["x"], rect["y"], rect["w"], rect["h"]) == (422, 43, 1076, 529)
    portrait = th_army.inset_rect((1080, 1920))
    assert portrait["y"] + portrait["h"] <= 0.5 * 1920        # top half
    assert portrait["border"] >= 3 and portrait["r"] > 0


def test_render_props_name_a_still_per_graphic_and_a_line_per_inset():
    props = th_army.render_props(army_job(), portrait=True)
    assert props["canvas"] == "army/canvas_9x16.png"
    assert props["end"] == "army/end_9x16.png"
    files = [(b["layout"], b.get("file"), b.get("textFile")) for b in props["beats"]]
    assert files[0] == ("full", None, None)
    assert files[1] == ("inset", None, "army/beat02_text_9x16.png")
    assert files[4] == ("graphic", "army/beat05_9x16.png", None)
    assert props["beats"][4]["kind"] == "trading"
    assert props["runs"] == {"inset": [[6.0, 17.0]], "split": []}


def test_asset_files_match_what_the_props_point_at():
    job = army_job()
    for portrait, aspect in ((False, "16x9"), (True, "9x16")):
        props = th_army.render_props(job, portrait)
        named = {props["canvas"], props["end"]} | {b.get("file") or b.get("textFile") for b in props["beats"]} - {None}
        assert named == set(th_army.asset_files(job, aspect))


def test_no_end_card_still_without_a_headline():
    job = army_job(endCard={"seconds": 2.0, "headline": ""})
    assert th_army.render_props(job, False)["end"] is None
    assert not any("end_" in f for f in th_army.asset_files(job, "16x9"))


# ---- sheet, pacing, chapters, SFX ---------------------------------------------------

def test_the_sheet_shows_every_beat_after_it_lands():
    moments = th_lib.sheet_moments(army_job())
    assert 7.0 in moments          # inset 6.0 + 1.0, punch line up
    assert 40.6 in moments         # trading card 40.0 + 0.6


def test_beats_break_up_a_static_stretch():
    assert th_lib.static_stretches(army_job([]))       # 90 seconds of Tony full frame
    insets = [beat("inset", t, t + 5.0, text="x") for t in (0.0, 12.0, 24.0, 36.0, 48.0, 60.0, 72.0, 84.0)]
    assert th_lib.static_stretches(army_job(insets)) == []


def test_pacing_names_what_is_on_screen():
    job = army_job([beat("graphic", 0.0, 9.0, graphic={"type": "words", "text": "x"}), beat("inset", 9.5, 18.0, text="y")],
                   srcEnd=20.0, cuts=[])
    assert [g["showing"] for g in th_lib.static_stretches(job)] == ["words graphic", "Tony in the inset"]


def test_trading_cards_are_youtube_chapters_on_the_output_timeline():
    chapters = th_lib.chapters(army_job(), intro="Intro")
    assert chapters[-1] == (38.0, "#5 The cost")    # 40.0 minus the 2s cut


def test_sfx_whoosh_into_a_chain_pop_inside_it_impact_on_number_one():
    job = army_job()
    raw = th_army.sfx(job)
    assert (6.0, "whoosh") in raw and (6.15, "pop") in raw      # Tony shrinks, line lands
    assert (10.0, "pop") in raw                                 # agenda inside the chain
    assert (40.0, "whoosh") in raw and (43.0, "pop") in raw
    one = army_job([beat("graphic", 5.0, 8.0, graphic={**CARD, "number": 1}, prompt="p")])
    assert (5.0, "impact") in th_army.sfx(one)
    assert {"t": 6.0, "kind": "whoosh"} in th_lib.sfx_cues(job)


# ---- drawing ---------------------------------------------------------------------

@pytest.mark.parametrize("size", [(1920, 1080), (1080, 1920)])
def test_punch_line_layer_is_transparent_outside_the_text_area(size):
    layer = army.punch_overlay("1,757|comments", size, None, [2])
    assert layer.mode == "RGBA" and layer.size == size
    box, area = army.frame_boxes(size, True)
    x0, y0, x1, y1 = layer.getbbox()
    assert y0 >= box[3]                                   # never over Tony's box
    assert y1 <= area[3] + size[1] * 0.01                 # clear of the caption band
    assert layer.getchannel("A").getextrema()[1] == 255   # letters solid, not thinned


def test_frame_shots_still_use_the_same_box(tmp_path):
    pic = Image.new("RGB", (640, 360), (90, 120, 160))
    img = army.render({"type": "frame", "text": "You read|it first"}, (1920, 1080), None, [pic], None, seed=3)
    box, _ = army.frame_boxes((1920, 1080), True)
    # inside the frame is the picture, outside it the navy canvas
    assert img.getpixel((round((box[0] + box[2]) / 2), round((box[1] + box[3]) / 2))) == (90, 120, 160)


@pytest.fixture
def built(tmp_path, monkeypatch):
    calls = []

    def flux(cfg, theme, prompt, size, seed=None):
        calls.append((prompt, size))
        return Image.new("RGB", size, (100, 140, 180)), seed or 11, 0.5
    monkeypatch.setattr(gen_images, "flux_picture", flux)
    monkeypatch.setattr(gen_images, "subject_cutout", lambda path: None)
    monkeypatch.setattr(common, "job_dir", lambda job_id: tmp_path)
    monkeypatch.setattr(common, "load_config", lambda: {})
    return tmp_path, calls


def test_build_draws_every_asset_for_both_cuts(built):
    jdir, calls = built
    job = army_job()
    written = th_army_build.build("j", job)
    assert sorted(written) == sorted(th_army.asset_files(job, "16x9") + th_army.asset_files(job, "9x16"))
    assert Image.open(jdir / "public" / "army" / "beat05_9x16.png").size == (1080, 1920)
    assert Image.open(jdir / "public" / "army" / "beat02_text_16x9.png").mode == "RGBA"
    assert len(calls) == 1      # the card art, shared by both cuts


def test_rebuild_reuses_cached_pictures_and_drops_stale_stills(built):
    jdir, calls = built
    th_army_build.build("j", army_job())
    stale = jdir / "public" / "army" / "beat05_16x9.png"
    th_army_build.build("j", army_job([beat("inset", 1.0, 4.0, text="only one")]))
    assert not stale.exists()
    th_army_build.build("j", army_job())
    assert len(calls) == 1      # same prompt, same seed: no new FLUX call


def test_split_graphics_are_drawn_at_the_card_size(built):
    jdir, calls = built
    th_army_build.build("j", split_job())
    army_dir = jdir / "public" / "army"
    assert Image.open(army_dir / "beat03_16x9.png").size == th_army.card_size("16x9")
    assert Image.open(army_dir / "beat03_9x16.png").size == th_army.card_size("9x16")
    assert Image.open(army_dir / "wipe_5.png").mode == "RGBA"
    assert len(calls) == 1      # the card art, shared by both cuts


def test_a_new_seed_rerolls_the_picture(built):
    _, calls = built
    th_army_build.build("j", army_job())
    rerolled = army_job()
    rerolled["beats"][4] = {**rerolled["beats"][4], "seed": 99}
    th_army_build.build("j", rerolled)
    assert len(calls) == 2
