"""Row B in fv.py publish: on the table first, its link in every caption before it is live,
published at Go before anything reaches Blotato, and a failed blog stops the Shorts. The site
repo work is replaced (test_publish_blog.py covers it against a real git repo)."""
import pytest

from kit_fixtures import YOUTUBE, jobs  # noqa: F401
from test_publish_command import make_job, record, run, world  # noqa: F401

import kit_links  # noqa: E402
import lanes  # noqa: E402
import publish_blog  # noqa: E402

URL = "https://sitetwo.com/news/springfield-rent-hearings"


@pytest.fixture
def blog(world, monkeypatch):
    calls = {"plan": [], "publish": [], "fail": None, "problems": [], "live": [True]}

    def plan_row(jdir, lane, override, vid, links, day):
        path = jdir / "out" / "blog.md"
        if not path.exists():
            return None
        calls["plan"].append(override)
        site = "siteone" if override else "sitetwo"
        return {"id": "B", "kind": "blog", "file": "blog.md", "title": "Springfield", "seconds": 0,
                "slug": "springfield-rent-hearings", "site": site, "site_why": "topic",
                "url": URL.replace("sitetwo", site), "action": "add", "category": "Rent Control", "note": "",
                "library": "adds the video library entry", "entry": '  {\n    slug: "springfield-rent-hearings",\n  },\n',
                "entry_sha": str(len(path.read_text())), "problems": list(calls["problems"])}

    def publish_row(jdir, row, vid, links, at):
        if calls["fail"]:
            raise RuntimeError(calls["fail"])
        calls["publish"].append((row["url"], vid, len(world["sent"])))
        return {"status": "published", "action": "add", "url": row["url"], "commit": "abc1234",
                "at": at.isoformat(), "live": calls["live"][0], "library": row["library"]}

    monkeypatch.setattr(publish_blog, "plan_row", plan_row)
    monkeypatch.setattr(publish_blog, "publish", publish_row)
    monkeypatch.setattr(publish_blog, "wait_live", lambda url, vid, log=print: calls["live"][0])
    spec = lanes.spec()                               # Brand YouTube's id is confirmed here
    spec["channels"]["brand_youtube"] = {**spec["channels"]["brand_youtube"], "verified": True}
    monkeypatch.setattr(lanes, "spec", lambda: spec)
    return calls


def make_blog_job(root):
    jdir = make_job(root)
    (jdir / "out" / "blog.md").write_text("---\nslug: springfield-rent-hearings\n---\n\nText.\n")
    return jdir


def test_row_b_leads_the_table_and_its_link_is_in_the_captions(world, blog, jobs, capsys):
    jdir = make_blog_job(jobs)
    run(jdir.name, "--lane", "realestate", "--youtube", YOUTUBE)
    out = capsys.readouterr().out
    assert [r["id"] for r in record(jdir)["rows"]] == ["B", "1", "2", "L"]
    assert "sitetwo.com/news/springfield-rent-hearings (Rent Control, new post)" in out
    preview = (jdir / "out" / "publish_preview.md").read_text()
    assert f"{kit_links.BLOG_MARK} {URL}" in preview and "## B blog.md" in preview


def test_go_publishes_the_blog_before_any_short_and_records_the_link(world, blog, jobs):
    jdir = make_blog_job(jobs)
    run(jdir.name, "--lane", "realestate", "--youtube", YOUTUBE)
    run(jdir.name, "--go")
    assert blog["publish"] == [(URL, YOUTUBE, 0)]          # nothing in Blotato yet when the blog went
    assert world["sent"] and all(URL in b["post"]["content"]["text"] for b in world["sent"]
                                 if b["post"]["accountId"] != "90003")
    rows = {r["id"]: r for r in record(jdir)["rows"]}
    assert rows["B"]["status"] == "published" and rows["B"]["commit"] == "abc1234"
    assert kit_links.load(jdir)["blog_url"] == URL


def test_a_failed_blog_stops_the_shorts(world, blog, jobs):
    jdir = make_blog_job(jobs)
    run(jdir.name, "--lane", "realestate", "--youtube", YOUTUBE)
    blog["fail"] = "build failed"
    with pytest.raises(SystemExit):
        run(jdir.name, "--go")
    assert world["sent"] == []
    assert {r["id"]: r for r in record(jdir)["rows"]}["B"].get("status") is None


