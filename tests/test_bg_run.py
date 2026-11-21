"""Background runner (scripts/bg_run.py): long renders run detached from the Claude session,
at low priority, and ping Telegram when they end."""
import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import bg_run  # noqa: E402

NO_TELEGRAM = {}


def test_duration_reads_like_a_person_would_say_it():
    assert bg_run.fmt_duration(42) == "42s"
    assert bg_run.fmt_duration(192) == "3m 12s"
    assert bg_run.fmt_duration(3840) == "1h 04m"


def test_success_message_names_the_job_and_time():
    text = bg_run.build_message("ai20-l4", 0, 725, ["last line"])
    assert "ai20-l4" in text and "done" in text and "12m 05s" in text
    assert "last line" not in text


def test_failure_message_carries_the_exit_code_and_log_tail():
    text = bg_run.build_message("ai20-l4", 2, 30, ["Traceback", "ValueError: bad"])
    assert "FAILED" in text and "exit 2" in text
    assert "ValueError: bad" in text


def test_labels_must_be_safe_file_names():
    assert bg_run.check_label("talking-head_2026.v2") == "talking-head_2026.v2"
    for bad in ("", "../x", "a b", "a/b"):
        with pytest.raises(SystemExit):
            bg_run.check_label(bad)


def test_telegram_is_skipped_without_credentials():
    calls = []
    assert bg_run.send_telegram("hi", NO_TELEGRAM, opener=calls.append) is False
    assert calls == []


def test_telegram_posts_to_the_configured_chat():
    seen = []

    class Reply:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def opener(req, timeout=None):
        seen.append(req)
        return Reply()

    cfg = {"TELEGRAM_BOT_TOKEN": "123:abc", "TELEGRAM_CHAT_ID": "42"}
    assert bg_run.send_telegram("render done", cfg, opener=opener) is True
    assert seen[0].full_url == "https://api.telegram.org/bot123:abc/sendMessage"
    assert b"chat_id=42" in seen[0].data and b"render+done" in seen[0].data


def test_child_records_success_and_notifies(tmp_path):
    sent = []
    rc = bg_run.run_child("ok-job", [sys.executable, "-c", "print('rendered')"], tmp_path,
                          NO_TELEGRAM, notify=lambda text, cfg: sent.append(text))
    status = json.loads((tmp_path / "ok-job.status.json").read_text())
    assert rc == 0 and status["rc"] == 0 and status["state"] == "done"
    assert "rendered" in Path(status["log"]).read_text()
    assert len(sent) == 1 and "done" in sent[0]


def test_child_records_failure(tmp_path):
    sent = []
    rc = bg_run.run_child("bad-job", [sys.executable, "-c", "import sys; sys.exit(3)"], tmp_path,
                          NO_TELEGRAM, notify=lambda text, cfg: sent.append(text))
    status = json.loads((tmp_path / "bad-job.status.json").read_text())
    assert rc == 3 and status["state"] == "failed"
    assert "FAILED" in sent[0]


def test_launch_returns_at_once_and_the_job_finishes_on_its_own(tmp_path):
    started = time.monotonic()
    pid, log = bg_run.launch("detached", [sys.executable, "-c", "import time; time.sleep(1)"],
                             tmp_path, ping=False)
    assert pid > 0 and time.monotonic() - started < 1
    status_file = tmp_path / "detached.status.json"
    for _ in range(100):
        if status_file.exists() and json.loads(status_file.read_text())["state"] != "running":
            break
        time.sleep(0.1)
    assert json.loads(status_file.read_text())["state"] == "done"
