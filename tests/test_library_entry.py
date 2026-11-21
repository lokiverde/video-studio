"""The ready-to-paste VIDEO_LIBRARY entry: VideoEntry's exact fields, ISO 8601 duration,
chapters from the kit timeline, the transcript as spoken and the flagged takeaway fallback.
The sample type-checks against a scratch copy of VideoEntry in a temp folder (never inside
my-sites)."""
import json
import re
import shutil
import subprocess

import pytest

from kit_fixtures import FACELESS_ID, ROOT, jobs, make_faceless, make_talking_head, patch_length  # noqa: F401

import library_entry  # noqa: E402
import publish_kit  # noqa: E402

# Field order and types of VideoEntry in my-sites packages/ui/src/video-types.ts (2026-10-22).
VIDEO_TYPES = """export interface VideoChapter {
  start: number;
  label: string;
}

export interface VideoEntry {
  id: string;
  title: string;
  description: string;
  uploadDate: string;
  duration: string;
  ownerUrl: string;
  keyTakeaways: string[];
  chapters: VideoChapter[];
  transcript: string[];
  transcriptSource: string;
}
"""
FIELDS = ["id", "title", "description", "uploadDate", "duration", "ownerUrl", "keyTakeaways", "chapters",
          "transcript", "transcriptSource"]


def _entry(text):
    """The object literal without its comment lines and the trailing comma."""
    body = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("//"))
    return json.loads(body.rstrip().rstrip(","))


@pytest.mark.parametrize("seconds,iso", [(181, "PT3M1S"), (376.4, "PT6M16S"), (45, "PT45S"), (120, "PT2M"),
                                         (3725, "PT1H2M5S"), (0, "PT0S")])
def test_iso_duration(seconds, iso):
    assert library_entry.iso_duration(seconds) == iso


def test_faceless_entry_has_every_field_in_order_and_the_flagged_fallback(jobs, monkeypatch):
    patch_length(monkeypatch, 95.4)
    jdir = make_faceless(jobs)
    publish_kit.run(FACELESS_ID)
    text = (jdir / "out" / "video_library_entry.txt").read_text()
    entry = _entry(text)
    assert list(entry) == FIELDS
    assert entry["duration"] == "PT1M35S"
    assert entry["id"] == "TODO_YOUTUBE_ID" and entry["uploadDate"] == "TODO_UPLOAD_DATE"
    assert entry["ownerUrl"] == "TODO_ARTICLE_URL"
    assert entry["transcriptSource"] == "narration script"
    assert entry["transcript"][0] == "Springfield has no rent control. Tenants still get a hearing."   # no title line
    assert len(entry["transcript"]) == 4
    assert entry["keyTakeaways"] == ["Springfield has no rent control.", "Raise the rent more than 5% and a tenant can ask for one.",
                                     "Your notice has to say so.", "There is also a fee per unit."]
    assert "// FALLBACK takeaways" in text
    assert all(isinstance(c["start"], int) for c in entry["chapters"]) and entry["chapters"][0]["start"] == 0
    assert "\u2014" not in text and "\u2013" not in text      # house rule: no em or en dashes


def test_authored_takeaways_win_and_are_not_flagged(jobs, monkeypatch):
    patch_length(monkeypatch, 200.0)
    jdir = make_talking_head(jobs)
    import th
    th.write_kit(str(jdir))
    text = (jdir / "out" / "video_library_entry.txt").read_text()
    entry = _entry(text)
    assert entry["keyTakeaways"] == ["Riverside has no local rent control.", "The state cap is 8.7 percent.",
                                     "Just cause applies after a year."]
    assert "FALLBACK" not in text
    assert entry["transcriptSource"] == "final-cut captions"
    assert entry["duration"] == "PT3M20S"
    assert (jdir / "out" / "route.md").read_text().startswith("ROUTE: LONG (200s)")


def test_takeaway_count_outside_three_to_five_is_reported():
    entry = {"keyTakeaways": ["one", "two"]}
    assert library_entry.problems(entry, fallback=False)
    assert library_entry.problems({"keyTakeaways": ["a", "b", "c"]}, fallback=False) == []


def test_a_one_line_caption_transcript_is_split_at_sentence_ends_without_changing_a_word():
    sentence = "The cap is eight point seven percent this year in Los Angeles County for most rentals. "
    text = (sentence * 12).strip()
    paras = library_entry.paragraphs(text)
    assert len(paras) > 1
    assert " ".join(paras) == text


def test_link_lines_stay_out_of_the_library_description():
    entry = library_entry.build({"title": "T", "description": "Book a call: https://x.test/c\nWhat you learn."},
                                61, [(0, "Intro")], ["Said."], ["a", "b", "c"], "narration script", {})
    assert entry["description"] == "What you learn."


@pytest.mark.skipif(not (shutil.which("tsc") or (ROOT / "talking-head/node_modules/.bin/tsc").exists()),
                    reason="no TypeScript compiler here")
def test_the_sample_type_checks_against_video_entry(jobs, monkeypatch, tmp_path_factory):
    patch_length(monkeypatch, 95.0)
    jdir = make_faceless(jobs)
    publish_kit.run(FACELESS_ID)
    scratch = tmp_path_factory.mktemp("library")
    (scratch / "video-types.ts").write_text(VIDEO_TYPES)
    entry = (jdir / "out" / "video_library_entry.txt").read_text()
    (scratch / "video-library.ts").write_text(
        'import type { VideoEntry } from "./video-types";\n\nexport const VIDEO_LIBRARY: VideoEntry[] = [\n'
        + entry + "];\n")
    tsc = shutil.which("tsc") or str(ROOT / "talking-head/node_modules/.bin/tsc")
    result = subprocess.run([tsc, "--noEmit", "--strict", "--target", "es2020", "--module", "esnext", "--moduleResolution", "bundler",
                             str(scratch / "video-library.ts")], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert re.search(r'"duration": "PT1M35S"', entry)
