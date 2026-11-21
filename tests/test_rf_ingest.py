"""rf ingest: a file the generator returned (or Tony brought) is checked, copied into the
job, hashed and ledgered; the original is never touched. Media is made locally with
ffmpeg: no vendor files, no network."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import common  # noqa: E402
import rf  # noqa: E402


def ff(*args):
    subprocess.run(["ffmpeg", "-y", "-v", "error", *args], check=True)


def make_video(path, w=360, h=640, dur=2.0, fps=24, audio=True):
    args = ["-f", "lavfi", "-i", f"color=c=orange:s={w}x{h}:d={dur}:r={fps}"]
    if audio:
        args += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={dur}", "-shortest"]
    ff(*args, "-pix_fmt", "yuv420p", str(path))
    return path


@pytest.fixture
def job(tmp_path, monkeypatch):
    """A fresh real-footage job, plus a folder outside it where returned files arrive."""
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    monkeypatch.setattr(common, "JOBS_DIR", jobs)
    rf.main(["new", "fox", "--idea", "a fox says no"])
    (jdir,) = jobs.iterdir()
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    return jdir, downloads


def ledger(jdir):
    path = jdir / "rf" / "ledger.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def shot(jdir, shot_id):
    data = json.loads((jdir / "rf" / "shots.json").read_text())
    return next(s for s in data["shots"] if s["id"] == shot_id)


def test_a_returned_clip_is_copied_hashed_and_ledgered_with_the_engine_details(job):
    jdir, downloads = job
    src = make_video(downloads / "seedance draft.mp4")
    original, mtime = src.read_bytes(), src.stat().st_mtime
    rf.main(["ingest", jdir.name, str(src), "--shot", "S02", "--model", "byte-plus-seedance-2-5-draft",
             "--creation", "cr_123", "--credits", "42"])

    copy = jdir / "rf" / "returns" / "S02_take1.mp4"
    assert copy.read_bytes() == original
    assert src.read_bytes() == original and src.stat().st_mtime == mtime   # never edited
    (line,) = ledger(jdir)
    assert line["shot"] == "S02" and line["file"] == "rf/returns/S02_take1.mp4"
    assert line["sha256"] == hashlib.sha256(original).hexdigest()
    assert (line["provider"], line["model"], line["creation_id"], line["credits"]) == \
        ("openart", "byte-plus-seedance-2-5-draft", "cr_123", 42)
    assert line["resolution"] == "360x640" and line["fps"] == 24 and line["has_audio"] is True
    assert line["duration_s"] == pytest.approx(2.0, abs=0.1)
    assert line["prompt_sha256"] == hashlib.sha256(b"").hexdigest()   # the starter prompt is blank
    assert line["approved"] is False and line["ts"]
    assert shot(jdir, "S02")["status"] == "ingested"
    assert shot(jdir, "S02")["returns"] == ["rf/returns/S02_take1.mp4"]
    assert (jdir / "rf" / "returns" / "thumbs" / "S02_take1.jpg").stat().st_size > 0


def test_a_file_from_anywhere_else_is_ledgered_as_manual_and_takes_count_up(job):
    jdir, downloads = job
    rf.main(["ingest", jdir.name, str(make_video(downloads / "a.mp4")), "--shot", "S02"])
    rf.main(["ingest", jdir.name, str(make_video(downloads / "b.mov", audio=False)), "--shot", "S02"])
    first, second = ledger(jdir)
    assert (first["provider"], first["model"], first["creation_id"], first["credits"]) == \
        ("manual", None, None, None)
    assert second["file"] == "rf/returns/S02_take2.mov" and second["has_audio"] is False
    assert shot(jdir, "S02")["returns"] == ["rf/returns/S02_take1.mp4", "rf/returns/S02_take2.mov"]


def test_a_still_takes_an_image_and_records_no_duration(job):
    jdir, downloads = job
    still = downloads / "ref.png"
    ff("-f", "lavfi", "-i", "color=c=teal:s=576x1024", "-frames:v", "1", str(still))
    rf.main(["ingest", jdir.name, str(still), "--shot", "S01"])
    (line,) = ledger(jdir)
    assert (line["file"], line["resolution"], line["duration_s"], line["fps"], line["has_audio"]) == \
        ("rf/returns/S01_take1.png", "576x1024", None, None, False)


def make_bad(downloads, kind):
    """A file ingest must refuse, and the words its refusal must contain."""
    if kind == "archive":
        import zipfile
        path = downloads / "takes.zip"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("take.mp4", b"not really")
        return path, "archive"
    if kind == "renamed archive":
        import zipfile
        path = downloads / "take.mp4"
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("inner.mp4", b"x" * 64)
        return path, "archive"
    if kind == "empty":
        path = downloads / "empty.mp4"
        path.write_bytes(b"")
        return path, "is empty (0 bytes)"
    if kind == "unknown":
        path = downloads / "notes.mp4"
        path.write_text("this is a text file wearing an mp4 name\n" * 20)
        return path, "not a video or image"
    if kind == "sound only":
        path = downloads / "voice.m4a"
        ff("-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(path))
        return path, "not a video or image"
    raise ValueError(kind)


@pytest.mark.parametrize("kind", ["archive", "renamed archive", "empty", "unknown", "sound only"])
def test_files_that_are_not_pictures_are_refused_and_nothing_is_written(job, capsys, kind):
    jdir, downloads = job
    bad, words = make_bad(downloads, kind)
    with pytest.raises(SystemExit):
        rf.main(["ingest", jdir.name, str(bad), "--shot", "S02"])
    assert words in capsys.readouterr().err
    assert ledger(jdir) == [] and not (jdir / "rf" / "returns").exists()
    assert shot(jdir, "S02")["status"] == "drafted"


def test_one_bad_file_in_a_batch_ingests_none_of_them(job, capsys):
    jdir, downloads = job
    good = make_video(downloads / "good.mp4")
    bad, _ = make_bad(downloads, "empty")
    with pytest.raises(SystemExit):
        rf.main(["ingest", jdir.name, str(good), str(bad), "--shot", "S02"])
    assert ledger(jdir) == [] and not (jdir / "rf" / "returns").exists()


@pytest.mark.parametrize("shot_id,make,words", [
    ("S02", "image", "is an image, but S02 is a clip shot"),
    ("S01", "video", "is a video, but S01 is a still shot"),
])
def test_a_file_of_the_wrong_kind_for_its_shot_is_refused(job, capsys, shot_id, make, words):
    jdir, downloads = job
    if make == "image":
        src = downloads / "frame.png"
        ff("-f", "lavfi", "-i", "color=c=teal:s=360x640", "-frames:v", "1", str(src))
    else:
        src = make_video(downloads / "clip.mp4")
    with pytest.raises(SystemExit):
        rf.main(["ingest", jdir.name, str(src), "--shot", shot_id])
    assert words in capsys.readouterr().err
    assert ledger(jdir) == []


def test_a_clip_shaped_unlike_its_shot_is_kept_with_a_warning(job, capsys):
    jdir, downloads = job
    rf.main(["ingest", jdir.name, str(make_video(downloads / "wide.mp4", w=640, h=360)), "--shot", "S02"])
    assert "640x360, not 9:16" in capsys.readouterr().out
    assert len(ledger(jdir)) == 1


def test_an_unknown_shot_is_refused(job, capsys):
    jdir, downloads = job
    with pytest.raises(SystemExit):
        rf.main(["ingest", jdir.name, str(make_video(downloads / "a.mp4")), "--shot", "S09"])
    assert "no shot S09 (have: S01, S02)" in capsys.readouterr().err


def test_a_model_tony_names_without_a_creation_id_is_still_manual(job):
    """Only the engine has an OpenArt creation id; a model on its own is Tony's word."""
    jdir, downloads = job
    rf.main(["ingest", jdir.name, str(make_video(downloads / "a.mp4")), "--shot", "S02",
             "--model", "seedance-from-the-web-app"])
    (line,) = ledger(jdir)
    assert (line["provider"], line["model"]) == ("manual", "seedance-from-the-web-app")


