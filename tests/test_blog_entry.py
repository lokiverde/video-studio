"""The text edits the blog publisher makes to a site repo: a new entry at the top of the posts
array, a videoId on an existing post that has none, and the video library entry. Pure: file
text in, file text out."""
import json
from datetime import date

import kit_fixtures  # noqa: F401  (puts scripts/ on the path)
import blog_entry  # noqa: E402
import blog_md  # noqa: E402

DAY = date(2026, 10, 29)
VID = "AbCdEfGhIjK"
HM_POSTS = '''import type { BillRef } from "@my/ui/bill-tracker";

export interface NewsPost {
  slug: string;
}

export const POSTS: NewsPost[] = [
  {
    // videoId added once the YouTube link for this episode is supplied.
    slug: "shelbyville-rent-control-2026",
    title: "Shelbyville: No Local Rent Control, For Now",
    category: "Rent Control",
    date: "2026-10-25",
    excerpt: "Shelbyville has no local rent control today.",
    body: [
      "Intro.",
      "{{YOUTUBE_EMBED}}",
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
EMPTY_POSTS = "export const POSTS: NewsPost[] = [];\n"
TECH_POSTS = '''export const blogPosts: BlogPost[] = [
  // October 2026
  {
    slug: "which-ai-keeps-your-data",
    title: "Which AI Keeps Your Data?",
    date: "October 26, 2026",
    excerpt: "Six engines.",
    readingTime: "2 min read",
    category: "AI Safety",
    content: `
Text.
`,
  },
];
'''
BLOG = """---
slug: springfield-rent-hearings
title: "Springfield Has No Rent Control. Why Can Tenants Get a Hearing?"
excerpt: "A rent hearing still applies over 5%."
category: Rent Control
---

Springfield has no rent cap.

[VIDEO]

## The 5% line

Use `code` and ${money} here.
"""
LIBRARY = '''import type { VideoEntry } from "./video-types";

