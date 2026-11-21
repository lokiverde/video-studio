"""Post-publication links (links.json): the article URL first in every description, the
LinkedIn first comment, and fv.py bloglink / links. Idempotent like countdown quizlink, and
never a reason to re-approve: the sidecar sits outside every approval hash."""
import json

import pytest

from kit_fixtures import (BLOG, FACELESS_ID, YOUTUBE, jobs, make_faceless, make_talking_head,  # noqa: F401
                          patch_length)

import approval  # noqa: E402
import common  # noqa: E402
import kit_links  # noqa: E402
import publish_kit  # noqa: E402
import th_shorts  # noqa: E402

LINE = f"Written version with sources: {BLOG}"


# ---- pure apply functions --------------------------------------------------------------

def test_blog_line_goes_first_then_a_blank_line_then_the_body():
    out = kit_links.with_blog_line("Body one.\nBody two.", BLOG)
    assert out.split("\n") == [LINE, "", "Body one.", "Body two."]


def test_blog_line_twice_equals_once_and_a_new_url_replaces_the_old():
    once = kit_links.with_blog_line("Body.", BLOG)
    assert kit_links.with_blog_line(once, BLOG) == once
    moved = kit_links.with_blog_line(once, "https://sitetwo.com/news/other")
    assert moved.count("Written version with sources:") == 1
    assert moved.startswith("Written version with sources: https://sitetwo.com/news/other\n\nBody.")


def test_no_url_leaves_the_description_byte_for_byte():
    assert kit_links.with_blog_line("Body.\n", None) == "Body.\n"


def test_youtube_md_gets_the_line_in_the_description_section_only():
    md = "# YouTube kit\n\n## Title\n\nT\n\n## Description\n\nWhat you learn.\n\nTimeline\n0:00 A\n\n## Tags\n\na, b\n"
    once = kit_links.youtube_md_with_blog(md, BLOG)
    assert once == kit_links.youtube_md_with_blog(once, BLOG)
    assert f"## Description\n\n{LINE}\n\nWhat you learn." in once
    assert once.endswith("## Tags\n\na, b\n")
    assert once.replace(f"{LINE}\n\n", "") == md


def test_first_comment_has_placeholders_until_the_ids_exist():
    lines = kit_links.first_comment_lines({})
    assert lines == [f"Full video: {kit_links.YOUTUBE_PENDING}", f"Written version with sources: {kit_links.BLOG_PENDING}"]
    filled = kit_links.first_comment_lines({"youtube_id": YOUTUBE, "blog_url": BLOG})
    assert filled == [f"Full video: https://youtu.be/{YOUTUBE}", LINE]


def test_first_comment_section_replaces_itself_and_stays_last():
    md = "Post body.\n\n#Springfield\n"
    once = kit_links.with_first_comment(md, kit_links.first_comment_lines({}))
    filled = kit_links.with_first_comment(once, kit_links.first_comment_lines({"youtube_id": YOUTUBE}))
    assert filled == kit_links.with_first_comment(filled, kit_links.first_comment_lines({"youtube_id": YOUTUBE}))
    assert filled.count("## First comment") == 1
    assert filled.startswith("Post body.\n\n#Springfield\n\n## First comment\n\n")
    assert filled.rstrip().endswith(f"Written version with sources: {kit_links.BLOG_PENDING}")


def test_entry_gets_the_id_and_owner_url():
    text = '{\n  "id": "TODO_YOUTUBE_ID",\n  "title": "T",\n  "ownerUrl": "TODO_ARTICLE_URL",\n  "chapters": []\n}'
    once = kit_links.entry_with_links(text, {"youtube_id": YOUTUBE, "blog_url": BLOG})
    assert kit_links.entry_with_links(once, {"youtube_id": YOUTUBE, "blog_url": BLOG}) == once
    assert json.loads(once) == {"id": YOUTUBE, "title": "T", "ownerUrl": BLOG, "chapters": []}


