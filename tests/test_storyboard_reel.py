"""Storyboard reel: job.json validation, the timing math (fixed length, the Kling clip sets
its own shot, one `fill` shot absorbs the slack, sfx follow their shots), the Kling prompt
rules, the Shopify card copy, the feet repair, and the preview gate."""
import copy
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import approval  # noqa: E402
import sr_lib  # noqa: E402
import sr_matte  # noqa: E402
import sr_post  # noqa: E402

GOOD_PROMPT = ("Static locked-off camera. In one single slow upward movement he lifts the staff. "
               "It never swings sideways and never touches the ground. No lightning.")


def wizard(**over):
    """The Shop Wizard job as delivered 2026-10-18 (28.6 s)."""
    base = {
        "title": "Shop Wizard",
        "length": 28.6,
        "product": {"url": "https://yourshop.com/products/example-tee",
                    "title": "EXAMPLE TEE", "price": "$35", "sizes": "M-2XL", "colors": 5},
        "plate": {"src": "work/bg/plate.png", "prompt": "violet wireframe grid"},
        "figures": {
            "back": {"src": "src/skel_back.webp",
                     "feet": {"add": [1015, 1290, 1110, 1372], "drop": [820, 1345, 960, 1375]}},
            "front": {"src": "src/skel_front_side.webp", "feet": {"drop": [420, 838, 760, 858]}},
            "raised": {"src": "src/skel_staff_center_a.webp", "feet": {"rebuild": [440, 790, 800, 870]}},
        },
        "shots": [
            {"id": "logo", "kind": "logo", "dur": 3.2, "src": "src/logo.webp", "panel": 1},
            {"id": "black", "kind": "black", "dur": 1.0, "panel": 2},
            {"id": "back", "kind": "dolly", "dur": 5.0, "figure": "back", "panel": 3},
            {"id": "front", "kind": "pose", "dur": 1.5, "figure": "front", "panel": 4},
            {"id": "raise", "kind": "clip", "dur": "clip", "clip": "work/kling/raise_30.mp4",
             "from": "front", "to": "raised", "prompt": GOOD_PROMPT, "panel": 5},
            {"id": "glow", "kind": "glow", "dur": "fill", "figure": "raised", "panel": 5},
            {"id": "white", "kind": "white", "dur": 0.7, "panel": 6},
            {"id": "shirt", "kind": "shirt", "dur": 6.3, "src": "assets/photos/tee.jpg", "panel": 7},
            {"id": "card", "kind": "card", "dur": 3.0, "mockup": "src/shirt_mockup.webp", "panel": 8},
        ],
        "audio": {"music": "assets/music/bed.mp3", "sfx": [
            {"src": "impact.mp3", "shot": "logo", "offset": 0.12, "gain": -3},
            {"src": "whoosh.mp3", "shot": "front", "offset": -0.2, "gain": -6},
            {"src": "orb-charge.mp3", "shot": "raise", "offset": 2.2, "gain": -2},
            {"src": "impact.mp3", "shot": "white", "offset": -0.3, "gain": -2},
            {"src": "impact.mp3", "shot": "card", "offset": 0.0, "gain": -3}]},
        "post": {"caption": "He raised the staff.", "hashtags": ["yourshop"]},
    }
    base.update(over)
    return base


def kling(seconds):
    return lambda shot: seconds


def spans(job, clip=3.033):
    rows, total = sr_lib.timeline(job, kling(clip))
    return {shot["id"]: (start, end) for shot, start, end in rows}, total


def shot(job, sid):
    return next(s for s in job["shots"] if s["id"] == sid)


# ---------- timing ----------

def test_wizard_timeline_matches_the_delivered_cut():
    got, total = spans(wizard())
    assert total == 28.6
    assert got["front"] == (9.2, 10.7)
    assert got["raise"] == (10.7, 13.733)
    assert got["glow"] == (13.733, 18.6)
    assert got["white"] == (18.6, 19.3)
    assert got["card"] == (25.6, 28.6)


def test_a_longer_kling_clip_shortens_the_fill_shot_and_keeps_the_ending():
    got, total = spans(wizard(), clip=4.0)
    assert got["raise"] == (10.7, 14.7)
    assert got["glow"] == (14.7, 18.6)
    assert got["white"][0] == 18.6 and total == 28.6


def test_before_the_clip_exists_its_default_length_stands_in():
    rows, _ = sr_lib.timeline(wizard(), lambda s: None)
    assert {s["id"]: round(b - a, 3) for s, a, b in rows}["raise"] == 3.0


def test_frame_count_matches_the_delivered_video():
    assert sr_lib.frame_count(28.6, 30) == 858


def test_shot_at_a_cut_belongs_to_the_next_shot_and_the_end_holds_the_card():
    rows, _ = sr_lib.timeline(wizard(), kling(3.033))
    assert sr_lib.shot_at(rows, 276 / 30)[0]["id"] == "front"
    assert sr_lib.shot_at(rows, 275 / 30)[0]["id"] == "back"
    assert sr_lib.shot_at(rows, 28.6)[0]["id"] == "card"


def test_sfx_follow_their_shots():
    rows, _ = sr_lib.timeline(wizard(), kling(3.033))
    cues = sr_lib.sfx_cues(wizard(), rows)
    assert [round(at, 3) for _, at, _ in cues] == [0.12, 9.0, 12.9, 18.3, 25.6]
    assert cues[1][2] == -6


def test_sfx_can_be_placed_at_an_absolute_time():
    job = wizard()
    job["audio"]["sfx"] = [{"src": "impact.mp3", "at": 4.5}]
    rows, _ = sr_lib.timeline(job, kling(3.033))
    assert sr_lib.sfx_cues(job, rows) == [("impact.mp3", 4.5, 0)]


def test_sheet_keys_sample_every_shot_with_panel_labels():
    rows, _ = sr_lib.timeline(wizard(), kling(3.033))
    keys = sr_lib.sheet_keys(rows)
    labels = [label for _, label in keys]
    assert labels[0] == "1 Logo" and "3 Dolly in, start" in labels and labels[-1] == "8 Card"
    assert len(keys) == 11
    for t, _ in keys:
        assert 0 <= t < 28.6


def test_a_shot_label_and_sheet_override_are_used():
    job = wizard()
    shot(job, "glow")["label"] = "Orb glows"
    shot(job, "shirt")["sheet"] = [[0.5, "Halfway"]]
    rows, _ = sr_lib.timeline(job, kling(3.033))
    labels = [label for _, label in sr_lib.sheet_keys(rows)]
    assert "5 Orb glows" in labels and "7 Halfway" in labels and "7 Blank shirt" not in labels


def test_preview_window_brackets_the_clip():
    rows, total = sr_lib.timeline(wizard(), kling(3.033))
    assert sr_lib.preview_window(rows, total) == (8.6, 19.4)


# ---------- validation ----------

def test_the_wizard_job_is_valid():
    assert sr_lib.validate(wizard(), kling(3.033)) == []


def test_missing_files_are_named():
    problems = sr_lib.validate(wizard(), kling(3.033), exists=lambda p: "plate" not in p)
    assert any("work/bg/plate.png" in p for p in problems)


