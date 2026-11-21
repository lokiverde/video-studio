"""blog.md, the companion article a job ships, read into a post: the frontmatter (no PyYAML on
the Mac, so a small reader for the shapes the kit writes) and the body for each site's renderer."""
import pytest

import kit_fixtures  # noqa: F401  (puts scripts/ on the path)
import blog_md  # noqa: E402

BLOG = """---
site: brokerage.example
title: "ChatGPT Built My Whole Class. Can It Build Your Listing Presentation?"
slug: chatgpt-built-my-class-listing-presentation
date: 2026-10-28
tags: [examplerealty, blog, ai-for-realtors]
status: draft
excerpt: "I didn't build the slides. ChatGPT did."
meta_description: 'Tony''s method for a listing deck.'
notes_for_tony:
  - "Check the search engine claim."
  - "Vercel is not French."
---

# ChatGPT Built My Whole Class

I didn't build the slides for my AI class. ChatGPT did.

[VIDEO]

## Start with the room

I told ChatGPT who was going to be sitting in front of me, *agents*, not **technologists**.

### A smaller heading

- Class page: https://brokerage.example/ai20
* PowerPoint download

> You are a homeowner interviewing me.

| Tool | Free plan |
|---|---|
| ChatGPT | Yes |

---

Tony Self, MBA
Broker, Example Realty, CA DRE 00000001
"""


def test_frontmatter_reads_quoted_bare_list_and_block_values():
    meta, body = blog_md.frontmatter(BLOG)
    assert meta["site"] == "brokerage.example"
    assert meta["title"] == "ChatGPT Built My Whole Class. Can It Build Your Listing Presentation?"
    assert meta["date"] == "2026-10-28"
    assert meta["tags"] == ["examplerealty", "blog", "ai-for-realtors"]
    assert meta["meta_description"] == "Tony's method for a listing deck."
    assert meta["notes_for_tony"] == ["Check the search engine claim.", "Vercel is not French."]
    assert body.lstrip().startswith("# ChatGPT")


def test_no_frontmatter_is_an_empty_dict():
    assert blog_md.frontmatter("# Title\n\nText\n") == ({}, "# Title\n\nText\n")


def test_hm_body_one_entry_per_line_in_the_renderer_shapes():
    title, body = blog_md.hm_body(blog_md.frontmatter(BLOG)[1])
    assert title == "ChatGPT Built My Whole Class"
    assert body == [
        "I didn't build the slides for my AI class. ChatGPT did.",
        blog_md.VIDEO_SLOT,
        "## Start with the room",
        "I told ChatGPT who was going to be sitting in front of me, agents, not **technologists**.",
        "## A smaller heading",
        "• Class page: https://brokerage.example/ai20",
        "• PowerPoint download",
        '"You are a homeowner interviewing me."',
        "| Tool | Free plan |",
        "|---|---|",
        "| ChatGPT | Yes |",
        "Tony Self, MBA",
        "Broker, Example Realty, CA DRE 00000001",
    ]


@pytest.mark.parametrize("marker", ["[VIDEO]", "*[VIDEO EMBED]*", "[VIDEO EMBED]", "{{YOUTUBE_EMBED}}"])
def test_every_video_marker_becomes_the_slot(marker):
    assert blog_md.hm_body(f"Intro.\n\n{marker}\n\nMore.\n")[1] == ["Intro.", blog_md.VIDEO_SLOT, "More."]


def test_a_body_without_a_marker_gets_the_slot_after_the_first_paragraph():
    assert blog_md.hm_body("One.\n\nTwo.\n")[1] == ["One.", blog_md.VIDEO_SLOT, "Two."]
    assert blog_md.markdown_body("One.\n\nTwo.\n")[1] == f"One.\n\n{blog_md.VIDEO_SLOT}\n\nTwo."


def test_markdown_body_keeps_the_markdown_and_drops_the_h1():
    title, content = blog_md.markdown_body("# Big title\n\nIntro.\n\n*[VIDEO EMBED]*\n\n## Part\n\n- a\n")
    assert title == "Big title"
    assert content == f"Intro.\n\n{blog_md.VIDEO_SLOT}\n\n## Part\n\n- a"


def test_dashes_become_commas():
    assert blog_md.hm_body("Rent \u2014 the cap \u2013 is 8.7%.\n")[1][0] == "Rent, the cap, is 8.7%."


def test_post_falls_back_to_the_h1_and_the_meta_description():
    post = blog_md.post("---\nslug: a-b\nmeta_description: The short one.\n---\n\n# From the H1\n\nText.\n")
    assert post["title"] == "From the H1"
    assert post["excerpt"] == "The short one."
    assert post["slug"] == "a-b"


def test_problems_name_a_missing_slug_title_excerpt_and_banned_words():
    found = blog_md.problems(blog_md.post("---\ntitle: T\n---\n\nLet us delve into the realm.\n"))
    assert any("slug" in p for p in found)
    assert any("excerpt" in p for p in found)
    assert any("delve" in p for p in found) and any("realm" in p for p in found)
    assert blog_md.problems(blog_md.post(BLOG)) == []


def test_a_bad_slug_is_a_problem():
    assert any("slug" in p for p in blog_md.problems(blog_md.post("---\nslug: Not A Slug\ntitle: T\nexcerpt: E\n---\n\nX\n")))