@pytest.mark.parametrize("value", [YOUTUBE, f"https://youtu.be/{YOUTUBE}", f"https://www.youtube.com/watch?v={YOUTUBE}&t=3",
                                   f"https://youtube.com/shorts/{YOUTUBE}"])
def test_video_id_from_an_id_or_any_youtube_url(value):
    assert kit_links.video_id(value) == YOUTUBE


def test_bad_ids_and_urls_are_refused():
    with pytest.raises(ValueError):
        kit_links.video_id("not-an-id")
    with pytest.raises(ValueError):
        kit_links.check_url("sitetwo.com/news/x")


def test_save_merges_and_skips_empty_values(tmp_path):
    kit_links.save(tmp_path, blog_url=BLOG)
    links = kit_links.save(tmp_path, youtube_id=YOUTUBE, blog_url=None)
    assert links == {"blog_url": BLOG, "youtube_id": YOUTUBE}
    assert kit_links.load(tmp_path) == links


# ---- the CLI on a fixture job ----------------------------------------------------------

def _kit(jdir):
    """Write the kit the way finish does: publish kit, then the Shorts copy."""
    publish_kit.run(FACELESS_ID)
    th_shorts.write_kit(FACELESS_ID)


def _outputs(jdir):
    return {p.name: p.read_text() for p in sorted((jdir / "out").glob("*")) if p.suffix in (".md", ".txt")}


def _description_lines(md, n):
    """Lines of the nth (0-based) fenced description block in shorts.md."""
    return md.split("Description:\n```\n")[n + 1].split("\n```")[0].split("\n")


def test_bloglink_twice_is_byte_identical_and_puts_the_line_first(jobs, monkeypatch):
    patch_length(monkeypatch, 95.0)
    jdir = make_faceless(jobs)
    _kit(jdir)
    kit_links.main(["bloglink", FACELESS_ID, BLOG])
    first = _outputs(jdir)
    kit_links.main(["bloglink", FACELESS_ID, BLOG])
    assert _outputs(jdir) == first
    description = first["youtube.md"].split("## Description\n\n")[1]
    assert description.startswith(f"{LINE}\n\nSpringfield has no rent cap")
    assert first["youtube.md"].count(LINE) == 1
    shorts = first["shorts.md"]
    assert shorts.count(LINE) == 2
    one = _description_lines(shorts, 0)
    assert one[:3] == [LINE, "", "From the full episode: Springfield Has No Rent Control. Why Can Tenants Get a Hearing?."]
    assert _description_lines(shorts, 1)[:3] == [LINE, "", "The per-unit fee, in one minute."]
    assert "#Shorts" not in shorts
    assert json.loads((jdir / "links.json").read_text()) == {"blog_url": BLOG}


def test_a_kit_rerun_keeps_the_blog_line(jobs, monkeypatch):
    patch_length(monkeypatch, 95.0)
    jdir = make_faceless(jobs)
    _kit(jdir)
    kit_links.main(["bloglink", FACELESS_ID, BLOG])
    linked = _outputs(jdir)
    _kit(jdir)
    assert _outputs(jdir)["youtube.md"] == linked["youtube.md"]
    assert _outputs(jdir)["shorts.md"] == linked["shorts.md"]


def test_bloglink_never_voids_the_faceless_approval(jobs, monkeypatch):
    patch_length(monkeypatch, 95.0)
    jdir = make_faceless(jobs)
    common.set_state(FACELESS_ID, approved_fingerprint=approval.fingerprint(jdir, "faceless"))
    _kit(jdir)
    kit_links.main(["bloglink", FACELESS_ID, BLOG])
    kit_links.main(["links", FACELESS_ID, "--youtube", YOUTUBE])
    state = common.get_state(FACELESS_ID)
    assert approval.gate(state, approval.fingerprint(jdir, "faceless")) is None


def test_bloglink_never_changes_the_talking_head_fingerprint(jobs):
    jdir = make_talking_head(jobs)
    before = approval.fingerprint(jdir, "talking-head")
    job_json = (jdir / "job.json").read_text()
    kit_links.main(["bloglink", str(jdir), BLOG])
    assert approval.fingerprint(jdir, "talking-head") == before
    assert (jdir / "job.json").read_text() == job_json


