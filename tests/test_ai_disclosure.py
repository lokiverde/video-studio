"""The kit's AI disclosure: a video with realistic footage says so in its YouTube
description, and the kit reminds Tony to set YouTube's own altered or synthetic content
setting in Studio (docs/briefs/2026-10-24-realistic-footage.md, 5.6). No render, no network."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from kit_fixtures import FACELESS_ID, FOOTER, jobs, make_faceless, patch_length  # noqa: E402,F401

import common  # noqa: E402
import publish_kit  # noqa: E402


def with_clip_scene(jdir, narrated=True):
    """Turn scene 2 of the fixture job into a clip scene, or (narrated=False) make every
    scene a silent clip scene: only clip scenes may go without narration."""
    data = json.loads((jdir / "scenes.json").read_text())
    clip = {"caption": "Yes, that video is fake", "clip": "rf/returns/S02_take1.mp4"}
    if narrated:
        data["scenes"][1] = {"id": 2, **clip, "narration": data["scenes"][1]["narration"]}
    else:
        data["scenes"] = [{"id": s["id"], **clip} for s in data["scenes"]]
    (jdir / "scenes.json").write_text(json.dumps(data))
    return jdir


def description(jdir):
    md = (jdir / "out" / "youtube.md").read_text()
    return md.partition("## Description\n\n")[2].split("\n\n## ", 1)[0]


def test_a_video_with_ai_footage_discloses_it_in_the_description(jobs, monkeypatch, capsys):
    patch_length(monkeypatch, 95.0)
    jdir = with_clip_scene(make_faceless(jobs))
    publish_kit.run(FACELESS_ID)
    assert "This video contains AI-generated footage." in description(jdir)
    md = (jdir / "out" / "youtube.md").read_text()
    assert "altered or synthetic content" in md.split("## Description")[1].split("\n\n## ", 1)[1]
    assert "altered or synthetic content" in capsys.readouterr().out


def test_the_disclosure_line_can_be_reworded_in_config(jobs, monkeypatch):
    patch_length(monkeypatch, 95.0)
    monkeypatch.setattr(common, "load_config", lambda: {
        "YOUTUBE_FOOTER": FOOTER, "AI_DISCLOSURE_LINE": "Some scenes were made with AI video tools."})
    jdir = with_clip_scene(make_faceless(jobs))
    publish_kit.run(FACELESS_ID)
    assert "Some scenes were made with AI video tools." in description(jdir)
    assert "This video contains AI-generated footage." not in description(jdir)


def test_a_video_without_clips_gets_no_disclosure(jobs, monkeypatch):
    patch_length(monkeypatch, 95.0)
    jdir = make_faceless(jobs)
    publish_kit.run(FACELESS_ID)
    md = (jdir / "out" / "youtube.md").read_text()
    assert "AI-generated" not in md and "synthetic" not in md


def test_a_silent_video_with_ai_footage_still_prints_the_disclosure(jobs, monkeypatch, capsys):
    """A video with no narration gets no kit at all, so the line is printed to paste."""
    jdir = with_clip_scene(make_faceless(jobs), narrated=False)
    publish_kit.run(FACELESS_ID)
    out = capsys.readouterr().out
    assert "This video contains AI-generated footage." in out
    assert "altered or synthetic content" in out
    assert not (jdir / "out" / "youtube.md").exists()
