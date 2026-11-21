"""Lanes (docs/briefs/2026-10-29-auto-poster.md decisions 4, 6, 9, 12): which lane a job is
in, which channels that lane posts to, and which footer its captions end with. Tech never
carries the DRE line; real estate always does."""
import json

from kit_fixtures import FOOTER, jobs, make_faceless, make_talking_head  # noqa: F401

import lanes  # noqa: E402
import publish_store  # noqa: E402
import th_shorts  # noqa: E402

TAGLINE = "Tech Tony | AI for operators, not engineers | techtony.co"


def test_channels_file_has_every_lane_and_every_lane_channel_is_defined():
    spec = lanes.spec()
    assert set(spec["lanes"]) == {"tech", "realestate", "training"}
    for lane in spec["lanes"].values():
        for key in [*lane["channels"], *lane.get("optional", [])]:
            assert key in spec["channels"], key


def test_tech_and_realestate_channel_lists_match_the_brief():
    assert lanes.lane_channels("tech") == ["me_tiktok", "me_youtube", "me_linkedin", "me_x"]
    assert lanes.lane_channels("realestate") == ["biz_instagram", "biz_facebook", "biz_x", "biz_tiktok",
                                                 "brand_youtube", "me_linkedin"]


def test_default_lane_reads_the_thumbnail_mark():
    assert lanes.default_lane({"thumbnail": {"mark": "TECH TONY"}}) == "tech"
    assert lanes.default_lane({"thumbnail": {"mark": "EXAMPLE REALTY"}}) == "realestate"
    assert lanes.default_lane({"thumbnail": {"mark": "example realty"}}) == "realestate"
    assert lanes.default_lane({}) is None


def test_sidecar_lane_wins_over_the_thumbnail_mark(jobs):
    jdir = make_talking_head(jobs)
    job = json.loads((jdir / "job.json").read_text())
    job["thumbnail"] = {"mark": "EXAMPLE REALTY"}
    (jdir / "job.json").write_text(json.dumps(job))
    assert lanes.job_lane(jdir) == "realestate"
    publish_store.save(jdir, {"lane": "tech"})
    assert lanes.job_lane(jdir) == "tech"


def test_tech_footer_is_the_tagline_and_never_the_dre_line():
    cfg = {"YOUTUBE_FOOTER": FOOTER}
    assert lanes.footer_for("tech", cfg) == TAGLINE
    assert "DRE" not in lanes.footer_for("tech", cfg)


def test_tech_footer_can_be_reworded_in_config():
    assert lanes.footer_for("tech", {"TECHTONY_FOOTER": "Tech Tony | techtony.co"}) == "Tech Tony | techtony.co"


def test_realestate_and_unknown_lanes_keep_the_dre_footer():
    cfg = {"YOUTUBE_FOOTER": FOOTER}
    assert lanes.footer_for("realestate", cfg) == FOOTER
    assert lanes.footer_for(None, cfg) == FOOTER


def test_a_footer_authored_in_the_job_wins():
    job = {"youtube": {"footer": "Custom\\nfooter"}}
    assert lanes.footer_for("tech", {}, job) == "Custom\nfooter"


def test_shorts_kit_of_a_tech_job_ends_with_the_tagline_not_the_dre_line(jobs):
    jdir = make_faceless(jobs)
    publish_store.save(jdir, {"lane": "tech"})
    text = th_shorts.write_kit(jdir.name).read_text()
    assert TAGLINE in text
    assert "DRE" not in text


def test_shorts_kit_of_a_realestate_job_keeps_the_dre_line(jobs):
    jdir = make_faceless(jobs)
    publish_store.save(jdir, {"lane": "realestate"})
    assert FOOTER in th_shorts.write_kit(jdir.name).read_text()


def test_ai_footage_comes_from_clip_scenes_or_an_rf_folder(jobs):
    jdir = make_faceless(jobs)
    assert not lanes.ai_footage(jdir)
    (jdir / "rf").mkdir()
    assert lanes.ai_footage(jdir)
