"""The blog publisher against a real git repo: a local bare origin with the my-sites
layout, its own clone, the build stubbed. Covers which site a post goes to, the plan-time
row, the add-only commit, the build gate, a push that loses the race, and a post that is
already live."""
import json
import sys
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

import kit_fixtures  # noqa: F401  (puts scripts/ on the path)
import blog_md  # noqa: E402
import publish_blog  # noqa: E402
import publish_plan as pp  # noqa: E402

VID = "AbCdEfGhIjK"
LINKS = {"upload_date": "2026-10-28"}
AT = datetime(2026, 10, 30, 8, 0, tzinfo=pp.TZ)
POSTS = '''export const POSTS: NewsPost[] = [
  {
    // videoId added once the YouTube link for this episode is supplied.
    slug: "shelbyville-rent-control-2026",
    title: "Shelbyville",
    category: "Rent Control",
    date: "2026-10-25",
    excerpt: "Shelbyville.",
    body: [
      "Intro.",
    ],
  },
  {
    slug: "northside-mobilehome-2026",
    title: "Carson",
    category: "Compliance",
    date: "2026-10-25",
    videoId: "I9wz9_P_W5w",
    excerpt: "Carson.",
    body: [
      "Text.",
    ],
  },
];
'''
LIBRARY = 'export const VIDEO_LIBRARY: VideoEntry[] = [\n  {\n    "id": "I9wz9_P_W5w"\n  },\n];\n'
BLOG = """---
slug: springfield-rent-hearings
title: "Springfield Has No Rent Control. Why Can Tenants Get a Hearing?"
excerpt: "A rent hearing still applies over 5%."
tags: [springfield, landlord]
---

Springfield has no rent cap.

[VIDEO]

## The 5% line

Text.
"""
ENTRY = ('// VIDEO_LIBRARY entry\n{\n  "id": "TODO_YOUTUBE_ID",\n  "title": "Springfield",\n'
         '  "uploadDate": "TODO_UPLOAD_DATE",\n  "ownerUrl": "TODO_ARTICLE_URL"\n},\n')
FILES = {"apps/sitetwo/src/app/news/posts-data.ts": POSTS,
         "apps/siteone/src/app/news/posts-data.ts": "export const POSTS: NewsPost[] = [];\n",
         "apps/sitethree/src/app/blog/posts-data.ts": "export const POSTS: BlogPost[] = [];\n",
         "apps/examplerealty/src/app/news/posts-data.ts": "export const POSTS: NewsPost[] = [];\n",
         "apps/examplerealty/src/app/news/network-feed.ts": "export const NETWORK_FEED = [];\n",
         "packages/ui/src/video-library.ts": LIBRARY}
FEED = "apps/examplerealty/src/app/news/network-feed.ts"
# feed:build stand-in: the feed changes whenever the sitetwo posts file does
FEED_CMD = [sys.executable, "-c", f"import pathlib; p = pathlib.Path('{FEED}'); "
            "p.write_text('export const NETWORK_FEED = [' + str(len(pathlib.Path("
            "'apps/sitetwo/src/app/news/posts-data.ts').read_text())) + '];\\n')"]


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def world(tmp_path, monkeypatch):
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    seed = tmp_path / "seed"
    git(tmp_path, "clone", "-q", str(origin), str(seed))
    git(seed, "config", "user.email", "seed@example.com")
    git(seed, "config", "user.name", "seed")
    for rel, text in FILES.items():
        (seed / rel).parent.mkdir(parents=True, exist_ok=True)
        (seed / rel).write_text(text)
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "seed")
    git(seed, "push", "-q", "origin", "HEAD:main")
    cfg = json.loads(publish_blog.SITES_FILE.read_text())
    cfg["clones"] = str(tmp_path / "clones")
    repo = cfg["repos"]["my-sites"]
    cfg["repos"]["my-sites"] = {**repo, "remote": str(origin), "install": [], "after_write": [FEED_CMD],
                                     "build": ["true"], "indexnow": ["true"]}
    monkeypatch.setattr(publish_blog, "config", lambda: cfg)
    lives = []
    monkeypatch.setattr(publish_blog, "wait_live", lambda url, vid, log=print: lives.append(url) or True)
    jdir = tmp_path / "job"
    (jdir / "out").mkdir(parents=True)
    (jdir / "out" / "blog.md").write_text(BLOG)
    (jdir / "out" / "video_library_entry.txt").write_text(ENTRY)
    return {"origin": origin, "seed": seed, "cfg": cfg, "jdir": jdir, "lives": lives, "tmp": tmp_path}


# ---- which site ---------------------------------------------------------------------------------

def _p(**kw):
    return {**blog_md.post("---\nslug: a\ntitle: T\nexcerpt: E\n---\n\nX\n"), **kw}