def test_unknown_kind_and_duplicate_ids():
    job = wizard()
    job["shots"][1] = {"id": "logo", "kind": "smoke", "dur": 1.0}
    problems = sr_lib.validate(job, kling(3.033))
    assert any("unique" in p for p in problems)
    assert any("kind" in p for p in problems)


def test_only_one_fill_shot():
    job = wizard()
    shot(job, "white")["dur"] = "fill"
    assert any("fill" in p for p in sr_lib.validate(job, kling(3.033)))


def test_shots_that_overrun_the_length_are_flagged():
    job = wizard()
    shot(job, "shirt")["dur"] = 12.0
    assert any("glow" in p and "fill" in p for p in sr_lib.validate(job, kling(3.033)))


def test_without_a_fill_shot_the_durations_must_add_up():
    job = wizard()
    shot(job, "glow")["dur"] = 4.0
    assert any("28.6" in p for p in sr_lib.validate(job, kling(3.033)))


def test_dur_clip_only_on_a_clip_shot():
    job = wizard()
    shot(job, "white")["dur"] = "clip"
    assert any("white" in p and "clip" in p for p in sr_lib.validate(job, kling(3.033)))


def test_a_clip_must_follow_a_pose_of_its_start_figure():
    job = wizard()
    shot(job, "front")["figure"] = "raised"
    assert any("raise" in p and "pose" in p for p in sr_lib.validate(job, kling(3.033)))


def test_the_glow_after_a_clip_uses_its_end_figure():
    job = wizard()
    shot(job, "glow")["figure"] = "front"
    assert any("glow" in p and "raised" in p for p in sr_lib.validate(job, kling(3.033)))


def test_unknown_figures_are_flagged():
    job = wizard()
    shot(job, "back")["figure"] = "side"
    assert any("side" in p for p in sr_lib.validate(job, kling(3.033)))


def test_glow_needs_room_for_the_blowout():
    job = wizard()
    shot(job, "shirt")["dur"] = 9.5
    assert any("glow" in p and "2.0" in p for p in sr_lib.validate(job, kling(3.033)))


def test_sfx_must_point_at_a_real_shot_and_land_inside_the_video():
    job = wizard()
    job["audio"]["sfx"] = [{"src": "a.mp3", "shot": "nope"}, {"src": "b.mp3", "at": 40}]
    problems = sr_lib.validate(job, kling(3.033))
    assert any("nope" in p for p in problems)
    assert any("40" in p for p in problems)


def test_feet_boxes_must_be_four_ordered_numbers():
    job = wizard()
    job["figures"]["front"]["feet"] = {"drop": [760, 838, 420, 858]}
    job["figures"]["back"]["feet"] = {"nudge": [1, 2, 3, 4]}
    problems = sr_lib.validate(job, kling(3.033))
    assert any("front" in p and "drop" in p for p in problems)
    assert any("nudge" in p for p in problems)


def test_missing_top_level_keys():
    job = wizard()
    del job["length"]
    assert any("length" in p for p in sr_lib.validate(job, kling(3.033)))


# ---------- Kling prompt rules ----------

def test_swing_in_a_kling_prompt_is_flagged_unless_it_is_ruled_out():
    bad = "Static camera. He swings it in front of his body and raises it."
    assert any("swing" in p for p in sr_lib.kling_prompt_problems(bad))
    assert sr_lib.kling_prompt_problems(GOOD_PROMPT) == []


def test_a_kling_prompt_must_lock_the_camera():
    assert any("camera" in p for p in sr_lib.kling_prompt_problems("He lifts the staff slowly."))


def test_a_bad_kling_prompt_fails_validation():
    job = wizard()
    shot(job, "raise")["prompt"] = "He swings the staff overhead."
    assert any("raise" in p and "swing" in p for p in sr_lib.validate(job, kling(3.033)))


# ---------- card copy from Shopify ----------

SHOPIFY = {"product": {
    "title": "EXAMPLE TEE",
    "options": [{"name": "Color", "values": ["Black", "White", "Charcoal", "Navy", "Military Green"]},
                {"name": "Size", "values": ["M", "L", "XL", "2XL"]}],
    "variants": [{"price": "35.00"}, {"price": "35.00"}]}}


def test_product_facts_from_the_shopify_json():
    facts = sr_lib.product_facts(SHOPIFY, "https://yourshop.com/products/example-tee?x=1")
    assert facts == {"url": "https://yourshop.com/products/example-tee",
                     "title": "EXAMPLE TEE", "price": "$35", "sizes": "M-2XL", "colors": 5,
                     "color_names": ["Black", "White", "Charcoal", "Navy", "Military Green"]}


def test_card_details_line_and_text_fill():
    product = wizard()["product"]
    assert sr_lib.details(product) == "$35   ·   M-2XL   ·   5 COLORS"
    assert sr_lib.fill_text("{title} at {site}", product) == "EXAMPLE TEE at YOURSHOP.COM"


def test_one_colour_and_cents_prices():
    data = copy.deepcopy(SHOPIFY)
    data["product"]["options"][0]["values"] = ["Black"]
    data["product"]["variants"] = [{"price": "29.99"}]
    facts = sr_lib.product_facts(data, "https://yourshop.com/products/x")
    assert facts["price"] == "$29.99" and facts["colors"] == 1
    assert sr_lib.details(facts) == "$29.99   ·   M-2XL"


# ---------- feet repair ----------

def test_drop_clears_dark_floor_shadow_inside_the_box_only():
    src = np.full((40, 40, 3), 200, np.uint8)
    src[10:20, 5:35] = 60                       # cast shadow on a pale floor
    cut = np.zeros((40, 40, 4), np.uint8)
    cut[..., 3] = 0
    cut[10:20, 5:35, 3] = 255                    # rembg kept the shadow
    out = sr_matte.repair_feet(src, cut, {"drop": [5, 10, 20, 20]})
    assert out[15, 10, 3] == 0                   # inside the box: dropped
    assert out[15, 30, 3] == 255                 # outside the box: untouched
    assert cut[15, 10, 3] == 255                 # the input is not modified


def test_add_restores_pale_bone_the_matte_lost():
    src = np.full((40, 40, 3), 120, np.uint8)
    src[10:20, 10:20] = 230                      # pale bone
    cut = np.zeros((40, 40, 4), np.uint8)
    out = sr_matte.repair_feet(src, cut, {"add": [5, 5, 25, 25]})
    assert out[15, 15, 3] == 255 and tuple(out[15, 15, :3]) == (230, 230, 230)
    assert out[7, 7, 3] == 0


# ---------- preview gate ----------

