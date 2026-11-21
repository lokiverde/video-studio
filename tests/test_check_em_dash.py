"""check_em_dash: the house rule (no em dashes) checked on the lines a change adds, so
files that already carry one do not block unrelated work. Runs against a throwaway git
repo; the character is always written as an escape here."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_em_dash  # noqa: E402

DASH = "\u2014"


def git(repo, *args):
    subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *args],
                   cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repo whose first commit already has an em dash in an old doc."""
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "old.md").write_text(f"an old line {DASH} left alone\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "base")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_added_lines_carry_their_file_and_new_line_number():
    diff = "\n".join([
        "diff --git a/doc.md b/doc.md", "--- a/doc.md", "+++ b/doc.md",
        "@@ -3,0 +4,2 @@", f"+fine", f"+not fine {DASH} here",
        "@@ -9 +11 @@", f"-gone {DASH}", "+kept",
        "diff --git a/gone.md b/gone.md", "--- a/gone.md", "+++ /dev/null", "@@ -1 +0,0 @@", f"-{DASH}",
    ])
    assert check_em_dash.offenders(diff) == [("doc.md", 5, f"not fine {DASH} here")]


def test_a_staged_line_with_an_em_dash_is_refused(repo, capsys):
    (repo / "new.md").write_text(f"first line\nsecond {DASH} line\n")
    git(repo, "add", "new.md")
    assert check_em_dash.main(["--staged"]) == 1
    err = capsys.readouterr().err
    assert "new.md:2" in err and "comma" in err


def test_old_em_dashes_and_escaped_ones_pass(repo):
    (repo / "old.md").write_text(f"an old line {DASH} left alone\na new clean line\n")
    (repo / "code.py").write_text('DASH = "\\u2014"\n')
    git(repo, "add", ".")
    assert check_em_dash.main(["--staged"]) == 0


def test_a_branch_is_checked_against_its_base(repo):
    git(repo, "checkout", "-q", "-b", "feature")
    (repo / "notes.md").write_text(f"a note {DASH} with a dash\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "notes")
    assert check_em_dash.main(["--base", "main"]) == 1
    git(repo, "checkout", "-q", "main")
    assert check_em_dash.main(["--base", "main"]) == 0


def test_an_added_line_that_starts_with_two_pluses_is_still_an_added_line():
    diff = "\n".join([
        "diff --git a/doc.md b/doc.md", "--- a/doc.md", "+++ b/doc.md", "@@ -0,0 +1,2 @@",
        "+++ a line that starts with two pluses", f"+then a dash {DASH}",
    ])
    assert check_em_dash.offenders(diff) == [("doc.md", 2, f"then a dash {DASH}")]


def test_a_file_with_a_non_ascii_name_is_checked(repo):
    (repo / "caf\u00e9 notes.md").write_text(f"un caf\u00e9 {DASH} noir\n")
    git(repo, "add", ".")
    assert check_em_dash.main(["--staged"]) == 1