def test_site_comes_from_the_flag_then_blog_md_then_the_lane_then_the_topic():
    cfg = json.loads(publish_blog.SITES_FILE.read_text())
    assert publish_blog.choose_site(_p(site="sitetwo.com"), "tech", "sitethree.com", cfg)[0] == "sitethree"
    assert publish_blog.choose_site(_p(site="siteone.com/news"), "tech", None, cfg)[0] == "siteone"
    assert publish_blog.choose_site(_p(site="https://www.TechTony.co"), "realestate", None, cfg)[0] == "techtony"
    assert publish_blog.choose_site(_p(), "tech", None, cfg)[0] == "techtony"
    assert publish_blog.choose_site(_p(title="Two HOA reserve deadlines"), "realestate", None, cfg)[0] == "sitethree"
    assert publish_blog.choose_site(_p(title="Landlords: the rent control map"), "realestate", None, cfg)[0] == "sitetwo"
    assert publish_blog.choose_site(_p(title="Pending home sales are down"), "realestate", None, cfg)[0] == "siteone"


def test_the_training_lane_files_its_posts_as_agent_training_on_examplerealty():
    cfg = json.loads(publish_blog.SITES_FILE.read_text())
    post = _p(category="Education")
    assert publish_blog.lane_category(post, "training", "examplerealty", cfg)["category"] == "Agent Training"
    assert post["category"] == "Education"                       # never mutates the post
    # --site sent it somewhere else, or another lane: the post keeps its own category
    assert publish_blog.lane_category(post, "training", "siteone", cfg)["category"] == "Education"
    assert publish_blog.lane_category(post, "tech", "techtony", cfg)["category"] == "Education"
    assert publish_blog.lane_category(post, "realestate", "examplerealty", cfg)["category"] == "Education"


def test_an_unknown_site_is_refused():
    cfg = json.loads(publish_blog.SITES_FILE.read_text())
    with pytest.raises(ValueError):
        publish_blog.choose_site(_p(site="myspace.com"), "tech", None, cfg)


# ---- the plan-time row ----------------------------------------------------------------------------

def test_plan_row_predicts_the_url_category_and_library(world):
    row = publish_blog.plan_row(world["jdir"], "realestate", None, VID, LINKS, AT.date())
    assert row["id"] == "B" and row["kind"] == "blog" and row["problems"] == []
    assert row["site"] == "sitetwo" and row["url"] == "https://sitetwo.com/news/springfield-rent-hearings"
    assert row["action"] == "add" and row["category"] == "Rent Control"
    assert row["library"] == "adds the video library entry"
    assert 'slug: "springfield-rent-hearings"' in row["entry"]


def test_plan_row_moves_to_the_site_that_already_has_the_slug(world):
    blog = BLOG.replace("springfield-rent-hearings", "shelbyville-rent-control-2026")
    (world["jdir"] / "out" / "blog.md").write_text(blog.replace("---\nslug", "---\nsite: siteone.com\nslug", 1))
    row = publish_blog.plan_row(world["jdir"], "realestate", None, VID, {}, AT.date())
    assert row["site"] == "sitetwo" and row["action"] == "fill"
    assert "already" in row["site_why"]


def test_plan_row_without_blog_md_is_none(world):
    (world["jdir"] / "out" / "blog.md").unlink()
    assert publish_blog.plan_row(world["jdir"], "realestate", None, VID, {}, AT.date()) is None


def test_plan_row_reports_blog_problems_instead_of_raising(world):
    (world["jdir"] / "out" / "blog.md").write_text("---\ntitle: T\n---\n\nX\n")
    row = publish_blog.plan_row(world["jdir"], "realestate", None, VID, {}, AT.date())
    assert row["problems"] and row["url"] is None


# ---- Go -----------------------------------------------------------------------------------------------

def test_publish_commits_only_the_post_library_and_feed_then_pushes(world):
    row = publish_blog.plan_row(world["jdir"], "realestate", None, VID, LINKS, AT.date())
    result = publish_blog.publish(world["jdir"], row, VID, LINKS, AT)
    assert result["status"] == "published" and result["action"] == "add"
    assert result["url"] == "https://sitetwo.com/news/springfield-rent-hearings"
    git(world["seed"], "fetch", "-q")
    changed = git(world["seed"], "show", "--name-only", "--format=", "origin/main").split("\n")
    assert sorted(changed) == sorted(["apps/sitetwo/src/app/news/posts-data.ts", FEED, "packages/ui/src/video-library.ts"])
    assert git(world["seed"], "log", "-1", "--format=%ae", "origin/main") == "you@example.com"
    posts = git(world["seed"], "show", "origin/main:apps/sitetwo/src/app/news/posts-data.ts")
    assert posts.index("springfield-rent-hearings") < posts.index("shelbyville-rent-control-2026")
    assert '    date: "2026-10-30",' in posts
    library = git(world["seed"], "show", "origin/main:packages/ui/src/video-library.ts")
    assert f'"id": "{VID}"' in library and '"ownerUrl": "https://sitetwo.com/news/springfield-rent-hearings"' in library
    assert '"uploadDate": "2026-10-28"' in library
    assert world["lives"] == [result["url"]]


