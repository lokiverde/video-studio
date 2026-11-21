"""On the Mac mini, jobs/ is a link onto the external SSD. When the SSD is not
mounted, say so instead of a FileExistsError or a misleading "no such job"."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import common  # noqa: E402


@pytest.fixture
def unmounted(tmp_path, monkeypatch):
    link = tmp_path / "jobs"
    link.symlink_to(tmp_path / "Volumes" / "ExternalSSD" / "jobs")
    monkeypatch.setattr(common, "JOBS_DIR", link)
    return link


def test_new_job_names_the_missing_drive(unmounted, capsys):
    with pytest.raises(SystemExit):
        common.new_job(word="riverside")
    err = capsys.readouterr().err
    assert "ExternalSSD" in err and "mounted" in err


def test_existing_job_names_the_missing_drive(unmounted, capsys):
    with pytest.raises(SystemExit):
        common.job_dir("20261029-120000-riverside")
    err = capsys.readouterr().err
    assert "mounted" in err and "no such job" not in err


def test_a_mounted_link_works_like_a_folder(tmp_path, monkeypatch):
    drive = tmp_path / "ssd" / "jobs"
    drive.mkdir(parents=True)
    link = tmp_path / "jobs"
    link.symlink_to(drive)
    monkeypatch.setattr(common, "JOBS_DIR", link)
    job_id, jdir = common.new_job(word="riverside")
    assert (drive / job_id / "work").is_dir() and common.job_dir(job_id) == jdir
