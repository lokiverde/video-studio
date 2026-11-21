"""Format routing: SHORT under 120 s, JUDGMENT from 120 to 180 s inclusive, LONG over 180 s,
decided from the real rendered length and printed as one ROUTE: line plus out/route.md."""
import shutil
import subprocess

import pytest

from kit_fixtures import BLOG, FACELESS_ID, jobs, make_faceless, patch_length  # noqa: F401

import format_route  # noqa: E402
import kit_links  # noqa: E402
import publish_kit  # noqa: E402


@pytest.mark.parametrize("seconds,kind", [(119, "SHORT"), (119.9, "SHORT"), (120, "JUDGMENT"), (179, "JUDGMENT"),
                                          (180, "JUDGMENT"), (180.5, "LONG"), (181, "LONG")])
def test_boundaries(seconds, kind):
    assert format_route.decide(seconds, has_article=False).kind == kind


def test_a_short_with_an_article_also_gets_an_unlisted_16x9_for_the_embed():
    with_article = format_route.decide(95, has_article=True)
    without = format_route.decide(95, has_article=False)
    assert any("Unlisted" in s for s in with_article.steps)
    assert not any("Unlisted" in s for s in without.steps)
    assert any("Never publish the 16:9 as a public video" in s for s in without.steps)
    assert format_route.route_line(with_article) == ("ROUTE: SHORT (95s). 9:16 public Short + 16:9 Unlisted for "
                                                     "the article embed.")


def test_judgment_recommends_long_form_only_when_the_kit_has_chapters():
    chaptered = format_route.decide(150, False, chapters=4)
    single = format_route.decide(150, False, chapters=1)
    assert (chaptered.recommend, single.recommend) == ("LONG", "SHORT")
    assert format_route.route_line(chaptered).startswith("ROUTE: JUDGMENT (150s). Recommend LONG")


def test_long_form_gets_the_thumbnail_set_shorts_and_the_related_video_reminder():
    route = format_route.decide(245, has_article=True, chapters=6)
    text = " ".join(route.steps)
    assert "Test & compare" in text and "th_shorts.py" in text and "Related video" in text


@pytest.mark.parametrize("fmt", sorted(format_route.SHORTS_ONLY))
def test_shorts_only_formats_stay_shorts_without_a_thumbnail_set(fmt):
    route = format_route.decide(240, False, fmt=fmt)
    assert route.kind == "SHORT"
    assert "no thumbnail set" in route.reason


def test_write_prints_the_route_and_writes_route_md(jobs, monkeypatch, capsys):
    patch_length(monkeypatch, 95.0)
    jdir = make_faceless(jobs)
    route = format_route.write(jdir, chapters=3, fmt="faceless")
    assert route.kind == "SHORT"
    assert "[route] ROUTE: SHORT (95s)" in capsys.readouterr().out
    md = (jdir / "out" / "route.md").read_text()
    assert md.startswith("ROUTE: SHORT (95s). 9:16 public Short, no 16:9 upload.\n")
    assert "Measured length: 95.0 s (final_16x9.mp4, ffprobe)" in md
    assert format_route.recorded_kind(jdir) == "SHORT"


def test_no_final_no_route(jobs):
    jdir = make_faceless(jobs, final=False)
    assert format_route.write(jdir, chapters=3, fmt="faceless") is None
    assert not (jdir / "out" / "route.md").exists()


def test_the_kit_routes_after_render_and_an_article_link_re_decides(jobs, monkeypatch):
    patch_length(monkeypatch, 95.0)
    jdir = make_faceless(jobs)
    publish_kit.run(FACELESS_ID)
    assert "no 16:9 upload" in (jdir / "out" / "route.md").read_text()
    kit_links.main(["bloglink", FACELESS_ID, BLOG])
    assert "16:9 Unlisted for the article embed" in (jdir / "out" / "route.md").read_text()


def test_a_blog_md_counts_as_a_companion_article(jobs, monkeypatch):
    patch_length(monkeypatch, 95.0)
    jdir = make_faceless(jobs)
    (jdir / "out" / "blog.md").write_text("# Post\n")
    assert format_route.write(jdir, chapters=1, fmt="faceless").has_article


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_the_length_is_measured_from_the_real_file(tmp_path):
    video = tmp_path / "final_16x9.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=64x36:d=3:r=25",
                    "-pix_fmt", "yuv420p", str(video), "-y"], check=True)
    assert format_route.probe_seconds(video) == pytest.approx(3.0, abs=0.25)


def test_an_unreadable_final_warns_and_never_aborts_the_kit(jobs, monkeypatch, capsys):
    def broken(path):
        raise subprocess.CalledProcessError(1, ["ffprobe"])
    monkeypatch.setattr(format_route, "probe_seconds", broken)
    jdir = make_faceless(jobs)
    publish_kit.run(FACELESS_ID)
    assert (jdir / "out" / "youtube.md").exists()
    assert not (jdir / "out" / "route.md").exists()
    assert "could not measure final_16x9.mp4" in capsys.readouterr().out
