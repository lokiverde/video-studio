"""Real-footage jobs on the command line: start one, see where it stands, bring generated
files back in with a ledger (docs/briefs/2026-10-24-realistic-footage.md, 5.2 and 5.3).
Every media file here is made locally with ffmpeg: no vendor files, no network."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import common  # noqa: E402
import rf  # noqa: E402


@pytest.fixture
def jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "JOBS_DIR", tmp_path)
    return tmp_path


def only_job(root):
    (jdir,) = [p for p in root.iterdir() if p.is_dir()]
    return jdir


def test_new_starts_a_job_with_a_brief_and_a_starter_shot_list(jobs):
    rf.main(["new", "fox", "--idea", "a fox in a call-center headset shakes its head no"])
    jdir = only_job(jobs)
    assert jdir.name.endswith("-fox")
    shots = json.loads((jdir / "rf" / "shots.json").read_text())
    assert shots["job"] == jdir.name
    assert shots["idea"] == "a fox in a call-center headset shakes its head no"
    assert shots["lane"] == "techtony"
    assert shots["ai_disclosure"] is True
    assert shots["likeness"] == {}
    assert shots["defaults"] == {"provider": "openart", "aspect": "9:16", "draft_first": True,
                                 "ref_tag_syntax": "image N by position (OpenArt, 2026-10-24)"}
    still, clip = shots["shots"]
    assert (still["id"], still["kind"], still["model"], still["status"]) == \
        ("S01", "still", "nano-banana-pro", "drafted")
    assert (clip["id"], clip["kind"], clip["status"], clip["returns"]) == ("S02", "clip", "drafted", [])
    assert clip["model"] == {"draft": "byte-plus-seedance-2-5-draft", "final": "byte-plus-seedance-2-5"}
    assert "a fox in a call-center headset" in (jdir / "rf" / "brief.md").read_text()


def test_new_on_an_existing_job_adds_the_rf_folder_to_it(jobs):
    jdir = jobs / "20261024-101500-scam"
    (jdir / "work").mkdir(parents=True)
    rf.main(["new", jdir.name, "--idea", "x", "--lane", "example-realty"])
    assert only_job(jobs) == jdir
    assert json.loads((jdir / "rf" / "shots.json").read_text())["lane"] == "example-realty"


def test_new_never_overwrites_a_shot_list(jobs, capsys):
    jdir = jobs / "20261024-101500-scam"
    (jdir / "rf").mkdir(parents=True)
    (jdir / "rf" / "shots.json").write_text('{"keep": "me"}')
    with pytest.raises(SystemExit):
        rf.main(["new", jdir.name, "--idea", "x"])
    assert "already" in capsys.readouterr().err
    assert (jdir / "rf" / "shots.json").read_text() == '{"keep": "me"}'


def test_ladder_writes_four_levels_into_the_brief(jobs):
    rf.main(["new", "fox", "--idea", "a man deletes junk mail", "--ladder"])
    brief = (only_job(jobs) / "rf" / "brief.md").read_text()
    assert "Level 0: a man deletes junk mail" in brief    # the idea as given is the expected version
    for level in (1, 2, 3):
        assert f"Level {level}:" in brief


def status_rows(job_id, capsys):
    capsys.readouterr()
    rf.main(["status", job_id])
    lines = [line.split() for line in capsys.readouterr().out.splitlines() if line.strip()]
    return lines[0], lines[1:]


def test_status_prints_one_row_per_shot(jobs, capsys):
    rf.main(["new", "fox", "--idea", "x"])
    header, rows = status_rows(only_job(jobs).name, capsys)
    assert header == ["shot", "kind", "technique", "style", "status", "returns", "lint"]
    # nothing written, returned or linted yet: every empty cell reads "-"
    assert rows == [["S01", "still", "-", "-", "drafted", "-", "-"],
                    ["S02", "clip", "-", "-", "drafted", "-", "-"]]


@pytest.mark.parametrize("command", ["status", "ingest"])
@pytest.mark.parametrize("value", [False, None, "yes", 1])
def test_a_shot_list_without_disclosure_is_refused(jobs, capsys, value, command):
    rf.main(["new", "fox", "--idea", "x"])
    path = only_job(jobs) / "rf" / "shots.json"
    path.write_text(json.dumps({**json.loads(path.read_text()), "ai_disclosure": value}))
    extra = [str(path), "--shot", "S02"] if command == "ingest" else []
    with pytest.raises(SystemExit):
        rf.main([command, only_job(jobs).name, *extra])
    assert "'ai_disclosure' must be true" in capsys.readouterr().err


def test_the_main_cli_carries_the_rf_group():
    import subprocess
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "fv.py"), "rf", "--help"],
                         capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    for command in ("new", "status", "ingest"):
        assert command in out.stdout