def test_credits_without_a_creation_id_are_refused(job, capsys):
    jdir, downloads = job
    with pytest.raises(SystemExit):
        rf.main(["ingest", jdir.name, str(make_video(downloads / "a.mp4")), "--shot", "S02",
                 "--credits", "40"])
    assert "--creation" in capsys.readouterr().err
    assert ledger(jdir) == []


def test_a_failure_part_way_through_a_batch_leaves_nothing_behind(job, monkeypatch):
    """The checks pass, then making the second file's thumbnail fails: no copy, no ledger
    line and no status change may survive from the first file either."""
    import rf_ingest
    jdir, downloads = job
    real, calls = rf_ingest.thumbnail, []

    def flaky(path):
        calls.append(path)
        if len(calls) == 2:
            raise subprocess.CalledProcessError(1, "ffmpeg")
        return real(path)

    monkeypatch.setattr(rf_ingest, "thumbnail", flaky)
    with pytest.raises(SystemExit):
        rf.main(["ingest", jdir.name, str(make_video(downloads / "a.mp4")),
                 str(make_video(downloads / "b.mp4")), "--shot", "S02"])
    returns = jdir / "rf" / "returns"
    assert ledger(jdir) == []
    assert not [p for p in returns.rglob("*") if p.is_file()] if returns.exists() else True
    assert shot(jdir, "S02")["status"] == "drafted"


def write_record(path, history_id="cr_123"):
    """What the engine saves for one OpenArt call: the creation record, the quote and the
    balance on either side of the call."""
    record = {"creation": {"historyId": history_id, "prompt": "REFERENCES: image 1 supplies only the fox.",
                           "suggestedActions": [{"kind": "draft_upgrade", "credits": 2565}]},
              "quote": {"totalCredits": 42}, "balance_before": 100, "balance_after": 58}
    path.write_text(json.dumps(record))
    return record


