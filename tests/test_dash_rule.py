"""Tony's dash rule (2026-11-14): a folder whose name ends in "-" is done, so nothing updates
or uploads from it; a video file whose name ends in "-" is never uploaded."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import common  # noqa: E402
import dash_rule  # noqa: E402
import publish_rows  # noqa: E402
import upload  # noqa: E402

DONE_JOB = "20261025-235247-shelbyville-"
LIVE_JOB = "20261114-110920-datacenter"


def make_file(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return path


@pytest.fixture(autouse=True)
def no_override(monkeypatch):
    monkeypatch.delenv(dash_rule.OVERRIDE_ENV, raising=False)


def test_file_ending_in_dash_is_skipped():
    assert dash_rule.skipped_file(Path("out/clip-.mp4"))
    assert dash_rule.skipped_file(Path("out/clip.mp4-"))
    assert dash_rule.skipped_file(Path("out/short_3-.mp4"))


def test_dash_in_the_middle_of_a_name_does_not_count():
    assert not dash_rule.skipped_file(Path("out/final_9x16-preview.mp4"))
    assert not dash_rule.skipped_file(Path("out/final_9x16.mp4"))
    assert dash_rule.done_folder(Path(f"jobs/{LIVE_JOB}/out/final_9x16.mp4")) is None


def test_folder_ending_in_dash_is_done_at_any_depth(tmp_path):
    job = tmp_path / "jobs" / DONE_JOB
    assert dash_rule.done_folder(job / "out" / "final_9x16.mp4") == job
    assert dash_rule.done_folder(job / "out" / "shorts" / "short_1.mp4") == job
    assert dash_rule.done_folder(tmp_path / "listings-" / "a.mp4") == tmp_path / "listings-"


def test_job_folder_itself_counts_when_it_exists(tmp_path):
    job = tmp_path / DONE_JOB
    job.mkdir()
    assert dash_rule.done_folder(job) == job


def test_put_file_refuses_a_dashed_file_before_any_network(tmp_path):
    clip = make_file(tmp_path / LIVE_JOB / "out" / "clip-.mp4")
    with pytest.raises(dash_rule.DashRuleError, match="clip-.mp4"):
        upload.put_file({}, clip, "faceless/x/clip-.mp4")


def test_put_file_refuses_anything_in_a_done_folder(tmp_path):
    final = make_file(tmp_path / DONE_JOB / "out" / "final_9x16.mp4")
    with pytest.raises(dash_rule.DashRuleError, match=DONE_JOB):
        upload.put_file({}, final, "faceless/x/final_9x16.mp4")


def test_override_opens_a_done_folder_but_never_a_dashed_file(tmp_path, monkeypatch):
    monkeypatch.setenv(dash_rule.OVERRIDE_ENV, "1")
    dash_rule.check_upload(make_file(tmp_path / DONE_JOB / "out" / "final_9x16.mp4"))
    with pytest.raises(dash_rule.DashRuleError):
        dash_rule.check_upload(make_file(tmp_path / DONE_JOB / "out" / "short_2-.mp4"))


def test_keep_uploads_drops_dashed_files_and_says_so(tmp_path, capsys):
    out = tmp_path / LIVE_JOB / "out"
    keep = make_file(out / "short_1.mp4")
    drop = make_file(out / "short_2-.mp4")
    assert dash_rule.keep_uploads([keep, drop]) == [keep]
    assert "short_2-.mp4" in capsys.readouterr().out


def test_upload_run_refuses_a_done_job(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "JOBS_DIR", tmp_path)
    make_file(tmp_path / DONE_JOB / "out" / "final_9x16.mp4")
    with pytest.raises(dash_rule.DashRuleError, match=DONE_JOB):
        upload.run(DONE_JOB)


def test_write_commands_refuse_a_done_job(tmp_path):
    (tmp_path / DONE_JOB).mkdir()
    for cmd in ("finish", "publish", "regen-scene", "kit", "voiceover"):
        with pytest.raises(dash_rule.DashRuleError, match=DONE_JOB):
            dash_rule.guard_command(cmd, DONE_JOB, tmp_path)


def test_read_only_commands_still_work_on_a_done_job(tmp_path):
    (tmp_path / DONE_JOB).mkdir()
    dash_rule.guard_command("status", DONE_JOB, tmp_path)
    dash_rule.guard_command("save-theme", DONE_JOB, tmp_path)
    dash_rule.guard_command("finish", LIVE_JOB, tmp_path)
    dash_rule.guard_command("finish", None, tmp_path)


def test_publish_rows_leave_out_a_dashed_short_and_say_why(tmp_path, capsys):
    out = tmp_path / LIVE_JOB / "out"
    make_file(out / "short_1.mp4")
    make_file(out / "short_2-.mp4")
    job = {"shorts": [{"title": "One"}, {"title": "Two"}]}
    rows = publish_rows.build(tmp_path / LIVE_JOB, job, "LONG", probe=lambda _p: 30.0)
    assert [r["file"] for r in rows] == ["short_1.mp4"]
    said = capsys.readouterr().out
    assert "short_2-.mp4" in said and "not cut yet" not in said
