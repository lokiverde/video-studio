"""Job folders end in one word that says what the video is (Tony, 2026-09-27):
20260927-153037-riverside, not 20260927-153037-0651."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import common  # noqa: E402


def test_explicit_word_is_cleaned():
    assert common.job_word("Riverside") == "riverside"
    assert common.job_word("El Segundo!") == "elsegundo"
    assert common.job_word("AB-1482") == "ab1482"


def test_word_from_title_picks_the_subject_not_filler():
    assert common.job_word(title="Riverside Rent Control: No Ordinance, Still Rules (2026)") == "riverside"
    assert common.job_word(title="Ogdenville Rent Control: What Landlords Must Know") == "ogdenville"
    assert common.job_word(title="Self-Managed HOA? Answer These 5 Questions First") == "hoa"
    assert common.job_word(title="The Insurance Bill That Decides If You Keep The Building") == "insurance"


def test_no_word_and_no_title_falls_back_to_hex():
    word = common.job_word()
    assert len(word) == 4 and all(c in "0123456789abcdef" for c in word)


def test_word_is_capped():
    assert len(common.job_word("Supercalifragilisticexpialidocious")) <= 20


def test_new_job_uses_the_word(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "JOBS_DIR", tmp_path)
    job_id, jdir = common.new_job(word="Riverside")
    assert job_id.endswith("-riverside") and (jdir / "work").is_dir()
    again, _ = common.new_job(word="Riverside")
    assert again != job_id