def test_the_calls_record_is_kept_beside_the_ledger_line(job):
    jdir, downloads = job
    src = make_video(downloads / "draft.mp4")
    record = write_record(downloads / "cr_123.json")
    rf.main(["ingest", jdir.name, str(src), "--shot", "S02", "--model", "byte-plus-seedance-2-5-draft",
             "--creation", "cr_123", "--credits", "42", "--record", str(downloads / "cr_123.json")])

    kept = jdir / "rf" / "openart" / "cr_123.json"
    assert kept.read_bytes() == (downloads / "cr_123.json").read_bytes()   # kept byte for byte
    assert json.loads(kept.read_text()) == record
    assert json.loads((downloads / "cr_123.json").read_text()) == record   # never edited
    (line,) = ledger(jdir)
    assert line["record"] == "rf/openart/cr_123.json"


def test_a_raw_creation_record_is_accepted_as_well(job):
    jdir, downloads = job
    (downloads / "raw.json").write_text(json.dumps({"historyId": "cr_123", "status": "COMPLETED"}))
    rf.main(["ingest", jdir.name, str(make_video(downloads / "draft.mp4")), "--shot", "S02",
             "--creation", "cr_123", "--credits", "42", "--record", str(downloads / "raw.json")])
    (line,) = ledger(jdir)
    assert line["record"] == "rf/openart/cr_123.json"


def test_without_a_record_the_ledger_says_so(job):
    jdir, downloads = job
    rf.main(["ingest", jdir.name, str(make_video(downloads / "a.mp4")), "--shot", "S02"])
    (line,) = ledger(jdir)
    assert line["record"] is None
    assert not (jdir / "rf" / "openart").exists()


@pytest.mark.parametrize("case, words", [
    ("another creation", "cr_999"),
    ("no creation id", "--creation"),
    ("no history id", "historyId"),
    ("not json", "JSON"),
    ("missing file", "no such"),
])
def test_a_record_that_does_not_belong_to_the_call_is_refused(job, capsys, case, words):
    jdir, downloads = job
    record = downloads / "record.json"
    args = ["ingest", jdir.name, str(make_video(downloads / "a.mp4")), "--shot", "S02",
            "--creation", "cr_123", "--credits", "42", "--record", str(record)]
    if case == "another creation":
        write_record(record, history_id="cr_999")
    elif case == "no creation id":
        write_record(record)
        args = [a for a in args if a not in ("--creation", "cr_123", "--credits", "42")]
    elif case == "no history id":
        record.write_text(json.dumps({"quote": {"totalCredits": 42}}))
    elif case == "not json":
        record.write_text("creation zudNRVgkRQHzJhICPk5S, 480cr")
    with pytest.raises(SystemExit):
        rf.main(args)
    assert words in capsys.readouterr().err
    assert ledger(jdir) == []
    assert not (jdir / "rf" / "returns").exists() or not any((jdir / "rf" / "returns").glob("S02_*"))
    assert not (jdir / "rf" / "openart").exists()


def test_a_record_that_cannot_be_kept_leaves_nothing_behind(job, capsys):
    jdir, downloads = job
    write_record(downloads / "cr_123.json")
    (jdir / "rf" / "openart").write_text("a file where the folder should be")
    with pytest.raises(SystemExit):
        rf.main(["ingest", jdir.name, str(make_video(downloads / "a.mp4")), "--shot", "S02",
                 "--creation", "cr_123", "--credits", "42", "--record", str(downloads / "cr_123.json")])
    assert "record" in capsys.readouterr().err
    assert ledger(jdir) == []
    assert not any((jdir / "rf" / "returns").glob("S02_*"))
    assert not any((jdir / "rf" / "returns" / "thumbs").glob("S02_*"))


def test_one_creation_keeps_one_record(job, capsys):
    jdir, downloads = job
    write_record(downloads / "cr_123.json")
    args = ["--shot", "S02", "--creation", "cr_123", "--credits", "42", "--record", str(downloads / "cr_123.json")]
    rf.main(["ingest", jdir.name, str(make_video(downloads / "a.mp4")), *args])
    rf.main(["ingest", jdir.name, str(make_video(downloads / "b.mp4")), *args])   # the same record again
    assert len(ledger(jdir)) == 2

    record = json.loads((downloads / "cr_123.json").read_text())
    (downloads / "cr_123.json").write_text(json.dumps({**record, "balance_after": 1}))
    with pytest.raises(SystemExit):
        rf.main(["ingest", jdir.name, str(make_video(downloads / "c.mp4")), *args])
    assert "different record" in capsys.readouterr().err
    assert len(ledger(jdir)) == 2
    assert json.loads((jdir / "rf" / "openart" / "cr_123.json").read_text())["balance_after"] == 58
