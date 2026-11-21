"""Shorts cut from a finished talking-head video. Segments are written as spoken phrases,
resolved against the burned-in captions (transcript.srt, output timeline), so a cut
always starts and ends on a caption boundary instead of mid-word."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import th_shorts  # noqa: E402

SRT = """1
00:00:00,300 --> 00:00:02,000
In Ogdenville, you can't legally

2
00:00:02,000 --> 00:00:04,500
collect rent until you have a piece of paper.

3
00:00:04,500 --> 00:00:07,250
Not a permit to build, not a business license.

4
00:01:02,000 --> 00:01:05,100
That number belongs in your offer.
"""


def test_parse_srt_reads_times_and_text():
    cues = th_shorts.parse_srt(SRT)
    assert len(cues) == 4
    assert cues[0][:2] == pytest.approx((0.3, 2.0))
    assert cues[3][0] == pytest.approx(62.0)
    assert "offer" in cues[3][2]


def test_resolve_starts_at_the_cue_holding_the_start_phrase():
    cues = th_shorts.parse_srt(SRT)
    start, end = th_shorts.resolve(cues, "collect rent until", "belongs in your offer")
    assert start == pytest.approx(2.0)
    assert end == pytest.approx(65.1)


def test_resolve_ignores_case_and_punctuation():
    cues = th_shorts.parse_srt(SRT)
    start, _ = th_shorts.resolve(cues, "IN OGDENVILLE you cant", "business license")
    assert start == pytest.approx(0.3)


def test_resolve_phrase_spanning_two_cues():
    cues = th_shorts.parse_srt(SRT)
    start, end = th_shorts.resolve(cues, "can't legally collect rent", "paper")
    assert start == pytest.approx(0.3)
    assert end == pytest.approx(4.5)


def test_resolve_missing_phrase_raises():
    cues = th_shorts.parse_srt(SRT)
    with pytest.raises(ValueError):
        th_shorts.resolve(cues, "not in the video", "offer")


def test_resolve_end_before_start_raises():
    cues = th_shorts.parse_srt(SRT)
    with pytest.raises(ValueError):
        th_shorts.resolve(cues, "belongs in your offer", "In Ogdenville")


def test_check_length_flags_long_and_short():
    assert th_shorts.check_length(0, 45) == []
    assert th_shorts.check_length(0, 181)    # YouTube's Shorts limit is 180 s since 2024-10-15
    assert th_shorts.check_length(0, 8)


JOB = {"title": "Rent Control, City by City #2: Ogdenville",
       "youtube": {"title": "Ogdenville Rent Control: Can You Still Raise the Rent?",
                   "hashtags": ["#RentControl", "Ogdenville", "#Landlord"]}}
SHORT = {"start": "a", "end": "b", "hook": "H", "title": "Ogdenville Move-Out Costs 4x",
         "description": "In Ogdenville a no-fault move-out starts at three times the rent."}
FOOTER = "Tony Self, Broker, CA DRE #00000001"


def test_copy_has_title_description_episode_hashtags_and_footer():
    copy = th_shorts.short_copy(SHORT, JOB, FOOTER)
    assert copy["title"] == "Ogdenville Move-Out Costs 4x"
    body = copy["description"]
    assert body.startswith("In Ogdenville a no-fault move-out")
    assert "Ogdenville Rent Control: Can You Still Raise the Rent?" in body
    assert "#RentControl #Ogdenville #Landlord" in body
    assert body.rstrip().endswith("Tony Self, Broker, CA DRE 00000001")
    assert "#Shorts" not in body


def test_copy_drops_pound_sign_from_license_numbers():
    body = th_shorts.short_copy({**SHORT, "description": "Call me. DRE #00000001"}, JOB, FOOTER)["description"]
    assert "#0" not in body


def test_copy_uses_episode_url_when_known():
    job = {**JOB, "youtube": {**JOB["youtube"], "url": "https://youtu.be/cSQI3mSHgVA"}}
    assert "https://youtu.be/cSQI3mSHgVA" in th_shorts.short_copy(SHORT, job, FOOTER)["description"]


def test_standalone_short_has_no_full_episode_line():
    body = th_shorts.short_copy({**SHORT, "standalone": True}, JOB, FOOTER)["description"]
    assert "Full episode" not in body
    assert "Ogdenville Rent Control: Can You Still Raise the Rent?" not in body
    assert body.startswith("In Ogdenville a no-fault move-out")
    assert body.rstrip().endswith("Tony Self, Broker, CA DRE 00000001")


def test_copy_without_description_falls_back_to_episode_line():
    short = {k: v for k, v in SHORT.items() if k != "description"}
    body = th_shorts.short_copy(short, JOB, FOOTER)["description"]
    assert body.startswith("From the full episode")


def test_copy_flags_em_dash_and_long_title():
    bad = {**SHORT, "title": "x" * 101, "description": "Rent — capped"}
    assert len(th_shorts.copy_problems(bad)) == 2
    assert th_shorts.copy_problems(SHORT) == []


def test_editing_copy_does_not_void_cut_approval():
    edited = [{**SHORT, "title": "New", "description": "New"}]
    assert th_shorts.fingerprint([SHORT]) == th_shorts.fingerprint(edited)
    moved = [{**SHORT, "hook": "Other"}]
    assert th_shorts.fingerprint([SHORT]) != th_shorts.fingerprint(moved)


def _job(tmp_path, monkeypatch, shorts):
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "transcript.srt").write_text(SRT)
    (tmp_path / "job.json").write_text(__import__("json").dumps({"shorts": shorts}))
    monkeypatch.setattr(th_shorts.common, "job_dir", lambda _job: tmp_path)
    return th_shorts.load("job")[3]


def test_tail_keeps_picture_past_the_last_word(tmp_path, monkeypatch):
    resolved = _job(tmp_path, monkeypatch, [
        {"start": "In Ogdenville", "end": "business license", "tail": 2.5},
        {"start": "In Ogdenville", "end": "business license"}])
    assert resolved[0]["to"] == pytest.approx(7.25 + 2.5)
    assert resolved[1]["to"] == pytest.approx(7.25)


def test_tail_is_clamped(tmp_path, monkeypatch):
    resolved = _job(tmp_path, monkeypatch, [
        {"start": "In Ogdenville", "end": "business license", "tail": 30},
        {"start": "In Ogdenville", "end": "business license", "tail": -5}])
    assert resolved[0]["to"] == pytest.approx(7.25 + th_shorts.MAX_TAIL)
    assert resolved[1]["to"] == pytest.approx(7.25)


def test_changing_tail_voids_cut_approval():
    base = {"start": "a", "end": "b", "hook": "H"}
    assert th_shorts.fingerprint([base]) != th_shorts.fingerprint([{**base, "tail": 2.5}])


def test_split_jobs_get_the_brokerage_banner(tmp_path):
    # Tony, 2026-10-14: Brokerage blue with a light blue outline instead of yellow
    assert th_shorts.banner_for({"layout": "split"}) == th_shorts.BANNERS["brokerage"]
    assert th_shorts.banner_for({"style": "board"}) == th_shorts.BANNERS["default"]
    png = th_shorts.hook_png("TEXAS TAX: 2X CALIFORNIA", tmp_path / "hook.png", banner=th_shorts.BANNERS["brokerage"])
    from PIL import Image
    image = Image.open(png).convert("RGB")
    top = th_shorts.HOOK_TOP
    assert image.getpixel((th_shorts.W // 2, top + 2)) == (41, 168, 214)        # light blue border
    assert image.getpixel((th_shorts.W // 2 - 440, top + 40)) == (29, 53, 87)    # Brokerage blue fill


def test_opener_and_banner_edits_void_cut_approval():
    base = {"start": "a", "end": "b", "hook": "H"}
    assert th_shorts.fingerprint([base]) != th_shorts.fingerprint([{**base, "opener": {"type": "number", "text": "X"}}])
    assert th_shorts.fingerprint([base]) != th_shorts.fingerprint([{**base, "banner": "red"}])


def test_each_short_gets_its_own_banner(tmp_path, monkeypatch):
    resolved = _job(tmp_path, monkeypatch, [
        {"start": "In Ogdenville", "end": "business license", "hook": "H", "banner": "red"},
        {"start": "In Ogdenville", "end": "business license", "hook": "",
         "opener": {"type": "number", "text": "$10,500"}}])
    assert resolved[0]["banner"] == th_shorts.BANNERS["red"]
    assert resolved[1]["banner"] is None


def test_no_banner_means_a_clear_overlay(tmp_path):
    from PIL import Image
    png = th_shorts.hook_png("ANYTHING", tmp_path / "hook.png", banner=None)
    assert Image.open(png).getextrema()[3] == (0, 0)          # alpha channel all zero