def test_a_training_lane_post_lands_on_examplerealty_as_agent_training(world):
    row = publish_blog.plan_row(world["jdir"], "training", None, VID, LINKS, AT.date())
    assert row["problems"] == [] and row["site"] == "examplerealty"
    assert row["category"] == "Agent Training" and row["want_category"] == "Agent Training"
    result = publish_blog.publish(world["jdir"], row, VID, LINKS, AT)
    assert result["status"] == "published" and result["url"] == "https://brokerage.example/news/springfield-rent-hearings"
    git(world["seed"], "fetch", "-q")
    posts = git(world["seed"], "show", "origin/main:apps/examplerealty/src/app/news/posts-data.ts")
    assert 'category: "Agent Training",' in posts


def test_a_failed_build_pushes_nothing_and_leaves_the_clone_clean(world):
    world["cfg"]["repos"]["my-sites"]["build"] = ["false"]
    row = publish_blog.plan_row(world["jdir"], "realestate", None, VID, {}, AT.date())
    with pytest.raises(RuntimeError):
        publish_blog.publish(world["jdir"], row, VID, {}, AT)
    clone = publish_blog.clone_dir("my-sites", world["cfg"])
    assert git(clone, "status", "--porcelain", "--untracked-files=no") == ""
    git(world["seed"], "fetch", "-q")
    assert git(world["seed"], "log", "--format=%s", "origin/main") == "seed"


def test_a_push_that_loses_the_race_is_redone_on_the_new_origin(world, monkeypatch):
    row = publish_blog.plan_row(world["jdir"], "realestate", None, VID, {}, AT.date())
    real_run, raced = publish_blog.run, []

    def run(cmd, cwd, timeout=900, strip=True):
        if cmd == ["true"] and not raced:          # the build: the Mac mini pushes meanwhile
            raced.append(1)
            other = world["seed"] / "apps/sitetwo/src/app/news/posts-data.ts"
            other.write_text(other.read_text().replace("export const POSTS: NewsPost[] = [\n",
                             'export const POSTS: NewsPost[] = [\n  {\n    slug: "other-post",\n  },\n', 1))
            git(world["seed"], "commit", "-q", "-am", "other")
            git(world["seed"], "push", "-q", "origin", "HEAD:main")
        return real_run(cmd, cwd, timeout, strip)

    monkeypatch.setattr(publish_blog, "run", run)
    result = publish_blog.publish(world["jdir"], row, VID, {}, AT)
    assert result["status"] == "published"
    git(world["seed"], "fetch", "-q")
    assert git(world["seed"], "log", "--format=%s", "-3", "origin/main").split("\n")[1:] == ["other", "seed"]
    posts = git(world["seed"], "show", "origin/main:apps/sitetwo/src/app/news/posts-data.ts")
    assert "other-post" in posts and "springfield-rent-hearings" in posts


def test_a_post_that_already_has_its_video_changes_nothing(world):
    blog = BLOG.replace("springfield-rent-hearings", "northside-mobilehome-2026")
    (world["jdir"] / "out" / "blog.md").write_text(blog)
    carson = "I9wz9_P_W5w"
    row = publish_blog.plan_row(world["jdir"], "realestate", None, carson, {}, AT.date())
    assert row["action"] == "live" and row["problems"] == []
    result = publish_blog.publish(world["jdir"], row, carson, {}, AT)
    assert result["action"] == "live" and result["commit"] is None
    git(world["seed"], "fetch", "-q")
    assert git(world["seed"], "log", "--format=%s", "origin/main") == "seed"


def test_a_dirty_clone_is_refused(world):
    row = publish_blog.plan_row(world["jdir"], "realestate", None, VID, {}, AT.date())
    clone = publish_blog.clone_dir("my-sites", world["cfg"])
    (clone / FEED).write_text("hand edit\n")
    with pytest.raises(RuntimeError, match="uncommitted"):
        publish_blog.publish(world["jdir"], row, VID, {}, AT)