export const VIDEO_LIBRARY: VideoEntry[] = [
  {
    "id": "I9wz9_P_W5w",
    "title": "Carson"
  },
];
'''
ENTRY_TXT = '''// VIDEO_LIBRARY entry for job x. Paste at the top of VIDEO_LIBRARY.
// Until upload: id (TODO_YOUTUBE_ID).
{
  "id": "TODO_YOUTUBE_ID",
  "title": "Springfield",
  "uploadDate": "TODO_UPLOAD_DATE",
  "ownerUrl": "TODO_ARTICLE_URL",
  "keyTakeaways": [
    "One."
  ]
},
'''
HM_SITE = {"format": "hm", "default_category": "Rent Control", "video_before": "excerpt"}
TECH_SITE = {"format": "techtony", "default_category": "How To", "video_before": "content",
             "image_url": "/images/blog/{slug}.jpg"}


def _post():
    return blog_md.post(BLOG)


def test_a_new_hm_post_goes_first_with_the_video_and_today():
    out = blog_entry.change(HM_POSTS, _post(), HM_SITE, VID, DAY)
    assert out["action"] == "add" and out["category"] == "Rent Control"
    first = out["text"].index('slug: "springfield-rent-hearings"')
    assert first < out["text"].index('slug: "shelbyville-rent-control-2026"')
    assert '    date: "2026-10-29",\n    videoId: "AbCdEfGhIjK",\n' in out["text"]
    assert '      "{{YOUTUBE_EMBED}}",\n      "## The 5% line",\n' in out["text"]
    assert out["text"].count("export const POSTS") == 1 and out["text"].endswith("];\n")


def test_the_hm_entry_is_valid_data():
    entry = blog_entry.hm_entry(_post(), category="Rent Control", day=DAY, video_id=VID, author="Tony Self")
    as_json = "{" + entry.strip().strip(",").strip()[1:-1] + "}"
    as_json = __import__("re").sub(r"^(\s+)(\w+):", r'\1"\2":', as_json, flags=__import__("re").M)
    as_json = __import__("re").sub(r",(\s*[\]}])", r"\1", as_json)
    data = json.loads(as_json)
    assert data["author"] == "Tony Self" and data["videoId"] == VID
    assert data["body"][1] == "{{YOUTUBE_EMBED}}"


def test_an_unknown_category_falls_back_to_the_site_default():
    post = {**_post(), "category": "Gossip"}
    out = blog_entry.change(HM_POSTS, post, {**HM_SITE, "default_category": "Compliance"}, VID, DAY)
    assert out["category"] == "Compliance"
    assert "Gossip" in out["note"]


def test_category_matching_keeps_the_site_spelling():
    out = blog_entry.change(HM_POSTS, {**_post(), "category": "rent control"}, HM_SITE, VID, DAY)
    assert out["category"] == "Rent Control"


def test_an_empty_posts_array_takes_the_first_entry():
    out = blog_entry.change(EMPTY_POSTS, _post(), {**HM_SITE, "default_category": "Education"}, VID, DAY)
    assert out["text"].startswith("export const POSTS: NewsPost[] = [\n  {\n")
    assert out["text"].endswith("  },\n];\n")
    assert out["category"] == "Rent Control"   # nothing to match against: the post's own category stands


def test_an_existing_post_without_a_video_gets_it_and_loses_the_placeholder_comment():
    post = {**_post(), "slug": "shelbyville-rent-control-2026"}
    out = blog_entry.change(HM_POSTS, post, HM_SITE, VID, DAY)
    assert out["action"] == "fill"
    assert "videoId added once" not in out["text"]
    assert ('    date: "2026-10-25",\n    videoId: "AbCdEfGhIjK",\n    excerpt: "Shelbyville has' in out["text"])
    assert out["text"].count("videoId:") == 2          # Carson's own is untouched
    assert out["entry"].startswith("  {\n    slug: \"shelbyville") and out["entry"].endswith("  },\n")


def test_an_existing_post_with_a_video_is_left_alone():
    post = {**_post(), "slug": "northside-mobilehome-2026"}
    out = blog_entry.change(HM_POSTS, post, HM_SITE, VID, DAY)
    assert out == {"action": "live", "text": HM_POSTS, "entry": "", "category": "Compliance", "note": "",
                   "video": "I9wz9_P_W5w"}


def test_techtony_entry_sits_under_this_month_with_reading_time_image_and_escapes():
    out = blog_entry.change(TECH_POSTS, _post(), TECH_SITE, VID, DAY)
    text = out["text"]
    assert text.index("  // October 2026\n  {\n    slug: \"springfield-rent-hearings\"") < text.index("which-ai-keeps")
    assert '    date: "October 29, 2026",\n' in text
    assert '    readingTime: "1 min read",\n' in text
    assert '    featuredImage: "/images/blog/springfield-rent-hearings.jpg",\n' in text
    assert "Use \\`code\\` and \\${money} here." in text
    assert "content: `\nSpringfield has no rent cap.\n\n{{YOUTUBE_EMBED}}\n\n## The 5% line" in text
    assert out["category"] == "How To"                 # Rent Control is not a techtony category


def test_techtony_new_month_gets_its_own_comment():
    out = blog_entry.change(TECH_POSTS, _post(), TECH_SITE, VID, date(2026, 11, 2))
    assert out["text"].startswith("export const blogPosts: BlogPost[] = [\n  // November 2026\n  {\n")
    assert "  },\n  // October 2026\n" in out["text"]


def test_library_entry_is_filled_reindented_and_goes_first():
    links = {"youtube_id": VID, "upload_date": "2026-10-29", "blog_url": "https://sitetwo.com/news/g"}
    obj, why = blog_entry.library_entry(ENTRY_TXT, links)
    assert why is None
    text, why = blog_entry.add_library(LIBRARY, obj, VID)
    assert why is None
    assert text.index(f'"id": "{VID}"') < text.index('"id": "I9wz9_P_W5w"')
    assert '  {\n    "id": "AbCdEfGhIjK",\n' in text and '"ownerUrl": "https://sitetwo.com/news/g"' in text
    assert "TODO_" not in text and "// VIDEO_LIBRARY" not in text


def test_library_entry_is_skipped_for_fallback_takeaways_or_a_known_id():
    fallback = ENTRY_TXT.replace('  "keyTakeaways"', "  // FALLBACK takeaways: replace.\n  \"keyTakeaways\"")
    links = {"youtube_id": VID, "upload_date": "2026-10-29", "blog_url": "https://x.co/a"}
    assert blog_entry.library_entry(fallback, links)[0] is None
    obj, _ = blog_entry.library_entry(ENTRY_TXT, {**links, "youtube_id": "I9wz9_P_W5w"})
    text, why = blog_entry.add_library(LIBRARY, obj, "I9wz9_P_W5w")
    assert text == LIBRARY and "already" in why


def test_library_entry_needs_every_placeholder_filled():
    obj, why = blog_entry.library_entry(ENTRY_TXT, {"youtube_id": VID, "blog_url": "https://x.co/a"})
    assert obj is None and "uploadDate" in why


def test_a_techtony_entry_with_a_code_sample_brace_is_found_whole():
    text = TECH_POSTS.replace("Text.\n`,", "Code:\n  },\nFinal paragraph.\n`,")
    start, end = blog_entry.find_post(text, "which-ai-keeps-your-data")
    assert text[start:end].endswith("Final paragraph.\n`,\n  },")


def test_a_library_entry_that_is_not_an_object_is_skipped():
    obj, why = blog_entry.library_entry("[1, 2]\n", {"youtube_id": VID})
    assert obj is None and "object" in why
