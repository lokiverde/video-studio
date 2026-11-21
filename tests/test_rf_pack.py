"""The prompt pack: each shot's camera style and behavior picked from the library, and
the pack the engine generates from (docs/briefs/2026-10-24-realistic-footage.md, 5.2,
5.3, 6.4 and 6.5). Everything is local: no generator, no network."""
import json
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from rf_fixtures import FOX, MONTAGE  # noqa: E402

import common  # noqa: E402
import rf  # noqa: E402


@pytest.fixture
def jobs(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "JOBS_DIR", tmp_path)
    return tmp_path


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Packing is local: any attempt to open a connection fails the test."""
    def refuse(*args, **kwargs):
        raise AssertionError("rf pack tried to use the network")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


def only_job(root):
    (jdir,) = [p for p in root.iterdir() if p.is_dir()]
    return jdir


def test_new_puts_the_chosen_style_and_technique_on_the_shots(jobs):
    rf.main(["new", "fox", "--idea", "x", "--style", "phone-snapshot", "--technique", "whip-pan"])
    still, clip = json.loads((only_job(jobs) / "rf" / "shots.json").read_text())["shots"]
    assert still["style"] == clip["style"] == "phone-snapshot"
    assert clip["technique"] == "whip-pan"
    assert "technique" not in still


@pytest.mark.parametrize("flag,bad,known", [("--style", "vhs-glow", "phone-snapshot"),
                                            ("--technique", "dolly-zoom", "whip-pan")])
def test_new_rejects_a_name_that_is_not_in_the_library(jobs, capsys, flag, bad, known):
    with pytest.raises(SystemExit):
        rf.main(["new", "fox", "--idea", "x", flag, bad])
    err = capsys.readouterr().err
    assert f"'{bad}'" in err and known in err     # names the bad one and lists the real ones
    assert not list(jobs.iterdir())               # nothing written


JOB = "20261024-101500-fox"
STILL_PROMPT = ("Candid disposable camera snapshot, wide fixed lens, chest height, crooked crop. "
                "A fox in a call-center headset at a cluttered desk. Harsh flash; film grain.")
CLIP_PROMPT = FOX         # lint-clean: spec Appendix A
CLOSE_PROMPT = MONTAGE    # lint-clean montage


def make_job(jobs, edit=None):
    """A lint-clean job whose shot list names its clip before its still, with one still
    already returned and ledgered (its quoted credits sit in the ledger, never the pack)."""
    rf_dir = jobs / JOB / "rf"
    rf_dir.mkdir(parents=True)
    shots = {"job": JOB, "idea": "a fox says no to a scam call", "lane": "techtony",
             "ai_disclosure": True, "likeness": {},
             "defaults": {"provider": "openart", "aspect": "9:16", "draft_first": True,
                          "ref_tag_syntax": "unverified"},
             "shots": [
                 {"id": "S02", "kind": "clip", "technique": "whip-pan", "style": "phone-snapshot",
                  "model": {"draft": "byte-plus-seedance-2-5-draft", "final": "byte-plus-seedance-2-5"},
                  "mode": "element2video", "duration_s": 8,
                  "refs": [{"label": "IMG1", "file": "rf/returns/S01_take1.png",
                            "role": "supplies only the fox and the desk"},
                           {"label": "IMG2", "file": "characters/fox/sheet.png",
                            "role": "supplies only the fox's headset and lanyard"}],
                  "dialogue": [{"speaker": "Marcus", "line": "Oh, no.", "voice": "generated"}],
                  "prompt": CLIP_PROMPT,
                  "settings": {"draft": "480p", "final": "1080p", "aspect": "9:16"},
                  "status": "drafted", "returns": []},
                 {"id": "S01", "kind": "still", "purpose": "reference frame for S02",
                  "model": "nano-banana-pro", "mode": "text2image", "style": "disposable-flash",
                  "refs": [], "prompt": STILL_PROMPT,
                  "settings": {"resolution": "2K", "aspect": "9:16"},
                  "status": "ingested", "returns": ["rf/returns/S01_take1.png"]},
                 {"id": "S03", "kind": "clip", "technique": "handheld", "style": "disposable-flash",
                  "model": {"draft": "byte-plus-seedance-2-5-draft", "final": "byte-plus-seedance-2-5"},
                  "mode": "text2video", "duration_s": 5, "refs": [], "dialogue": [],
                  "prompt": CLOSE_PROMPT,
                  "settings": {"draft": "480p", "final": "1080p", "aspect": "9:16"},
                  "status": "drafted", "returns": []},
             ]}
    if edit:
        edit(shots)
    (rf_dir / "shots.json").write_text(json.dumps(shots, indent=2))
    (rf_dir / "ledger.jsonl").write_text(json.dumps(
        {"shot": "S01", "file": "rf/returns/S01_take1.png", "provider": "openart",
         "model": "nano-banana-pro", "credits": 40}) + "\n")
    return rf_dir


def sections(pack):
    """The pack split into its per-shot sections, keyed by shot id, in file order."""
    parts = pack.split("\n## ")[1:]
    return {part.split()[0]: part for part in parts}


def test_pack_lists_stills_before_clips(jobs):
    rf_dir = make_job(jobs)
    rf.main(["pack", JOB])
    assert list(sections((rf_dir / "pack.md").read_text())) == ["S01", "S02", "S03"]


def test_each_packed_shot_carries_what_the_engine_needs(jobs):
    rf_dir = make_job(jobs)
    rf.main(["pack", JOB])
    still, clip, close = sections((rf_dir / "pack.md").read_text()).values()
    assert "nano-banana-pro" in still and "text2image" in still
    assert "2K" in still and "disposable-flash" in still and STILL_PROMPT in still
    assert "byte-plus-seedance-2-5-draft" in clip and "byte-plus-seedance-2-5," in clip
    assert "element2video" in clip and "480p" in clip and "1080p" in clip and "8s" in clip
    assert "- [ ] IMG1: rf/returns/S01_take1.png. Role: supplies only the fox and the desk" in clip
    assert "whip-pan" in clip and "phone-snapshot" in clip and "Oh, no." in clip
    assert CLIP_PROMPT in clip and CLOSE_PROMPT in close
    for section in (clip, close):
        assert "Run the final only after Tony passes the draft" in section
    assert "final only after Tony" not in still      # a still has no draft stage


def test_pack_writes_one_text_file_per_prompt(jobs):
    rf_dir = make_job(jobs)
    (rf_dir / "prompts").mkdir()
    (rf_dir / "prompts" / "S09.txt").write_text("a shot since removed from the list")
    rf.main(["pack", JOB])
    files = {p.name: p.read_text().strip() for p in (rf_dir / "prompts").iterdir()}
    assert files == {"S01.txt": STILL_PROMPT, "S02.txt": CLIP_PROMPT, "S03.txt": CLOSE_PROMPT}


def test_no_price_appears_anywhere_in_the_pack(jobs):
    rf_dir = make_job(jobs)
    rf.main(["pack", JOB])
    written = [rf_dir / "pack.md", *(rf_dir / "prompts").iterdir()]
    for path in written:
        text = path.read_text().lower()
        for word in ("credit", "price", "cost", "$", "usd"):
            assert word not in text, (path.name, word)


@pytest.mark.parametrize("edit,message", [
    (lambda d: d["shots"][2].update(prompt=" "), "shot S03 has no prompt"),
    (lambda d: d["shots"][0].update(style="vhs-glow"), "style 'vhs-glow' is not in"),
    (lambda d: d["shots"][2].update(technique="dolly-zoom"), "technique 'dolly-zoom' is not in"),
    (lambda d: d["shots"][2].update(id="S02"), "shot id 'S02' is used twice"),
    (lambda d: d["shots"][2].update(id="../S03"), "shot id '../S03'"),
    (lambda d: d["shots"][2].pop("mode"), "shot S03 has no 'mode'"),
    (lambda d: d["shots"][0]["settings"].update(credits=300), "shot S02: settings carry a price"),
    (lambda d: d["shots"][0]["settings"].update(note="$4.20 a run"), "shot S02: settings carry a price"),
    (lambda d: d["defaults"].update(draft_first=False), "'draft_first' must stay true"),
])
def test_pack_refuses_a_shot_list_it_cannot_pack(jobs, capsys, edit, message):
    rf_dir = make_job(jobs, edit)
    with pytest.raises(SystemExit):
        rf.main(["pack", JOB])
    assert message in capsys.readouterr().err
    assert not (rf_dir / "pack.md").exists() and not (rf_dir / "prompts").exists()


def test_the_pack_says_which_shots_already_came_back(jobs):
    rf_dir = make_job(jobs)
    rf.main(["pack", JOB])
    still, clip, _ = sections((rf_dir / "pack.md").read_text()).values()
    assert "Status: ingested (returns: rf/returns/S01_take1.png)" in still
    assert "Status: packed" in clip


def test_a_line_without_a_voice_is_not_given_one(jobs):
    rf_dir = make_job(jobs, lambda d: d["shots"][0]["dialogue"][0].pop("voice"))
    rf.main(["pack", JOB])
    clip = sections((rf_dir / "pack.md").read_text())["S02"]
    assert '- Marcus: "Oh, no."' in clip and "None" not in clip


def test_packed_shots_show_as_packed_and_returned_ones_keep_their_status(jobs, capsys):
    make_job(jobs)
    rf.main(["pack", JOB])
    capsys.readouterr()
    rf.main(["status", JOB])
    rows = {line.split()[0]: line.split() for line in capsys.readouterr().out.splitlines()[1:]}
    assert "packed" in rows["S02"] and "packed" in rows["S03"]
    assert "ingested" in rows["S01"]
