"""YouTube API client: the pieces that do not need the network. The update body must
carry every snippet field YouTube requires back, or a title edit wipes the description
and category."""
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import yt_api  # noqa: E402

SNIPPET = {"title": "Old", "description": "Desc", "categoryId": "22", "tags": ["a"],
           "defaultLanguage": "en", "thumbnails": {"x": 1}, "channelTitle": "Example Realty",
           "publishedAt": "2026-09-25T00:00:00Z"}


def test_auth_url_has_client_scopes_and_offline_access():
    url = yt_api.auth_url("cid.apps.googleusercontent.com", "http://127.0.0.1:8765", "st8")
    q = parse_qs(urlparse(url).query)
    assert q["client_id"] == ["cid.apps.googleusercontent.com"]
    assert q["access_type"] == ["offline"]
    assert q["prompt"] == ["consent"]
    assert q["state"] == ["st8"]
    for scope in yt_api.SCOPES:
        assert scope in q["scope"][0]


def test_retitle_body_keeps_required_fields_and_drops_read_only():
    body = yt_api.retitle_body("vid1", SNIPPET, "New title")
    snip = body["snippet"]
    assert body["id"] == "vid1"
    assert snip["title"] == "New title"
    assert snip["description"] == "Desc" and snip["categoryId"] == "22" and snip["tags"] == ["a"]
    assert "thumbnails" not in snip and "channelTitle" not in snip and "publishedAt" not in snip
    assert SNIPPET["title"] == "Old"


def test_retitle_rejects_long_or_empty_titles():
    with pytest.raises(ValueError):
        yt_api.retitle_body("v", SNIPPET, "x" * 101)
    with pytest.raises(ValueError):
        yt_api.retitle_body("v", SNIPPET, "   ")


def test_retitle_rejects_angle_brackets():
    with pytest.raises(ValueError):
        yt_api.retitle_body("v", SNIPPET, "Rent <cap>")


def test_token_expired_with_margin():
    assert yt_api.token_expired({"expires_at": 1000}, now=950)
    assert not yt_api.token_expired({"expires_at": 1000}, now=800)


def test_reach_rows_filters_to_videos_and_sums():
    csv_text = ("date,channel_id,video_id,video_thumbnail_impressions,"
                "video_thumbnail_impressions_ctr\n"
                "20260928,UC1,v1,100,0.05\n20260929,UC1,v1,300,0.03\n20260929,UC1,v2,50,0.1\n")
    rows = yt_api.reach_summary(csv_text, {"v1"})
    assert rows["v1"]["impressions"] == 400
    assert rows["v1"]["clicks"] == pytest.approx(14.0)
    assert "v2" not in rows


# ---- describe ---------------------------------------------------------------------------

def test_describe_body_keeps_the_snippet_and_swaps_the_description():
    body = yt_api.describe_body("vid12345678", SNIPPET, "  Written version with sources: https://x.test/a\n\nBody.  ")
    assert body["snippet"]["description"] == "Written version with sources: https://x.test/a\n\nBody."
    assert body["snippet"]["title"] == "Old" and body["snippet"]["categoryId"] == "22"
    assert "thumbnails" not in body["snippet"]


@pytest.mark.parametrize("bad", ["", "   ", "has <b>tags</b>", "x" * 5001])
def test_describe_body_refuses_what_youtube_rejects(bad):
    with pytest.raises(ValueError):
        yt_api.describe_body("vid12345678", SNIPPET, bad)


def test_description_from_a_youtube_md_kit_is_just_its_description_section():
    md = "# YouTube kit\n\n## Title\n\nT\n\n## Description\n\nLine one.\n\nTimeline\n0:00 A\n\n## Tags\n\na, b\n"
    assert yt_api.description_from_file(md) == "Line one.\n\nTimeline\n0:00 A"
    assert yt_api.description_from_file("Plain text.\n") == "Plain text."


# ---- reach windows ----------------------------------------------------------------------

REACH_CSV = ("date,channel_id,video_id,video_thumbnail_impressions,video_thumbnail_impressions_ctr\n"
             "20260926,UC1,AAA,100,0.01\n"
             "20260928,UC1,AAA,50,0.1\n"
             "20260928,UC1,BBB,10,0.5\n")


def test_reach_without_a_window_counts_every_row():
    totals = yt_api.reach_summary(REACH_CSV, {"AAA"})
    assert totals["AAA"]["impressions"] == 150
    assert totals["AAA"]["clicks"] == pytest.approx(6.0)


def test_reach_window_keeps_only_the_days_inside_it():
    after = yt_api.reach_summary(REACH_CSV, {"AAA"}, start="20260928", end="20261004")
    assert after["AAA"] == {"impressions": 50, "clicks": pytest.approx(5.0)}
    before = yt_api.reach_summary(REACH_CSV, {"AAA"}, end=yt_api.day_key("2026-09-26"))
    assert before["AAA"]["impressions"] == 100


def test_a_regenerated_day_counts_once_and_the_newest_report_wins():
    reports = [{"startTime": "2026-09-27T07:00:00Z", "createTime": "2026-09-29T01:00:00Z", "id": "old"},
               {"startTime": "2026-09-27T07:00:00Z", "createTime": "2026-10-10T01:00:00Z", "id": "new"},
               {"startTime": "2026-09-28T07:00:00Z", "createTime": "2026-09-30T01:00:00Z", "id": "next"}]
    assert [r["id"] for r in yt_api.latest_per_day(reports)] == ["new", "next"]


@pytest.mark.parametrize("bad", ["2026/09/27", "09-27-2026", "20260927x"])
def test_a_mistyped_reach_date_is_refused_not_ignored(bad):
    with pytest.raises(ValueError):
        yt_api.day_key(bad)
    assert yt_api.day_key("2026-09-27") == "20260927"
