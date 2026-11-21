"""Per-platform caption text (brief decisions 9, 14, 23, 24). Pure: no job folder, no network."""
from kit_fixtures import FOOTER  # noqa: F401  (also puts scripts/ on the path)

import publish_copy  # noqa: E402

BLOG = "https://sitetwo.com/news/shelbyville-rent-control-2026"
DESCRIPTION = (f"Written version with sources: {BLOG}\n\n"
               "Shelbyville has no local rent control today.\n\n"
               "Full episode: https://youtu.be/abcdefghijk\n\n"
               "#Shelbyville #Landlord\n\n" + FOOTER)
TITLE = "Shelbyville Has No Rent Control. What Applies Now?"


def test_youtube_gets_the_title_capped_at_100_without_angle_brackets():
    out = publish_copy.for_platform("youtube", "<b>" + "x" * 120, DESCRIPTION, FOOTER)
    assert out["title"] == ("b" + "x" * 120)[:100]
    assert out["text"] == DESCRIPTION


def test_tiktok_instagram_facebook_get_the_full_description():
    for platform in ("tiktok", "instagram", "facebook"):
        assert publish_copy.for_platform(platform, TITLE, DESCRIPTION, FOOTER)["text"] == DESCRIPTION


def test_long_text_is_cut_at_the_platform_limit():
    long = "word " * 1000
    assert len(publish_copy.for_platform("instagram", TITLE, long, FOOTER)["text"]) <= 2200


def test_linkedin_short_drops_every_url_line_and_keeps_the_footer():
    text = publish_copy.for_platform("linkedin", TITLE, DESCRIPTION, FOOTER)["text"]
    assert "http" not in text
    assert "Written version" not in text and "Full episode" not in text
    assert "Shelbyville has no local rent control today." in text
    assert text.endswith(FOOTER)
    assert "\n\n\n" not in text


def test_x_fits_280_with_urls_counted_as_23():
    text = publish_copy.for_platform("twitter", TITLE, DESCRIPTION, FOOTER)["text"]
    assert TITLE in text and BLOG in text and FOOTER in text
    assert publish_copy.x_length(text) <= 280


def test_x_drops_the_footer_before_it_cuts_the_title_when_the_footer_is_huge():
    text = publish_copy.for_platform("twitter", TITLE, DESCRIPTION, "F" * 300)["text"]
    assert text.startswith(TITLE)
    assert publish_copy.x_length(text) <= 280


def test_x_length_counts_any_url_as_23():
    assert publish_copy.x_length("a https://example.com/" + "p" * 200) == 2 + 23


def test_ai_disclosure_line_goes_on_every_platform():
    line = publish_copy.AI_LINE
    for platform in ("youtube", "tiktok", "instagram", "facebook", "linkedin", "twitter"):
        out = publish_copy.for_platform(platform, TITLE, DESCRIPTION, FOOTER, ai=True)
        assert line in out["text"], platform


def test_linkedin_full_strips_frontmatter_and_first_comment_and_adds_a_missing_footer():
    md = ("---\ntitle: x\npostdate:\n---\n\nI didn't build my AI class.\n\nWould you?\n\n"
          "#AI\n\n## First comment\n\nFull video: https://youtu.be/abcdefghijk\n")
    text = publish_copy.linkedin_full(md, FOOTER)
    assert text.startswith("I didn't build my AI class.")
    assert "First comment" not in text and "youtu.be" not in text and "postdate" not in text
    assert text.endswith(FOOTER)


def test_linkedin_full_drops_the_kit_title_note_and_divider():
    md = ("---\ntitle: x\n---\n\n# LINKEDIN\n\nBefore posting: upload the 16:9 video and put the links "
          "in the first comment, not the post body.\n\nAgents told me the internet would never take off.\n\n"
          "#AI #Realtors\n\n---\n\n## First comment\n\nFull video: https://youtu.be/abcdefghijk\n")
    text = publish_copy.linkedin_full(md, FOOTER)
    assert text == f"Agents told me the internet would never take off.\n\n#AI #Realtors\n\n{FOOTER}"


def test_linkedin_full_starts_after_the_kit_preamble():
    md = ("# Twenty tools, LinkedIn\n\nBefore posting: upload it.\n\nFacts: checked 2026-10-21.\n\n---\n\n"
          "# LINKEDIN\n\nThe post.\n")
    assert publish_copy.linkedin_full(md, FOOTER) == f"The post.\n\n{FOOTER}"


def test_linkedin_full_keeps_a_hashtag_line_that_opens_the_post():
    assert publish_copy.linkedin_full("#AI #Realtors\n\nBody.\n", FOOTER).startswith("#AI #Realtors")


def test_linkedin_full_drops_a_first_comment_heading_in_capitals():
    md = "Body.\n\n# FIRST COMMENT\n\nFull video: https://youtu.be/abcdefghijk\n"
    assert publish_copy.linkedin_full(md, FOOTER) == f"Body.\n\n{FOOTER}"


def test_linkedin_full_keeps_a_footer_already_there():
    md = f"Body.\n\n{FOOTER}\n"
    assert publish_copy.linkedin_full(md, FOOTER).count(FOOTER) == 1


def test_no_em_dashes_reach_any_platform():
    text = "Shelbyville \u2014 rules \u2013 now"
    for platform in ("youtube", "linkedin", "twitter"):
        out = publish_copy.for_platform(platform, text, text, FOOTER)
        assert "\u2014" not in out["text"] and "\u2013" not in out["text"]
        assert "\u2014" not in out.get("title", "")


def test_realestate_x_never_drops_the_dre_footer_it_cuts_the_title():
    long_title = "Shelbyville " * 40
    text = publish_copy.for_platform("twitter", long_title, DESCRIPTION, FOOTER, keep_footer=True)["text"]
    assert text.endswith(FOOTER)
    assert publish_copy.x_length(text) <= 280


def test_a_cut_keeps_the_footer_whole_at_the_end():
    long = ("word " * 1000) + "\n\n" + FOOTER
    text = publish_copy.for_platform("instagram", TITLE, long, FOOTER)["text"]
    assert len(text) <= 2200 and text.endswith(FOOTER)


def test_ai_line_sits_before_the_footer():
    text = publish_copy.for_platform("tiktok", TITLE, DESCRIPTION, FOOTER, ai=True)["text"]
    assert text.endswith(FOOTER)
    assert text.index(publish_copy.AI_LINE) < text.index(FOOTER)