def gate_job(tmp_path):
    job = wizard()
    for rel in ("src/skel_back.webp", "work/bg/plate.png", "work/kling/raise_30.mp4", "work/cut/skel_back.png"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_bytes(rel.encode())
    (tmp_path / "job.json").write_text(json.dumps(job))
    return tmp_path, job


def fp(path):
    return approval.fingerprint(path, "storyboard-reel")


def test_sound_and_post_edits_do_not_void_an_approval(tmp_path):
    j, job = gate_job(tmp_path)
    before = fp(j)
    job["audio"]["sfx"][0]["gain"] = -9
    job["post"]["caption"] = "new words"
    (j / "job.json").write_text(json.dumps(job))
    assert fp(j) == before


def test_picture_edits_void_an_approval(tmp_path):
    j, job = gate_job(tmp_path)
    before = fp(j)
    shot(job, "shirt")["dur"] = 6.0
    (j / "job.json").write_text(json.dumps(job))
    assert fp(j) != before


def test_a_new_plate_clip_or_cutout_voids_an_approval(tmp_path):
    j, _ = gate_job(tmp_path)
    for rel in ("work/bg/plate.png", "work/kling/raise_30.mp4", "work/cut/skel_back.png"):
        before = fp(j)
        (j / rel).write_bytes(b"rerolled")
        assert fp(j) != before, rel


def test_template_placeholders_left_in_a_kling_prompt_are_flagged():
    job = wizard()
    shot(job, "raise")["prompt"] = GOOD_PROMPT + " A <figure description> on the grid."
    assert any("placeholders" in p for p in sr_lib.validate(job, kling(3.033)))


def test_post_text_layout():
    job = wizard()
    job["post"]["notes"] = ["Product: tee."]
    text = sr_post.post_text(job)
    assert text.startswith("SHOP WIZARD (Example Tee) - 9:16. Per-platform captions: posts.md\n\n"
                           "CAPTION\nHe raised the staff.\n\nYOURSHOP NEW DROP\n")
    assert "#skatewear\n\nLINK\nhttps://yourshop.com/products/example-tee\n\nNOTES\n" in text
    assert text.endswith("NOTES\n- Product: tee.\n")


# ---------- VHS overlay ----------

def test_vhs_number_is_the_strength_with_wizard_defaults():
    rows, _ = sr_lib.timeline(wizard(vhs=0.5), kling(3.033))
    cfg = sr_lib.vhs_config(wizard(vhs=0.5), rows)
    assert cfg == {"strength": 0.5, "fade": (18.6, 19.3), "osd": "PLAY \u25B6", "osd_end": 4.2}


def test_vhs_is_off_by_default():
    rows, _ = sr_lib.timeline(wizard(), kling(3.033))
    assert sr_lib.vhs_config(wizard(), rows)["strength"] == 0


def test_vhs_covers_the_character_section_and_fades_out_across_the_white():
    rows, _ = sr_lib.timeline(wizard(vhs=0.5), kling(3.033))
    cfg = sr_lib.vhs_config(wizard(vhs=0.5), rows)
    assert sr_lib.vhs_mix(cfg, 10.0) == 1.0
    assert sr_lib.vhs_mix(cfg, 18.6) == 1.0
    assert 0.4 < sr_lib.vhs_mix(cfg, 18.95) < 0.6
    assert sr_lib.vhs_mix(cfg, 19.3) == 0.0 and sr_lib.vhs_mix(cfg, 27.0) == 0.0


def test_vhs_options_can_move_the_fade_and_the_readout():
    job = wizard(vhs={"strength": 1, "fade_on": "card", "osd": "", "osd_until": "logo"})
    rows, _ = sr_lib.timeline(job, kling(3.033))
    cfg = sr_lib.vhs_config(job, rows)
    assert cfg["fade"] == (25.6, 28.6) and cfg["osd"] == "" and cfg["osd_end"] == 3.2


def test_bad_vhs_settings_are_flagged():
    for vhs in (1.5, {"strength": 0.5, "fade_on": "nope"}, {"strength": 0.5, "osd_until": "nope"}):
        problems = sr_lib.validate(wizard(vhs=vhs), kling(3.033))
        assert any("vhs" in p for p in problems), vhs


def test_cover_defaults_to_the_glow_at_full_strength():
    rows, _ = sr_lib.timeline(wizard(), kling(3.033))
    assert sr_lib.cover_time(wizard(), rows) == 17.2
    job = wizard()
    job["post"]["cover"] = {"at": 16.6}
    assert sr_lib.cover_time(job, rows) == 16.6


# ---------- posts.md ----------

def social(job):
    job["product"]["color_names"] = ["Black", "White", "Charcoal", "Navy", "Military Green"]
    job["post"].update({
        "cover": {"note": "the orb at full glow"},
        "instagram": {"cover_text": "SUMMON THE DROP", "caption": "Don't blink.", "hashtags": ["darkapparel"],
                      "pin": "Which color?", "notes": ["Pick cover.jpg."]},
        "tiktok": {"on_screen": "wait for it", "caption": "he raises it", "hashtags": ["lowpoly"], "pin": "which"},
        "youtube": {"title": "The Wizard", "description": "Example Tee by Shop.", "hashtags": ["shorts"]},
        "facebook": {"caption": "Watch the orb.", "notes": ["Link in the first comment."]},
        "hooks": ["Don't blink.", "Summoned, not restocked."], "order": "TikTok first."})
    return job


def test_posts_md_has_every_platform_and_every_caption_ends_with_the_signature():
    md = sr_post.posts_md(social(wizard(vhs=0.5)), clean=True)
    assert md.startswith("# Shop Wizard: social posts\n\n**Video:** `final_9x16_vhs.mp4` (28.6s, 9:16, VHS overlay at 50%). "
                         "Clean version: `final_9x16.mp4`.\n**Cover:** `cover.jpg` (the orb at full glow).")
    assert "**Product:** Example Tee. $35. M to 2XL. Black, White, Charcoal, Navy, Military Green.\n" in md
    for head in ("## Instagram Reels", "## TikTok", "## YouTube Shorts", "## Facebook Reels", "## Hooks to test",
                 "## Order of play"):
        assert head in md
    assert "**Title:** The Wizard" in md
    blocks = md.split("```")[1::2]
    assert len(blocks) == 5
    for block in blocks[1:]:
        body = block.strip("\n").split("\n\n#")[0] if "\n\n#" in block else block.strip("\n")
        assert body.endswith(sr_post.SIGNATURE)
    assert blocks[1].strip("\n").endswith("#darkapparel")
    assert "clears the PLAY readout" in md


def test_posts_md_without_vhs_or_a_clean_cut():
    md = sr_post.posts_md(social(wizard()), clean=True)
    assert md.split("\n")[2] == "**Video:** `final_9x16.mp4` (28.6s, 9:16)."
    assert "Clean version" not in md and "PLAY readout" not in md


def test_the_deliverable_is_the_tape_cut_only_when_vhs_is_on():
    assert sr_post.main_video(wizard(vhs=0.5)) == "final_9x16_vhs.mp4"
    assert sr_post.main_video(wizard()) == sr_post.main_video(wizard(vhs=0)) == "final_9x16.mp4"


def test_post_problems_name_empty_captions_and_template_placeholders():
    job = social(wizard())
    job["post"]["tiktok"]["caption"] = ""
    job["post"]["instagram"]["notes"] = ["Rename the sound to SHOP // <NAME>.EXE"]
    problems = sr_post.post_problems(job)
    assert any("tiktok" in p for p in problems) and any("<NAME>" in p for p in problems)
    assert sr_post.post_problems(social(wizard())) == []


# ---------- full-frame stills (Night Soldier, 2026-10-24) ----------

EYES_PROMPT = ("Static locked-off camera. Extreme close-up of the skull. In one single quick movement "
               "his glowing eyes dart to his left. The skull and helmet stay still. No camera movement.")


def soldier(**over):
    """A board drawn from full-frame generated stills: no plate, no figures, a Kling clip
    between two stills, and a black beat where the music cuts out under gunfire."""
    base = {
        "title": "Shop Night Soldier",
        "length": 20.0,
        "product": {"url": "https://yourshop.com/products/night soldier",
                    "title": "NIGHT SOLDIER", "price": "$35", "sizes": "M-2XL", "colors": 5},
        "shots": [
            {"id": "logo", "kind": "logo", "dur": 3.0, "src": "src/logo.png", "panel": 1},
            {"id": "hall", "kind": "still", "dur": "fill", "src": "work/keys/hall.png",
             "push": 0.1, "fade_in": 1.0, "panel": 3},
            {"id": "face", "kind": "still", "dur": 1.2, "src": "work/keys/face.png", "flash": 0.15, "panel": 4},
            {"id": "eyes", "kind": "clip", "dur": "clip", "clip": "work/kling/eyes_30.mp4",
             "start": "work/keys/face.png", "end": "work/keys/face_left.png", "prompt": EYES_PROMPT, "panel": 5},
            {"id": "shots", "kind": "black", "dur": 2.0, "panel": 9},
            {"id": "white", "kind": "white", "dur": 0.5, "panel": 10},
            {"id": "shirt", "kind": "shirt", "dur": 4.0, "src": "assets/photos/tee.jpg", "panel": 10},
            {"id": "card", "kind": "card", "dur": 3.0, "mockup": "product/shop_01.jpg", "panel": 10},
        ],
        "audio": {"music": "assets/music/bed.mp3", "mute": ["shots"], "sfx": []},
        "post": {"caption": "He heard something."},
    }
    base.update(over)
    return base


def test_a_still_board_needs_no_plate_or_figures():
    assert sr_lib.validate(soldier(), kling(3.0)) == []


def test_a_still_needs_its_image():
    job = soldier()
    del shot(job, "hall")["src"]
    assert any("hall" in p and "src" in p for p in sr_lib.validate(job, kling(3.0)))
    missing = sr_lib.validate(soldier(), kling(3.0), exists=lambda p: p != "work/keys/face_left.png")
    assert any("face_left" in p for p in missing)


def test_a_still_clip_needs_its_start_frame():
    job = soldier()
    del shot(job, "eyes")["start"]
    assert any("eyes" in p and "start" in p for p in sr_lib.validate(job, kling(3.0)))


def test_a_camera_clip_needs_no_end_frame():
    """Tony, 2026-10-25: camera-first clips run from a start frame only, so the camera is free."""
    job = soldier()
    del shot(job, "eyes")["end"]
    assert sr_lib.validate(job, kling(3.0)) == []


def test_a_camera_clip_can_cut_in_after_any_shot():
    job = soldier()
    job["shots"] = [s for s in job["shots"] if s["id"] != "face"]
    job["shots"].insert(2, {"id": "gap", "kind": "black", "dur": 0.5})
    assert sr_lib.validate(job, kling(3.0)) == []


def test_a_still_clip_must_follow_a_still_of_its_start_frame():
    job = soldier()
    shot(job, "face")["src"] = "work/keys/other.png"
    assert any("eyes" in p and "still" in p for p in sr_lib.validate(job, kling(3.0)))


def test_a_still_that_holds_a_clip_cannot_push():
    job = soldier()
    shot(job, "face")["push"] = 0.1
    assert any("face" in p and "push" in p for p in sr_lib.validate(job, kling(3.0)))


def test_a_figure_clip_still_needs_the_plate():
    job = wizard()
    del job["plate"]
    assert any("plate" in p for p in sr_lib.validate(job, kling(3.033)))


def test_the_still_board_timeline_fills_around_the_clip():
    got, total = spans(soldier(), clip=3.033)
    assert total == 20.0
    assert got["hall"] == (3.0, 6.267)
    assert got["eyes"] == (7.467, 10.5)
    assert got["shots"] == (10.5, 12.5)


def test_still_sheet_keys_use_the_panel_and_label():
    job = soldier()
    shot(job, "face")["label"] = "Skull close-up"
    rows, _ = sr_lib.timeline(job, kling(3.0))
    labels = [label for _, label in sr_lib.sheet_keys(rows)]
    assert "3 Still" in labels and "4 Skull close-up" in labels


def test_music_cuts_out_across_its_mute_shots():
    rows, _ = sr_lib.timeline(soldier(), kling(3.0))
    assert sr_lib.music_mutes(soldier(), rows) == [(10.5, 12.5)]


def test_a_mute_must_name_a_real_shot():
    job = soldier()
    job["audio"]["mute"] = ["gunfire"]
    assert any("mute" in p and "gunfire" in p for p in sr_lib.validate(job, kling(3.0)))


def _still_assets(tmp_path, shots, length, mkdir=True, **over):
    import pytest
    pytest.importorskip("cv2")
    import sr_shots
    from PIL import Image
    if mkdir:
        (tmp_path / "keys").mkdir()
        Image.new("RGB", (540, 960), (200, 30, 30)).save(tmp_path / "keys" / "red.png")
        Image.new("RGB", (540, 960), (30, 30, 200)).save(tmp_path / "keys" / "blue.png")
    job = {"title": "t", "length": length, "product": soldier()["product"], "shots": shots, **over}
    rows, _ = sr_lib.timeline(job, lambda s: None)
    return sr_shots, sr_shots.Assets(tmp_path, job, rows, lambda p: tmp_path / p)


def test_a_still_fills_the_frame_fades_in_and_flashes(tmp_path):
    shots = [{"id": "hall", "kind": "still", "dur": 2.0, "src": "keys/red.png", "fade_in": 1.0, "push": 0.1},
             {"id": "face", "kind": "still", "dur": 1.0, "src": "keys/blue.png", "flash": 0.3}]
    sr_shots, a = _still_assets(tmp_path, shots, 3.0)
    img, sid = sr_shots.frame_at(a, 0.0)
    assert sid == "hall" and img.max() < 8                      # faded up from black
    img, _ = sr_shots.frame_at(a, 1.5)
    assert img.shape == (1920, 1080, 3) and abs(int(img[960, 540, 0]) - 200) < 4
    img, sid = sr_shots.frame_at(a, 2.0)
    assert sid == "face" and img.min() > 245                    # the flash cut opens on white
    img, _ = sr_shots.frame_at(a, 2.6)
    assert abs(int(img[960, 540, 2]) - 200) < 4


def test_a_still_clip_stands_in_as_a_dissolve_between_its_frames(tmp_path):
    shots = [{"id": "face", "kind": "still", "dur": 1.0, "src": "keys/red.png"},
             {"id": "eyes", "kind": "clip", "dur": "clip", "clip": "kling/none.mp4",
              "start": "keys/red.png", "end": "keys/blue.png", "prompt": EYES_PROMPT}]
    sr_shots, a = _still_assets(tmp_path, shots, 4.0)
    start, _ = sr_shots.frame_at(a, 1.1)
    end, _ = sr_shots.frame_at(a, 3.9)
    assert start[960, 540, 0] > 190 and end[960, 540, 2] > 190


def test_handheld_is_off_by_default():
    rows, _ = sr_lib.timeline(soldier(), kling(3.0))
    cfg = sr_lib.handheld_config(soldier(), rows)
    assert cfg["strength"] == 0 and sr_lib.handheld_offset(cfg, 6.0) is None


def test_handheld_covers_the_character_section_and_nothing_else():
    job = soldier(handheld=0.6)
    rows, _ = sr_lib.timeline(job, kling(3.0))
    spans = {s["id"]: (a, b) for s, a, b in rows}
    cfg = sr_lib.handheld_config(job, rows)
    assert cfg["span"] == (spans["hall"][0], spans["eyes"][1])
    assert sr_lib.handheld_offset(cfg, 1.0) is None                       # logo stays put
    assert sr_lib.handheld_offset(cfg, spans["face"][0] + 0.1) is not None
    assert sr_lib.handheld_offset(cfg, spans["shirt"][0] + 0.5) is None   # shirt and card stay clean


def test_handheld_options_can_move_the_span():
    job = soldier(handheld={"strength": 0.4, "from": "face", "to": "face"})
    rows, _ = sr_lib.timeline(job, kling(3.0))
    spans = {s["id"]: (a, b) for s, a, b in rows}
    cfg = sr_lib.handheld_config(job, rows)
    assert cfg["strength"] == 0.4 and cfg["span"] == spans["face"]


def test_handheld_drift_is_slight_smooth_and_runs_through_the_cuts():
    job = soldier(handheld=1.0)
    rows, _ = sr_lib.timeline(job, kling(3.0))
    cfg = sr_lib.handheld_config(job, rows)
    t0, t1 = cfg["span"]
    moves = [sr_lib.handheld_offset(cfg, t0 + i / 30) for i in range(int((t1 - t0) * 30))]
    xs, ys, rots = (np.array([m[k] for m in moves]) for k in range(3))
    assert np.abs(xs).max() <= sr_lib.HANDHELD["x"] and np.abs(ys).max() <= sr_lib.HANDHELD["y"]
    assert np.abs(rots).max() <= sr_lib.HANDHELD["rot"]
    assert np.ptp(xs) > sr_lib.HANDHELD["x"] * 0.5                         # it really moves
    assert np.abs(np.diff(xs)).max() < 0.002 and np.abs(np.diff(ys)).max() < 0.002   # no jumps, cut or not


def test_handheld_overscan_never_shows_the_frame_edge():
    pytest = __import__("pytest")
    cv2 = pytest.importorskip("cv2")
    import sr_shots
    job = soldier(handheld=1.0)
    rows, _ = sr_lib.timeline(job, kling(3.0))
    cfg = sr_lib.handheld_config(job, rows)
    t0, t1 = cfg["span"]
    W, H = sr_shots.W, sr_shots.H
    corners = np.array([[0, 0, 1], [W - 1, 0, 1], [0, H - 1, 1], [W - 1, H - 1, 1]], np.float64).T
    for i in range(int((t1 - t0) * 30)):
        inv = cv2.invertAffineTransform(sr_shots.handheld_matrix(cfg, t0 + i / 30))
        x, y = inv @ corners
        assert x.min() >= 0 and x.max() <= W - 1 and y.min() >= 0 and y.max() <= H - 1


def test_handheld_moves_the_picture_only_inside_its_span(tmp_path):
    shots = [{"id": "hall", "kind": "still", "dur": 2.0, "src": "keys/grad.png"},
             {"id": "white", "kind": "white", "dur": 1.0}]
    from PIL import Image
    (tmp_path / "keys").mkdir()
    grad = np.tile(np.linspace(0, 255, 540, dtype=np.uint8)[None, :, None], (960, 1, 3))
    Image.fromarray(grad).save(tmp_path / "keys" / "grad.png")
    sr_shots, still = _still_assets(tmp_path, shots, 3.0, mkdir=False)
    _, shaky = _still_assets(tmp_path, shots, 3.0, mkdir=False, handheld=1.0)
    a, _ = sr_shots.frame_at(still, 1.0)
    b, _ = sr_shots.frame_at(shaky, 1.0)
    assert np.abs(a.astype(int) - b.astype(int)).mean() > 1.0
    assert (sr_shots.frame_at(shaky, 2.5)[0] == 255).all()


def test_bad_handheld_settings_are_flagged():
    for hh in (1.5, {"strength": 0.5, "from": "nope"}, {"strength": 0.5, "to": "nope"},
               {"strength": 0.5, "from": "eyes", "to": "hall"}, "lots"):
        problems = sr_lib.validate(soldier(handheld=hh), kling(3.0))
        assert any("handheld" in p for p in problems), hh
    assert sr_lib.validate(soldier(handheld=0.6), kling(3.0)) == []


# ---------- creator stamp (creator, Tony 2026-10-25) ----------

FROG = "assets/brand/creator/stamp_white.png"


def test_stamp_is_off_by_default():
    rows, _ = sr_lib.timeline(soldier(), kling(3.0))
    cfg = sr_lib.stamp_config(soldier(), rows)
    assert cfg is None and sr_lib.stamp_alpha(cfg, 6.0) == 0.0


def test_stamp_is_a_brief_credit_at_the_start_of_the_character_section():
    """Tony: "just brief, to show me as the creator". In, hold, out, then gone."""
    job = soldier(stamp={"src": FROG})
    rows, _ = sr_lib.timeline(job, kling(3.0))
    spans = {s["id"]: (a, b) for s, a, b in rows}
    cfg = sr_lib.stamp_config(job, rows)
    hall, s = spans["hall"][0], sr_lib.STAMP
    shown = hall + s["fade_in"]
    gone = shown + s["hold"] + s["fade_out"]
    assert cfg["span"] == (hall, spans["eyes"][1])
    assert sr_lib.stamp_alpha(cfg, 1.0) == 0.0                                  # not on the logo
    assert sr_lib.stamp_alpha(cfg, hall) == 0.0                                 # fades in
    assert sr_lib.stamp_alpha(cfg, shown) == s["opacity"]
    assert sr_lib.stamp_alpha(cfg, shown + s["hold"]) == s["opacity"]
    assert 0 < sr_lib.stamp_alpha(cfg, gone - s["fade_out"] / 2) < s["opacity"]   # fades out
    assert sr_lib.stamp_alpha(cfg, gone) == 0.0 and sr_lib.stamp_alpha(cfg, spans["eyes"][0]) == 0.0
    assert sr_lib.stamp_alpha(cfg, spans["shirt"][0] + 0.5) == 0.0              # shirt and card stay clean


def test_stamp_with_no_hold_stays_until_the_cut():
    job = soldier(stamp={"src": FROG, "hold": None})
    rows, _ = sr_lib.timeline(job, kling(3.0))
    spans = {s["id"]: (a, b) for s, a, b in rows}
    cfg = sr_lib.stamp_config(job, rows)
    eyes = spans["eyes"][1]
    assert sr_lib.stamp_alpha(cfg, eyes - 0.01) == sr_lib.STAMP["opacity"]
    assert sr_lib.stamp_alpha(cfg, eyes) == 0.0                                 # gone on the cut to black


def test_stamp_options_move_the_span_and_the_look():
    job = soldier(stamp={"src": FROG, "from": "face", "to": "face", "opacity": 0.3, "fade_in": 0})
    rows, _ = sr_lib.timeline(job, kling(3.0))
    spans = {s["id"]: (a, b) for s, a, b in rows}
    cfg = sr_lib.stamp_config(job, rows)
    assert cfg["span"] == spans["face"] and sr_lib.stamp_alpha(cfg, spans["face"][0]) == 0.3


def test_stamp_is_drawn_in_its_corner_only_inside_its_span(tmp_path):
    from PIL import Image
    shots = [{"id": "hall", "kind": "still", "dur": 2.0, "src": "keys/red.png"},
             {"id": "shots", "kind": "black", "dur": 1.0}]
    (tmp_path / "keys").mkdir()
    Image.new("RGB", (540, 960), (200, 30, 30)).save(tmp_path / "keys" / "red.png")
    Image.new("RGBA", (200, 100), (255, 255, 255, 255)).save(tmp_path / "keys" / "bug.png")
    stamp = {"src": "keys/bug.png", "height": 100, "opacity": 1.0, "fade_in": 0,
             "corner": "top-right", "margin": [50, 250]}
    sr_shots, a = _still_assets(tmp_path, shots, 3.0, mkdir=False, stamp=stamp)
    img, _ = sr_shots.frame_at(a, 1.0)
    assert img[300, 1080 - 50 - 100].min() > 250                     # white bug, 200 wide, 50 in from the right
    assert img[300, 1080 - 50 - 210, 0] < 210 and img[200, 980, 1] < 40   # red just outside it
    assert abs(int(img[960, 540, 0]) - 200) < 4                       # picture untouched elsewhere
    assert sr_shots.frame_at(a, 2.5)[0].max() == 0                   # gone on the black


def test_bad_stamp_settings_are_flagged():
    for stamp in ({"height": 100}, "frog", {"src": FROG, "height": 0}, {"src": FROG, "opacity": 1.5},
                  {"src": FROG, "corner": "middle"}, {"src": FROG, "margin": "x"},
                  {"src": FROG, "fade_in": -1}, {"src": FROG, "hold": -2}, {"src": FROG, "fade_out": "x"},
                  {"src": FROG, "from": "nope"},
                  {"src": FROG, "from": "eyes", "to": "hall"}):
        problems = sr_lib.validate(soldier(stamp=stamp), kling(3.0))
        assert any("stamp" in p for p in problems), stamp
    missing = sr_lib.validate(soldier(stamp={"src": FROG}), kling(3.0), exists=lambda p: p != FROG)
    assert missing == [f"missing file: {FROG} (stamp)"]
    assert sr_lib.validate(soldier(stamp={"src": FROG}), kling(3.0)) == []


CAMERA_PROMPT = ("Game cutscene camera at eye level, 85mm lens. One very slow, steady push in on the skull: "
                 "not a zoom, not a cut. Near the end the pupils dart to the right and stay there.")


def test_a_still_clip_prompt_may_move_the_camera():
    """The locked-camera rule is for figure clips, whose poses must line up on the plate."""
    job = soldier()
    shot(job, "eyes")["prompt"] = CAMERA_PROMPT
    assert sr_lib.validate(job, kling(3.0)) == []
    assert sr_lib.kling_prompt_problems(CAMERA_PROMPT, locked=False) == []
    assert any("camera" in p for p in sr_lib.kling_prompt_problems(CAMERA_PROMPT))


def test_a_figure_clip_must_still_lock_the_camera():
    job = wizard()
    shot(job, "raise")["prompt"] = "He lifts the staff slowly."
    assert any("raise" in p and "camera" in p for p in sr_lib.validate(job, kling(3.033)))


def test_a_clip_can_skip_its_first_seconds():
    job = soldier()
    shot(job, "eyes")["in"] = 0.5
    spans_, _ = spans(job, clip=3.0)
    assert round(spans_["eyes"][1] - spans_["eyes"][0], 3) == 2.5


def test_a_camera_clip_stands_in_as_its_start_frame(tmp_path):
    shots = [{"id": "gap", "kind": "black", "dur": 1.0},
             {"id": "eyes", "kind": "clip", "dur": "clip", "clip": "kling/none.mp4",
              "start": "keys/red.png", "prompt": CAMERA_PROMPT}]
    sr_shots, a = _still_assets(tmp_path, shots, 4.0)
    start, _ = sr_shots.frame_at(a, 1.1)
    end, _ = sr_shots.frame_at(a, 3.9)
    assert start[960, 540, 0] > 190 and end[960, 540, 0] > 190


def test_a_clip_plays_from_its_in_point(tmp_path):
    cv2 = __import__("pytest").importorskip("cv2")
    (tmp_path / "kling").mkdir()
    out = cv2.VideoWriter(str(tmp_path / "kling" / "c.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 30, (108, 192))
    for i in range(10):
        out.write(np.full((192, 108, 3), (30, 30, 220) if i < 5 else (220, 30, 30), np.uint8))   # BGR: red, then blue
    out.release()
    shots = [{"id": "gap", "kind": "black", "dur": 1.0},
             {"id": "c", "kind": "clip", "dur": 0.1, "clip": "kling/c.mp4", "in": 5 / 30,
              "start": "keys/red.png", "prompt": CAMERA_PROMPT}]
    sr_shots, a = _still_assets(tmp_path, shots, 1.1)
    img, sid = sr_shots.frame_at(a, 1.0)
    assert sid == "c" and img[96, 54, 2] > 150 and img[96, 54, 0] < 100


def test_lights_out_flickers_then_stays_dark():
    """Tony, 2026-10-25: the side hallway goes really dark because all the lights go out."""
    p = sr_lib.params({"id": "pov", "kind": "clip", "lights_out": {"at": 2.0, "flicker": 0.6, "floor": 0.03}})
    assert sr_lib.light_level(p, 1.9) == 1.0
    during = [sr_lib.light_level(p, 2.0 + i / 30) for i in range(18)]
    assert min(during) <= 0.03 + 1e-9 and max(during) > 0.3          # it flickers: off, back on, off
    assert all(sr_lib.light_level(p, t) == 0.03 for t in (2.61, 3.0, 4.0))


def test_gain_dims_a_whole_shot():
    p = sr_lib.params({"id": "pov", "kind": "clip", "gain": 0.7})
    assert sr_lib.light_level(p, 0.5) == 0.7
    assert sr_lib.light_level(sr_lib.params({"id": "x", "kind": "clip"}), 0.5) == 1.0


def test_lights_out_needs_a_time():
    job = soldier()
    shot(job, "eyes")["lights_out"] = {"floor": 0.03}
    assert any("eyes" in p and "lights_out" in p for p in sr_lib.validate(job, kling(3.0)))


def test_a_clip_goes_dark_when_the_lights_go_out(tmp_path):
    shots = [{"id": "gap", "kind": "black", "dur": 1.0},
             {"id": "pov", "kind": "clip", "dur": 3.0, "clip": "kling/none.mp4", "start": "keys/red.png",
              "prompt": CAMERA_PROMPT, "lights_out": {"at": 1.0, "flicker": 0.5, "floor": 0.05}}]
    sr_shots, a = _still_assets(tmp_path, shots, 4.0)
    lit, _ = sr_shots.frame_at(a, 1.5)
    dark, _ = sr_shots.frame_at(a, 3.5)
    assert lit[960, 540, 0] > 190 and dark[960, 540, 0] < 20


def test_the_no_music_twin_sits_beside_the_final():
    import storyboard_reel
    assert storyboard_reel.nomusic_path(Path("out/final_9x16_vhs.mp4")) == Path("out/final_9x16_vhs_nomusic.mp4")
    assert storyboard_reel.nomusic_path(Path("out/final_9x16.mp4")) == Path("out/final_9x16_nomusic.mp4")


def test_a_clip_can_fade_up_from_black_and_flash_off_a_cut(tmp_path):
    """Rooftop Sniper board (Tony, 2026-10-30): fade from black into the rooftop, flash cut to the skull."""
    shots = [{"id": "roof", "kind": "clip", "dur": 2.0, "clip": "kling/none.mp4", "start": "keys/red.png",
              "prompt": CAMERA_PROMPT, "fade_in": 1.0},
             {"id": "face", "kind": "clip", "dur": 2.0, "clip": "kling/none.mp4", "start": "keys/blue.png",
              "prompt": CAMERA_PROMPT, "flash": 0.3}]
    sr_shots, a = _still_assets(tmp_path, shots, 4.0)
    assert sr_shots.frame_at(a, 0.0)[0][960, 540, 0] < 10                   # black at the top of the fade
    assert sr_shots.frame_at(a, 1.5)[0][960, 540, 0] > 190                  # up to full picture
    assert sr_shots.frame_at(a, 2.0)[0].min() > 245                         # white on the flash cut
    late = sr_shots.frame_at(a, 2.5)[0][960, 540]
    assert late[2] > 190 and late[0] < 40                                   # the flash has gone


def test_a_scope_shot_shows_the_clip_only_through_the_lens(tmp_path):
    """Panels 5 and 6: black frame, a round lens, a crosshair over the picture."""
    shots = [{"id": "scope", "kind": "clip", "dur": 2.0, "clip": "kling/none.mp4", "start": "keys/red.png",
              "prompt": CAMERA_PROMPT, "scope": {"sway": 0}}]
    sr_shots, a = _still_assets(tmp_path, shots, 2.0)
    img = sr_shots.frame_at(a, 1.0)[0]
    assert img[40, 40].max() < 5 and img[1880, 40].max() < 5                # outside the ring is black
    assert img[960, 40].max() < 5                                           # past the rim at the frame edge
    assert img[800, 700, 0] > 150                                           # the picture shows in the lens
    assert img[960, 700, 0] < 40 and img[800, 540, 0] < 40                  # the reticle's two lines
    assert img[960, 540, 0] < 40                                            # and its centre dot


def test_a_real_scope_never_stops_dead():
    """Tony 2026-10-30: "move freely like a real scope". A held breath calms it, nothing freezes it."""
    import pytest
    pytest.importorskip("cv2")
    import sr_shots
    cfg = sr_lib.scope_cfg({"sway": 20, "steady": 2.0})
    free = [sr_shots.scope_sway(cfg, t / 10) for t in range(0, 15)]
    held = [sr_shots.scope_sway(cfg, 2.6 + t / 30)[0] for t in range(0, 30)]
    assert 8 < max(abs(x) for x, _ in free) <= 20
    assert 0.2 < max(held) - min(held) < 8


def test_the_ring_floats_only_while_the_hand_moves():
    import pytest
    pytest.importorskip("cv2")
    import sr_shots
    moving = [sr_shots.scope_float(sr_lib.scope_cfg({"sway": 20}), t / 10) for t in range(0, 30)]
    assert max(abs(x) for x, _ in moving) > 2
    assert sr_shots.scope_float(sr_lib.scope_cfg({"sway": 0}), 1.0) == (0.0, 0.0)


def test_a_hand_steers_the_lens_it_does_not_pan_it():
    """Each point is where he wants to look: the aim leans in, overshoots, corrects and lands."""
    import pytest
    path = sr_lib.hand_path([[0, 0.1, 0.2], [0.2, 0.5, 0.4], [1.8, 0.7, 0.5]], 3.0, 30)
    xs = [x for x, _ in path]
    steps = sorted(abs(b - a) for a, b in zip(xs, xs[1:]))
    assert len(path) == 90
    assert path[0] == pytest.approx((0.1, 0.2))
    assert path[-1] == pytest.approx((0.7, 0.5))
    assert max(xs[:54]) > 0.5                       # ran past the point it was heading for
    assert steps[-1] > 4 * steps[len(steps) // 2]   # bursts and rests, never one speed


def test_the_eye_falls_behind_a_fast_move_and_catches_up():
    path = [(i * 10.0, 0.0) for i in range(30)] + [(290.0, 0.0)] * 60
    lag = sr_lib.aim_lag(path, 30)
    assert lag[25][0] > 20
    assert abs(lag[-1][0]) < 1


def _wide_still(tmp_path):
    """A still with a red left half and a blue right half."""
    from PIL import Image
    (tmp_path / "keys").mkdir()
    wide = Image.new("RGB", (1600, 900), (200, 30, 30))
    wide.paste((30, 30, 200), (800, 0, 1600, 900))
    wide.save(tmp_path / "keys" / "wide.png")


SCAN = {"id": "scope", "kind": "scan", "dur": 2.0, "src": "keys/wide.png", "span": 0.2,
        "path": [[0, 0.25, 0.5], [0.2, 0.75, 0.5]], "scope": {"sway": 0}}


def test_a_scan_steers_the_lens_across_one_wide_still(tmp_path):
    """Panel 5: the search is drawn in the edit, so nothing about it is left to a generated pan."""
    _wide_still(tmp_path)
    sr_shots, a = _still_assets(tmp_path, [dict(SCAN)], 2.0, mkdir=False)
    start, end = sr_shots.frame_at(a, 0.0)[0], sr_shots.frame_at(a, 1.9)[0]
    assert start[800, 700, 0] > 150 and start[800, 700, 2] < 60             # the red half
    assert end[800, 700, 2] > 150 and end[800, 700, 0] < 60                 # steered to the blue half
    assert end[40, 40].max() < 5 and end[960, 700, 2] < 40                  # through the ring and reticle


def test_a_scan_lands_on_the_next_clips_first_frame(tmp_path):
    _wide_still(tmp_path)
    sr_shots, a = _still_assets(tmp_path, [dict(SCAN)], 2.0, mkdir=False)

    class Green:
        def frame(self, i):
            return np.full((1920, 1080, 3), (0.1, 0.8, 0.1), np.float32)

    a.prep["scope"]["hold"] = Green()
    assert sr_shots.frame_at(a, 1.98)[0][800, 700, 1] > 150


LIVE = {"clip": "kling/wide.mp4", "box": [0.5, 0.25, 0.4], "at": 1.0}


def _wide_clip(tmp_path):
    """A 16:9 clip of one green, played inside the wide still."""
    import cv2
    import numpy as np
    (tmp_path / "kling").mkdir()
    out = cv2.VideoWriter(str(tmp_path / "kling" / "wide.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 30, (640, 360))
    for _ in range(60):
        out.write(np.full((360, 640, 3), (30, 200, 30), np.uint8))
    out.release()


def _live_scan(tmp_path):
    _wide_still(tmp_path)
    _wide_clip(tmp_path)
    return _still_assets(tmp_path, [{**SCAN, "path": [[0, 0.7, 0.4], [0.2, 0.7, 0.4]], "live": LIVE}], 2.0, mkdir=False)


def test_a_live_scan_plays_the_clip_inside_the_still(tmp_path):
    """Tony 2026-11-01: the soldier frozen under a moving lens read as a weird pause."""
    sr_shots, a = _live_scan(tmp_path)
    before, start, after = (sr_shots.frame_at(a, t)[0] for t in (0.5, 1.0, 1.5))
    assert before[800, 700, 2] > 150 and before[800, 700, 1] < 60           # the blue of the still
    assert start[800, 700, 2] > 150                                         # the clip fades up, no pop
    assert after[800, 700, 1] > 150 and after[800, 700, 2] < 60             # the clip, running


def test_a_live_scan_leaves_the_still_outside_the_clip(tmp_path):
    sr_shots, a = _live_scan(tmp_path)
    a.prep["scope"]["aim"] = [(600 * a.prep["scope"]["scale"], 360 * a.prep["scope"]["scale"])] * 60
    assert sr_shots.frame_at(a, 1.5)[0][800, 400, 0] > 150                  # the red half, left of the box


def test_a_live_scan_eases_into_the_clip_where_it_has_got_to(tmp_path):
    import numpy as np
    sr_shots, a = _live_scan(tmp_path)
    asked = []

    class Running:
        def frame(self, i):
            asked.append(i)
            return np.zeros((1920, 1080, 3), np.float32)

    a.prep["scope"].update(hold=Running(), hold_at=30)
    sr_shots.frame_at(a, 1.8)
    assert asked == [24]


def test_a_live_scan_hands_on_to_the_clip_at_the_same_moment():
    scan = {"id": "lens", "kind": "scan", "dur": 2.0, "src": "x.png", "path": [[0, 0.2, 0.5], [1, 0.4, 0.5]], "live": LIVE}
    after = {"id": "next", "kind": "clip", "dur": 1.0, "clip": "k.mp4", "start": "s.png", "prompt": CAMERA_PROMPT}
    job = soldier()
    job["shots"] = job["shots"] + [scan, {**after, "in": 0.4}]
    assert any("lens" in p and "`in`" in p for p in sr_lib.validate(job, kling(3.0)))
    job["shots"][-1] = {**after, "in": 1.0}
    assert not any("lens" in p for p in sr_lib.validate(job, kling(3.0)))
    job["shots"] = job["shots"][:-1]
    assert any("lens" in p and "clip after" in p for p in sr_lib.validate(job, kling(3.0)))


def test_a_live_scan_needs_its_clip_on_the_still():
    scan = {"id": "lens", "kind": "scan", "dur": 2.0, "src": "x.png", "path": [[0, 0.2, 0.5], [1, 0.4, 0.5]]}
    job = soldier()
    job["shots"] = job["shots"] + [{**scan, "live": {**LIVE, "box": [0.8, 0.25, 0.4]}}]
    assert any("lens" in p and "`box`" in p for p in sr_lib.validate(job, kling(3.0)))
    job["shots"][-1] = {**scan, "live": {**LIVE, "at": 2.5}}
    assert any("lens" in p and "`at`" in p for p in sr_lib.validate(job, kling(3.0)))
    job["shots"][-1] = {**scan, "live": LIVE}
    problems = sr_lib.validate(job, kling(3.0), exists=lambda path: path != LIVE["clip"])
    assert any(LIVE["clip"] in p for p in problems)


def test_the_hand_carries_on_across_the_cut_out_of_a_scan(tmp_path):
    _wide_still(tmp_path)
    from PIL import Image
    Image.new("RGB", (540, 960), (200, 30, 30)).save(tmp_path / "keys" / "red.png")
    shots = [{**SCAN, "scope": {"sway": 16}},
             {"id": "target", "kind": "clip", "dur": 2.0, "clip": "kling/none.mp4", "start": "keys/red.png",
              "prompt": CAMERA_PROMPT, "scope": {"sway": 16}}]
    sr_shots, a = _still_assets(tmp_path, shots, 4.0, mkdir=False)
    assert a.prep["target"]["scope"]["phase"] == 2.0


def test_a_scan_needs_a_path_on_its_still():
    job = soldier()
    job["shots"] = job["shots"] + [{"id": "lens", "kind": "scan", "dur": 2.0, "src": "x.png", "path": [[0, 1.4, 0.5]]}]
    assert any("lens" in p and "path" in p for p in sr_lib.validate(job, kling(3.0)))
    job["shots"][-1] = {**job["shots"][-1], "path": [[0, 0.2, 0.5], [1, 0.4, 0.5]]}
    assert not any("lens" in p and "path" in p for p in sr_lib.validate(job, kling(3.0)))


def test_a_scope_must_fit_the_frame():
    job = soldier()
    shot(job, "eyes")["scope"] = {"radius": 0.7}
    assert any("eyes" in p and "scope" in p for p in sr_lib.validate(job, kling(3.0)))
    shot(job, "eyes")["scope"] = {"radius": 0.44}
    assert not any("scope" in p for p in sr_lib.validate(job, kling(3.0)))


def test_the_shirt_can_fade_up_from_black(tmp_path):
    """Panel 10: one bang, black, then the shirt fades in, instead of the white-out."""
    from PIL import Image
    Image.new("RGB", (400, 400), (250, 250, 250)).save(tmp_path / "tee.png")
    shots = [{"id": "shirt", "kind": "shirt", "dur": 3.0, "src": "tee.png", "from_black": 1.0, "from_white": 0.0}]
    sr_shots, a = _still_assets(tmp_path, shots, 3.0)
    assert sr_shots.frame_at(a, 0.0)[0].max() < 10
    assert sr_shots.frame_at(a, 1.5)[0][60, 60].min() > 200


def test_a_scope_clip_fills_the_lens_instead_of_stretching_to_9x16():
    import sr_media
    assert "pad=1080:1920" in sr_media.clip_filter(lens=True)
    assert sr_media.clip_filter().startswith("scale=1080:1920")