def test_techtony_post_carries_the_thumbnail_as_its_featured_image(world):
    origin = world["tmp"] / "techtony.git"
    git(world["tmp"], "init", "-q", "--bare", "-b", "main", str(origin))
    seed = world["tmp"] / "tseed"
    git(world["tmp"], "clone", "-q", str(origin), str(seed))
    git(seed, "config", "user.email", "seed@example.com")
    git(seed, "config", "user.name", "seed")
    (seed / "src/lib").mkdir(parents=True)
    (seed / "src/lib/blog-data.ts").write_text("export const blogPosts: BlogPost[] = [\n  // October 2026\n];\n")
    git(seed, "add", "-A")
    git(seed, "commit", "-q", "-m", "seed")
    git(seed, "push", "-q", "origin", "HEAD:main")
    repo = world["cfg"]["repos"]["tech-site"]
    world["cfg"]["repos"]["tech-site"] = {**repo, "remote": str(origin), "install": [], "build": ["true"],
                                              "indexnow": ["true"]}
    (world["jdir"] / "out" / "thumbnail.jpg").write_bytes(b"jpeg")
    row = publish_blog.plan_row(world["jdir"], "tech", None, VID, {}, AT.date())
    assert row["site"] == "techtony" and row["url"] == "https://www.techtony.co/blog/springfield-rent-hearings"
    assert row["library"] == "no video library on this site"
    result = publish_blog.publish(world["jdir"], row, VID, {}, AT)
    assert result["action"] == "add"
    git(seed, "pull", "-q", "origin", "main")
    assert (seed / "public/images/blog/springfield-rent-hearings.jpg").read_bytes() == b"jpeg"
    text = (seed / "src/lib/blog-data.ts").read_text()
    assert 'featuredImage: "/images/blog/springfield-rent-hearings.jpg"' in text
    assert git(seed, "log", "-1", "--format=%s") == "feat: publish Springfield Has No Rent Control. Why Can Tenants Get a Hearing?"


def test_no_upload_date_skips_the_library_entry_rather_than_guessing(world):
    row = publish_blog.plan_row(world["jdir"], "realestate", None, VID, {}, AT.date())
    assert row["library"].startswith("skips the video library entry") and "uploadDate" in row["library"]


def test_a_live_post_with_another_video_blocks_the_blog(world):
    (world["jdir"] / "out" / "blog.md").write_text(BLOG.replace("springfield-rent-hearings",
                                                                "northside-mobilehome-2026"))
    row = publish_blog.plan_row(world["jdir"], "realestate", None, VID, {}, AT.date())
    assert row["problems"] and "I9wz9_P_W5w" in row["problems"][0]
    with pytest.raises(RuntimeError, match="already embeds"):
        publish_blog.publish(world["jdir"], {**row, "problems": []}, VID, {}, AT)


def test_go_refuses_an_entry_that_changed_since_the_table(world):
    row = publish_blog.plan_row(world["jdir"], "realestate", None, VID, LINKS, AT.date())
    with pytest.raises(RuntimeError, match="changed since the table"):
        publish_blog.publish(world["jdir"], {**row, "entry_sha": "something else"}, VID, LINKS, AT)
    git(world["seed"], "fetch", "-q")
    assert git(world["seed"], "log", "--format=%s", "origin/main") == "seed"


def test_the_gate_also_builds_the_app_behind_a_changed_feed(world, monkeypatch):
    world["cfg"]["repos"]["my-sites"]["build"] = ["true", "--filter={app}"]
    row = publish_blog.plan_row(world["jdir"], "realestate", None, VID, LINKS, AT.date())
    real_run, builds = publish_blog.run, []
    monkeypatch.setattr(publish_blog, "run", lambda cmd, cwd, timeout=900, strip=True:
                        (builds.append(cmd) if cmd[0] == "true" else None) or real_run(cmd, cwd, timeout, strip))
    publish_blog.publish(world["jdir"], row, VID, LINKS, AT)
    assert builds[0] == ["true", "--filter=sitetwo", "--filter=examplerealty"]   # then the IndexNow stub


def test_a_push_that_times_out_leaves_no_local_commit_behind(world, monkeypatch):
    row = publish_blog.plan_row(world["jdir"], "realestate", None, VID, LINKS, AT.date())
    real = subprocess.run

    def fake(cmd, *a, **kw):
        if cmd[:2] == ["git", "push"]:
            raise subprocess.TimeoutExpired(cmd, 300)
        return real(cmd, *a, **kw)

    monkeypatch.setattr(publish_blog.subprocess, "run", fake)
    with pytest.raises(RuntimeError, match="did not finish"):
        publish_blog.publish(world["jdir"], row, VID, LINKS, AT)
    clone = publish_blog.clone_dir("my-sites", world["cfg"])
    assert git(clone, "rev-list", "--count", "origin/main..HEAD") == "0"
    assert git(clone, "status", "--porcelain", "--untracked-files=no") == ""


def test_hyphenated_topic_words_match():
    cfg = json.loads(publish_blog.SITES_FILE.read_text())
    assert publish_blog.topic_site(_p(title="Running a mini-HOA"), cfg) == "sitethree"
