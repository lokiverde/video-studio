"""Script history learns the ai-footage format: log-script records format, technique and
style for an AI footage video, and every reader keeps working on old and new lines
(docs/briefs/2026-10-24-realistic-footage.md, 5.6 and 5.8)."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import common  # noqa: E402
import fv  # noqa: E402
import write_script  # noqa: E402

OLD_LINE = {"date": "2026-10-01", "job_id": "20261001-090000-springfield", "title": "Old video",
            "platform": "multi", "hook_category": "question", "framework": "pas", "tone": "calm",
            "opening_phrase": "Springfield has no rent control", "cta": "", "topic": "", "angle": "",
            "length_s": 95}


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A throwaway repo root (history/) and jobs folder holding one rendered job."""
    monkeypatch.setattr(common, "ROOT", tmp_path)
    monkeypatch.setattr(common, "JOBS_DIR", tmp_path / "jobs")
    job = tmp_path / "jobs" / "20261024-100000-fox"
    job.mkdir(parents=True)
    (job / "state.json").write_text(json.dumps({"title": "Do not reply to that email", "duration_s": 42}))
    (tmp_path / "history").mkdir()
    (tmp_path / "history" / "scripts.jsonl").write_text(json.dumps(OLD_LINE) + "\n")
    return tmp_path


def log_script(monkeypatch, *extra):
    monkeypatch.setattr(sys, "argv", ["fv.py", "log-script", "20261024-100000-fox", "--hook", "warning",
                                      "--framework", "cold-open", "--tone", "dry",
                                      "--opening", "Do not reply to that email", *extra])
    fv.main()


def history(repo):
    return [json.loads(line) for line in (repo / "history" / "scripts.jsonl").read_text().splitlines()]


def test_log_script_records_format_technique_and_style(repo, monkeypatch):
    log_script(monkeypatch, "--format", "ai-footage", "--technique", "whip-pan", "--style", "phone-snapshot")
    entry = history(repo)[-1]
    assert (entry["format"], entry["technique"], entry["style"]) == ("ai-footage", "whip-pan", "phone-snapshot")
    assert entry["hook_category"] == "warning" and entry["length_s"] == 42


def test_a_plain_log_line_is_unchanged(repo, monkeypatch):
    log_script(monkeypatch)
    assert not {"format", "technique", "style"} & set(history(repo)[-1])


def test_readers_handle_old_and_new_lines_together(repo, monkeypatch, capsys):
    log_script(monkeypatch, "--format", "ai-footage", "--technique", "whip-pan", "--style", "phone-snapshot")
    monkeypatch.setattr(sys, "argv", ["fv.py", "script-history"])
    fv.main()
    out = capsys.readouterr().out
    assert "Old video" in out and "Do not reply to that email" in out
    recent = write_script.recent_history()
    assert "Springfield has no rent control" in recent and "Do not reply to that email" in recent
