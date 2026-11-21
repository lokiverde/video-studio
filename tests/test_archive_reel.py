"""Archive reel: the shot list is cut on a beat grid, the drums and sound effects follow the
story from the shot list, generated footage is tone-matched to the archive, and the preview
gate covers exactly what the contact sheet shows."""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import approval  # noqa: E402
import ar_lib  # noqa: E402

B = 0.604


def job(**over):
    base = {
        "title": "t", "music": {"beat": B}, "end": {"seconds": 1.0, "lines": ["AVAILABLE NOW"]},
        "shots": [
            {"id": "castle", "kind": "footage", "src": "a.mp4", "dur": 2 * B, "accent": "big",
             "logo": {"src": "logo.webp"}},
            {"id": "card", "kind": "card", "text": "Then came\nthe hero.", "dur": 2 * B, "accent": "big"},
            {"id": "horde", "kind": "footage", "src": "b.mp4", "dur": 2 * B, "sfx": ["crowd"]},
            {"id": "hero", "kind": "footage", "dir": "public", "src": "comp_hero.mp4", "dur": 2 * B, "accent": "big"},
            {"id": "reveal", "kind": "footage", "src": "c.mp4", "dur": 4 * B, "sfx": ["fire"],
             "tee": {"src": "tee_back.jpg", "at": 1.0, "fade": 0.4}},
        ],
    }
    base.update(over)
    return base


def test_timeline_starts_and_total():
    rows, total = ar_lib.timeline(job())
    assert [round(start, 3) for _, _, start in rows] == [0, 1.208, 2.416, 3.624, 4.832]
    assert total == round(12 * B, 3)


def test_a_valid_job_has_no_problems():
    assert ar_lib.validate(job()) == []


def test_cut_off_the_beat_grid_is_flagged():
    j = job()
    j["shots"][0]["dur"] = 1.0
    assert any("off the beat grid" in p for p in ar_lib.validate(j))


def test_missing_source_is_flagged_with_its_folder():
    seen = []

    def exists(kind, src):
        seen.append((kind, src))
        return src != "b.mp4"

    problems = ar_lib.validate(job(), exists)
    assert any("b.mp4" in p for p in problems)
    assert ("public", "comp_hero.mp4") in seen  # composites are looked up in public/


def test_logo_only_on_footage_and_card_needs_text():
    j = job()
    j["shots"][1]["logo"] = {"src": "logo.webp"}
    j["shots"][1]["text"] = ""
    problems = ar_lib.validate(j)
    assert any("logo can only be printed onto footage" in p for p in problems)
    assert any("card needs `text`" in p for p in problems)


def test_tee_fade_must_fit_and_stay_out_of_the_ui():
    j = job()
    j["shots"][4]["tee"] = {"src": "x", "at": 2.3, "fade": 0.4, "y": 0.9}
    problems = ar_lib.validate(j)
    assert any("fade runs past" in p for p in problems)
    assert any("platform UI" in p for p in problems)


def test_end_card_cannot_outrun_the_last_shot():
    assert any("end card" in p for p in ar_lib.validate(job(end={"seconds": 9, "lines": []})))


def test_big_accents_get_a_boom_and_a_roll_in():
    hits = ar_lib.drum_hits(job())
    booms = [t for t, kind, _ in hits if kind == "big"]
    assert 0 in booms and 1.208 in booms and 3.624 in booms
    roll = [t for t, kind, _ in hits if 3.624 - 2 * B - 0.01 < t < 3.624]
    assert len(roll) >= 3  # half-beat roll into the hero


def test_end_card_always_lands_on_a_boom():
    _, total = ar_lib.timeline(job())
    end_at = round(total - 1.0, 3)
    assert (end_at, "big", 1.0) in ar_lib.drum_hits(job())


def test_extra_hits_inside_a_shot():
    j = job()
    j["shots"][4]["hits"] = [{"at": 1.0, "kind": "big"}, 0.5]
    hits = ar_lib.drum_hits(j)
    assert (round(4.832 + 1.0, 3), "big", 1.0) in hits
    assert (round(4.832 + 0.5, 3), "low", 0.6) in hits


def test_cards_stay_silent_unless_accented():
    j = job()
    j["shots"][1].pop("accent")
    assert not any(abs(t - 1.208) < 1e-6 for t, _, _ in ar_lib.drum_hits(j))


def test_sfx_cues_follow_tags_and_reveals():
    cues = ar_lib.sfx_cues(job())
    assert ("roar", 2.416, 3.624) in [(k, round(a, 3), round(b, 3)) for k, a, b in cues]
    assert any(k == "fire" for k, _, _ in cues)
    assert not any(k == "whoosh" for k, _, _ in cues)  # tee reveals are silent by default (Tony, 2026-09-23)


def test_whoosh_only_when_a_tee_asks_for_it():
    j = job()
    tee_shot = next(s for s in j["shots"] if s.get("tee"))
    tee_shot["tee"]["whoosh"] = True
    whoosh = [c for c in ar_lib.sfx_cues(j) if c[0] == "whoosh"][0]
    assert abs(whoosh[1] - (4.832 + 1.0 - 0.35)) < 1e-6


def test_histogram_match_gives_generated_footage_the_archive_range():
    rng = np.random.default_rng(0)
    generated = rng.integers(0, 256, 50000).astype(np.uint8)  # full 0..255, like Veo
    archive = rng.integers(10, 191, 50000).astype(np.uint8)  # 1924 print: no true black or white
    mapping = ar_lib.match_mapping(generated, archive)
    assert np.all(np.diff(mapping) >= 0)  # monotonic, no tone inversions
    assert mapping[0] >= 9 and mapping[255] <= 191
    mapped = mapping[generated]
    assert abs(np.median(mapped) - np.median(archive)) < 3


def test_cube_file_shape():
    text = ar_lib.cube_1d(np.arange(256))
    lines = text.strip().split("\n")
    assert lines[0] == "LUT_1D_SIZE 256" and len(lines) == 257 and lines[-1] == "1.00000 1.00000 1.00000"


def reel(tmp_path):
    (tmp_path / "public").mkdir()
    (tmp_path / "product").mkdir()
    (tmp_path / "job.json").write_text(json.dumps(job()))
    (tmp_path / "public" / "comp_hero.mp4").write_bytes(b"v1")
    (tmp_path / "product" / "tee_back.jpg").write_bytes(b"t1")
    return tmp_path


def test_gate_covers_composites_and_product_images(tmp_path):
    d = reel(tmp_path)
    shown = approval.fingerprint(d, "archive-reel")
    (d / "public" / "comp_hero.mp4").write_bytes(b"v2")
    assert approval.fingerprint(d, "archive-reel") != shown
    (d / "public" / "comp_hero.mp4").write_bytes(b"v1")
    (d / "product" / "tee_back.jpg").write_bytes(b"t2")
    assert approval.fingerprint(d, "archive-reel") != shown


def test_soundtrack_and_post_copy_do_not_void_approval(tmp_path):
    d = reel(tmp_path)
    shown = approval.fingerprint(d, "archive-reel")
    j = json.loads((d / "job.json").read_text())
    j["audio"] = {"mode": "record", "file": "x.flac", "start": 1}
    j["post"] = {"caption": "new words"}
    (d / "job.json").write_text(json.dumps(j))
    assert approval.fingerprint(d, "archive-reel") == shown
    j["shots"][0]["dur"] = 3 * B
    (d / "job.json").write_text(json.dumps(j))
    assert approval.fingerprint(d, "archive-reel") != shown
