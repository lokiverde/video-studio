"""rf lint on the command line, its result in rf status, and the gate it puts in front of
rf pack (docs/briefs/2026-10-24-realistic-footage.md, 5.2 and 5.5). No network."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from rf_fixtures import FOX, clip, job, still, swap  # noqa: E402

import common  # noqa: E402
import rf  # noqa: E402

JOB = "20261024-101500-fox"


@pytest.fixture
def jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "JOBS_DIR", tmp_path)
    return tmp_path


def make_job(jobs, data, brief="# Real-footage brief\n"):
    rf_dir = jobs / JOB / "rf"
    rf_dir.mkdir(parents=True)
    (rf_dir / "shots.json").write_text(json.dumps({**data, "job": JOB}, indent=2))
    (rf_dir / "brief.md").write_text(brief)
    return rf_dir


def shots(rf_dir):
    return {s["id"]: s for s in json.loads((rf_dir / "shots.json").read_text())["shots"]}


def status_rows(capsys):
    capsys.readouterr()
    rf.main(["status", JOB])
    return {line.split()[0]: line.split() for line in capsys.readouterr().out.splitlines()[1:]}


def test_a_clean_job_lints_and_its_shots_move_to_linted(jobs, capsys):
    rf_dir = make_job(jobs, job())
    rf.main(["lint", JOB])
    out = capsys.readouterr().out
    assert "0 FAIL, 0 WARN" in out and "Tony still looks" in out
    assert {(s["lint"], s["status"]) for s in shots(rf_dir).values()} == {("pass", "linted")}


def test_a_fail_prints_exits_non_zero_and_shows_in_status(jobs, capsys):
    rf_dir = make_job(jobs, job(lane="example-realty"))
    with pytest.raises(SystemExit) as stop:
        rf.main(["lint", JOB])
    assert stop.value.code == 1
    assert "FAIL C11 job:" in capsys.readouterr().out
    assert {(s["lint"], s["status"]) for s in shots(rf_dir).values()} == {("FAIL", "drafted")}
    assert "FAIL" in status_rows(capsys)["S02"]


def test_a_warning_prints_and_the_shot_still_moves_on(jobs, capsys):
    rf_dir = make_job(jobs, job(still(), clip(swap(FOX, " Intelligible spoken words, mouth in sync.", ""))))
    rf.main(["lint", JOB])
    assert "WARN C6 S02:" in capsys.readouterr().out
    assert (shots(rf_dir)["S02"]["lint"], shots(rf_dir)["S02"]["status"]) == ("WARN", "linted")
    assert shots(rf_dir)["S01"]["lint"] == "pass"


def test_one_shot_can_be_linted_on_its_own(jobs, capsys):
    rf_dir = make_job(jobs, job(still("A red fox in a doorway."), clip()))
    rf.main(["lint", JOB, "--shot", "S02"])
    assert "S01" not in capsys.readouterr().out
    assert "lint" not in shots(rf_dir)["S01"] and shots(rf_dir)["S02"]["lint"] == "pass"


def test_a_packed_shot_that_now_fails_drops_back_to_drafted(jobs):
    rf_dir = make_job(jobs, job(still(status="packed"), clip(swap(FOX, "Marcus lifts his hand", "Tony lifts his hand"),
                                                             status="packed")))
    with pytest.raises(SystemExit):
        rf.main(["lint", JOB])
    assert (shots(rf_dir)["S01"]["status"], shots(rf_dir)["S02"]["status"]) == ("packed", "drafted")


def test_any_fail_blocks_the_pack_and_nothing_is_written(jobs, capsys):
    rf_dir = make_job(jobs, job(lane="example-realty"))
    with pytest.raises(SystemExit):
        rf.main(["pack", JOB])
    captured = capsys.readouterr()
    assert "FAIL C11 job:" in captured.out and "lint FAIL blocks the pack" in captured.err
    assert not (rf_dir / "pack.md").exists() and not (rf_dir / "prompts").exists()


def test_a_refused_pack_leaves_no_shot_looking_packed(jobs, capsys):
    rf_dir = make_job(jobs, job(still(status="packed", lint="pass"),
                                clip(swap(FOX, "Marcus lifts his hand", "Tony lifts his hand"),
                                     status="packed", lint="pass")))
    with pytest.raises(SystemExit):
        rf.main(["pack", JOB])
    assert (shots(rf_dir)["S02"]["lint"], shots(rf_dir)["S02"]["status"]) == ("FAIL", "drafted")
    assert "drafted" in status_rows(capsys)["S02"]


def test_warnings_print_and_the_pack_goes_ahead(jobs, capsys):
    rf_dir = make_job(jobs, job(still(), clip(swap(FOX, " Intelligible spoken words, mouth in sync.", ""))))
    rf.main(["pack", JOB])
    assert "WARN C6 S02:" in capsys.readouterr().out
    assert (rf_dir / "pack.md").exists()
    assert {(s["lint"], s["status"]) for s in shots(rf_dir).values()} == {("pass", "packed"), ("WARN", "packed")}


def test_the_example_realty_override_is_read_from_the_brief(jobs):
    rf_dir = make_job(jobs, job(lane="example-realty"),
                      brief='# Real-footage brief\n\nlane_override: "tony-approved"\n')
    rf.main(["lint", JOB])
    assert {s["lint"] for s in shots(rf_dir).values()} == {"pass"}