def test_rerunning_go_never_publishes_the_blog_twice(world, blog, jobs):
    jdir = make_blog_job(jobs)
    run(jdir.name, "--lane", "realestate", "--youtube", YOUTUBE)
    run(jdir.name, "--go")
    planned = len(blog["plan"])
    run(jdir.name, "--go")
    assert len(blog["publish"]) == 1 and len(blog["plan"]) == planned


def test_drop_b_posts_the_shorts_without_the_blog_or_its_link(world, blog, jobs):
    jdir = make_blog_job(jobs)
    run(jdir.name, "--lane", "realestate", "--youtube", YOUTUBE, "--drop", "B")
    run(jdir.name, "--go")
    assert blog["publish"] == []
    assert world["sent"] and not any(URL in b["post"]["content"]["text"] for b in world["sent"])


def test_an_edit_to_blog_md_after_the_table_stops_go(world, blog, jobs, capsys):
    jdir = make_blog_job(jobs)
    run(jdir.name, "--lane", "realestate", "--youtube", YOUTUBE)
    (jdir / "out" / "blog.md").write_text("---\nslug: springfield-rent-hearings\n---\n\nNew text, longer.\n")
    run(jdir.name, "--go")
    assert blog["publish"] == [] and world["sent"] == []
    assert "review it, then --go again" in capsys.readouterr().out


def test_a_blog_problem_blocks_go_until_b_is_dropped(world, blog, jobs, capsys):
    jdir = make_blog_job(jobs)
    blog["problems"] = ["blog.md has no excerpt or meta_description"]
    run(jdir.name, "--lane", "realestate", "--youtube", YOUTUBE)
    assert "BLOCKED" in capsys.readouterr().out
    with pytest.raises(SystemExit):
        run(jdir.name, "--go")
    assert world["sent"] == []
    run(jdir.name, "--drop", "B")
    run(jdir.name, "--go")
    assert world["sent"]


def test_short_route_blog_needs_the_unlisted_video_id(world, blog, jobs):
    jdir = make_blog_job(jobs)
    run(jdir.name, "--lane", "realestate", "--route", "short")
    with pytest.raises(SystemExit):
        run(jdir.name, "--go")
    assert world["sent"] == [] and blog["publish"] == []


def test_site_flag_reaches_the_planner_and_is_remembered(world, blog, jobs):
    jdir = make_blog_job(jobs)
    run(jdir.name, "--lane", "realestate", "--youtube", YOUTUBE, "--site", "siteone.com")
    run(jdir.name)
    assert blog["plan"] == ["siteone.com", "siteone.com"]
    assert record(jdir)["blog_url"] == "https://siteone.com/news/springfield-rent-hearings"


def test_the_blog_cannot_be_pinned_or_dropped_once_live(world, blog, jobs):
    jdir = make_blog_job(jobs)
    with pytest.raises(SystemExit):
        run(jdir.name, "--lane", "realestate", "--at", "B=2026-10-31T15:00")
    run(jdir.name, "--lane", "realestate", "--youtube", YOUTUBE)
    run(jdir.name, "--go")
    with pytest.raises(SystemExit):
        run(jdir.name, "--edit", "--drop", "B")


def test_a_job_without_blog_md_has_no_row_b(world, blog, jobs):
    jdir = make_job(jobs)
    run(jdir.name, "--lane", "tech", "--youtube", YOUTUBE)
    assert [r["id"] for r in record(jdir)["rows"]] == ["1", "2", "L"]
    assert blog["plan"] == []


def test_a_pushed_blog_that_is_not_live_holds_the_shorts_until_it_is(world, blog, jobs):
    jdir = make_blog_job(jobs)
    run(jdir.name, "--lane", "realestate", "--youtube", YOUTUBE)
    blog["live"] = [False]
    with pytest.raises(SystemExit):
        run(jdir.name, "--go")
    assert world["sent"] == [] and len(blog["publish"]) == 1
    with pytest.raises(SystemExit):
        run(jdir.name, "--go")                      # still not live: re-checked, not pushed again
    assert world["sent"] == [] and len(blog["publish"]) == 1
    blog["live"] = [True]
    run(jdir.name, "--go")
    assert len(blog["publish"]) == 1 and world["sent"]
    assert {r["id"]: r for r in record(jdir)["rows"]}["B"]["live"] is True


def test_uploaded_lands_in_links_json(world, blog, jobs):
    jdir = make_blog_job(jobs)
    run(jdir.name, "--lane", "realestate", "--youtube", YOUTUBE, "--uploaded", "2026-10-29")
    assert kit_links.load(jdir)["upload_date"] == "2026-10-29"