def test_links_fills_the_first_comment_and_writes_the_paste_file(jobs, monkeypatch, capsys):
    patch_length(monkeypatch, 95.0)
    jdir = make_faceless(jobs)
    _kit(jdir)
    kit_links.main(["links", FACELESS_ID, "--youtube", f"https://youtu.be/{YOUTUBE}", "--blog", BLOG])
    first = _outputs(jdir)
    kit_links.main(["links", FACELESS_ID, "--youtube", YOUTUBE])
    assert _outputs(jdir) == first
    linkedin = first["linkedin.md"]
    body, comment = linkedin.split("## First comment")
    assert "http" not in body.split("---")[-1]          # the post body stays link-free
    assert comment.strip().split("\n") == [f"Full video: https://youtu.be/{YOUTUBE}", LINE]
    assert first["linkedin_comment.txt"] == f"Full video: https://youtu.be/{YOUTUBE}\n{LINE}\n"
    assert "Full video: https://youtu.be/" in capsys.readouterr().out


def test_links_fill_the_library_entry(jobs, monkeypatch):
    patch_length(monkeypatch, 95.0)
    jdir = make_faceless(jobs)
    _kit(jdir)
    entry = (jdir / "out" / "video_library_entry.txt").read_text()
    assert '"id": "TODO_YOUTUBE_ID"' in entry and '"ownerUrl": "TODO_ARTICLE_URL"' in entry
    kit_links.main(["links", FACELESS_ID, "--youtube", YOUTUBE, "--blog", BLOG])
    entry = (jdir / "out" / "video_library_entry.txt").read_text()
    assert f'"id": "{YOUTUBE}"' in entry and f'"ownerUrl": "{BLOG}"' in entry


def test_a_job_without_links_writes_the_same_youtube_md_as_before(jobs, monkeypatch):
    patch_length(monkeypatch, 95.0)
    jdir = make_faceless(jobs)
    publish_kit.run(FACELESS_ID)
    data = common.load_scenes(FACELESS_ID)
    durations = publish_kit.scene_durations(FACELESS_ID, data)
    today = publish_kit.youtube_markdown(publish_kit.youtube_meta(data, {}), publish_kit.chapters(data, durations),
                                         sum(durations), "Tony Self, Broker, CA DRE 00000001")
    assert (jdir / "out" / "youtube.md").read_text() == today
    assert not (jdir / "links.json").exists()


def test_bloglink_refuses_a_bare_domain(jobs):
    make_faceless(jobs)
    with pytest.raises(SystemExit):
        kit_links.main(["bloglink", FACELESS_ID, "sitetwo.com/news/x"])


def test_links_fills_the_upload_date_and_refuses_a_bad_one(jobs, monkeypatch):
    patch_length(monkeypatch, 95.0)
    jdir = make_faceless(jobs)
    _kit(jdir)
    kit_links.main(["links", FACELESS_ID, "--youtube", YOUTUBE, "--uploaded", "2026-10-19T16:28:37-07:00"])
    assert '"uploadDate": "2026-10-19T16:28:37-07:00"' in (jdir / "out" / "video_library_entry.txt").read_text()
    with pytest.raises(SystemExit):
        kit_links.main(["links", FACELESS_ID, "--uploaded", "10/19/2026"])


def test_a_bare_job_id_never_resolves_to_a_stray_folder_in_the_cwd(jobs, tmp_path_factory, monkeypatch):
    jdir = make_faceless(jobs)
    elsewhere = tmp_path_factory.mktemp("cwd")
    (elsewhere / FACELESS_ID).mkdir()
    monkeypatch.chdir(elsewhere)
    assert kit_links.resolve(FACELESS_ID) == jdir
    assert kit_links.resolve(f"./{FACELESS_ID}") == (elsewhere / FACELESS_ID).resolve()
