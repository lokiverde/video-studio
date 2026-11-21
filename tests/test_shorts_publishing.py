"""Shorts copy under the 2026-10-22 publishing rules: 180 second limit, the scheduler's 50 MiB
cap, the article link first, the related-video reminder after a long-form route, no #Shorts,
and byte-identical output for a job with none of the new fields."""
import json

from kit_fixtures import BLOG, FACELESS_ID, FOOTER, SHORTS_JOB, jobs, make_faceless, patch_length  # noqa: F401

import common  # noqa: E402
import format_route  # noqa: E402
import kit_links  # noqa: E402
import th_shorts  # noqa: E402


def _old_kit(job):
    """shorts.md exactly as write_kit wrote it before links and routes existed."""
    lines = [f"# Shorts: {job['title']}\n", "Same description for YouTube Shorts, TikTok and Reels.\n"]
    for n, short in enumerate(job["shorts"], 1):
        copy = th_shorts.short_copy(short, job, FOOTER)
        lines.append(f"\n## short_{n}.mp4\n\nTitle:\n```\n{copy['title']}\n```\n\n"
                     f"Description:\n```\n{copy['description']}\n```\n")
    return "".join(lines)


def test_shorts_run_to_180_seconds():
    assert th_shorts.check_length(0, 150) == []
    assert th_shorts.check_length(0, 180) == []
    assert "over 180s" in th_shorts.check_length(0, 181)[0]


def test_postdeck_cap_warns_above_50_mib():
    assert th_shorts.size_problems(28 * 1024 * 1024) == []
    assert "50 MiB" in th_shorts.size_problems(5.0e6 * 180 / 8)[0]     # 180 s at 5 Mbps is about 107 MiB


def test_a_job_with_no_new_fields_writes_the_same_shorts_md(jobs):
    jdir = make_faceless(jobs)
    th_shorts.write_kit(FACELESS_ID)
    assert (jdir / "out" / "shorts.md").read_text() == _old_kit(SHORTS_JOB)


def test_the_article_link_leads_and_the_episode_line_follows(jobs):
    jdir = make_faceless(jobs)
    kit_links.save(jdir, blog_url=BLOG)
    th_shorts.write_kit(FACELESS_ID)
    md = (jdir / "out" / "shorts.md").read_text()
    first = md.split("Description:\n```\n")[1].split("\n```")[0]
    assert first.startswith(f"Written version with sources: {BLOG}\n\nFrom the full episode: ")
    assert "#Shorts" not in md


def test_long_route_adds_the_related_video_reminder_to_every_short(jobs, monkeypatch):
    patch_length(monkeypatch, 240.0)
    jdir = make_faceless(jobs)
    format_route.write(jdir, chapters=5, fmt="faceless")
    th_shorts.write_kit(FACELESS_ID)
    md = (jdir / "out" / "shorts.md").read_text()
    assert md.count(th_shorts.RELATED_NOTES["LONG"]) == len(SHORTS_JOB["shorts"])
    # the reminder sits outside the paste-ready description block
    assert th_shorts.RELATED_NOTES["LONG"] not in md.split("Description:\n```\n")[1].split("\n```")[0]


def test_short_route_adds_no_reminder(jobs, monkeypatch):
    patch_length(monkeypatch, 60.0)
    jdir = make_faceless(jobs)
    format_route.write(jdir, chapters=1, fmt="faceless")
    th_shorts.write_kit(FACELESS_ID)
    assert "related video" not in (jdir / "out" / "shorts.md").read_text()


def test_weak_short_titles_warn_but_are_never_edited(jobs, capsys):
    jdir = make_faceless(jobs)
    job = {**SHORTS_JOB, "shorts": [{**SHORTS_JOB["shorts"][0], "title": "My one rule before I type anything into AI"}]}
    (jdir / "job.json").write_text(json.dumps(job))
    th_shorts.write_kit(FACELESS_ID)
    out = capsys.readouterr().out
    assert "#1 TITLE: no city, law or number in the first 40 characters" in out
    assert "My one rule before I type anything into AI" in (jdir / "out" / "shorts.md").read_text()
    assert common.get_state(FACELESS_ID).get("scene_durations")     # state untouched apart from the kit


def test_dashes_never_reach_shorts_md(jobs):
    jdir = make_faceless(jobs)
    job = {**SHORTS_JOB, "shorts": [{**SHORTS_JOB["shorts"][1], "title": "Springfield fees \u2014 2026",
                                     "description": "Line one \u2013 two.\nLine three."}]}
    (jdir / "job.json").write_text(json.dumps(job))
    th_shorts.write_kit(FACELESS_ID)
    md = (jdir / "out" / "shorts.md").read_text()
    assert "\u2014" not in md and "\u2013" not in md
    assert "Springfield fees, 2026" in md and "Line one, two.\nLine three." in md


def test_the_kit_names_the_cover_once_cut_writes_it(jobs):
    jdir = make_faceless(jobs)
    (jdir / "out" / "short_1_cover.jpg").write_bytes(b"jpg")
    th_shorts.write_kit(FACELESS_ID)
    md = (jdir / "out" / "shorts.md").read_text()
    assert "Custom thumbnail: short_1_cover.jpg" in md
    assert "short_2_cover.jpg" not in md
