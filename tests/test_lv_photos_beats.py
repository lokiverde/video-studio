import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import lv_beats  # noqa: E402
import lv_photos  # noqa: E402

NAMES = ["3 kitchen IMG_3.jpg", "0 exterior IMG_2.jpg", "0 exterior IMG_1.jpg",
         "6 bedroom IMG_9.jpg", "IMG_untagged.jpg", "7 bathroom IMG_5.jpg", "notes.txt"]


@pytest.fixture
def folder(tmp_path):
    for name in NAMES:
        (tmp_path / name).write_bytes(b"x")
    return tmp_path


def test_scan_orders_as_a_tour_and_keeps_untagged(folder):
    photos = lv_photos.scan(folder)
    assert [p["name"] for p in photos] == [
        "0 exterior IMG_1.jpg", "0 exterior IMG_2.jpg", "3 kitchen IMG_3.jpg",
        "6 bedroom IMG_9.jpg", "7 bathroom IMG_5.jpg", "IMG_untagged.jpg"]
    assert photos[-1]["room_code"] == lv_photos.OTHER
    assert [p["n"] for p in photos] == [1, 2, 3, 4, 5, 6]


def test_scan_missing_folder_raises(tmp_path):
    with pytest.raises(RuntimeError):
        lv_photos.scan(tmp_path / "nope")


def picks_for(names):
    return {"landscape": names, "portrait": names}


def test_validate_picks(folder):
    photos = lv_photos.scan(folder)
    good = picks_for(["0 exterior IMG_1.jpg", "3 kitchen IMG_3.jpg", "6 bedroom IMG_9.jpg"])
    assert lv_photos.validate_picks(good, photos) == []
    bad = {"landscape": ["0 exterior IMG_1.jpg", "missing.jpg",
                         {"photo": "3 kitchen IMG_3.jpg", "focus": 3, "callout": "x" * 40}],
           "portrait": ["0 exterior IMG_1.jpg"]}
    problems = lv_photos.validate_picks(bad, photos)
    assert any("unknown photo" in p for p in problems)
    assert any("focus" in p for p in problems)
    assert any("callout" in p for p in problems)
    assert any(p.startswith("portrait") for p in problems)


def test_resolve_labels_first_photo_of_each_room_only(folder):
    photos = lv_photos.scan(folder)
    picks = picks_for(["0 exterior IMG_1.jpg", "0 exterior IMG_2.jpg", "3 kitchen IMG_3.jpg",
                       {"photo": "6 bedroom IMG_9.jpg", "label": "Primary Suite", "callout": "Private balcony"},
                       {"photo": "IMG_untagged.jpg", "label": "Garage"}])
    out = lv_photos.resolve(picks, photos, "landscape")
    assert [p["label"] for p in out] == ["", "", "Kitchen", "Primary Suite", "Garage"]
    assert out[3]["callout"] == "Private balcony"
    assert out[0]["path"].endswith("IMG_1.jpg")


def test_opening_photo_never_gets_label_or_callout(folder):
    photos = lv_photos.scan(folder)
    picks = picks_for([{"photo": "3 kitchen IMG_3.jpg", "label": "Kitchen", "callout": "Granite"},
                       "0 exterior IMG_1.jpg", "6 bedroom IMG_9.jpg"])
    first = lv_photos.resolve(picks, photos, "portrait")[0]
    assert first["label"] == "" and first["callout"] == ""


def test_every_cut_lands_on_a_beat():
    segs, card = lv_beats.timeline(24, 96, 75, open_beats=6, card_seconds=5)
    beat = 60 / 96
    for seg in segs:
        assert abs(seg.start / beat - round(seg.start / beat)) < 1e-3
    assert card.start == pytest.approx(segs[-1].end)
    total = card.end
    assert 65 < total < 85


def test_beats_per_photo_clamps():
    assert lv_beats.beats_per_photo(200, 96, 30, 4, 4) == 2
    assert lv_beats.beats_per_photo(3, 96, 120, 4, 4) == 8


def test_timeline_overrides_hold_a_hero_shot():
    segs, _ = lv_beats.timeline(5, 120, 20, open_beats=4, card_seconds=3, overrides={2: 8})
    assert segs[2].dur == pytest.approx(4.0)
    assert segs[0].dur == pytest.approx(2.0)


def test_tempo_refinement_on_a_synthetic_click_track():
    import numpy as np
    fr, bpm = 43.07, 104.0
    onset = np.zeros(int(60 * fr))
    for t in np.arange(0.3, 59, 60 / bpm):
        onset[int(round(t * fr))] = 1.0
    est, phase = lv_beats.refine(onset, fr, float(lv_beats.estimate_bpm(onset, fr)))
    assert est == pytest.approx(bpm, abs=0.3)
    assert phase == pytest.approx(0.3, abs=0.03)


def test_classify_photographer_names_by_keyword():
    assert lv_photos.classify("Kitchen3.jpg")[0] == lv_photos.classify("kitchen.jpg")[0]
    assert lv_photos.classify("Front2.jpg")[2] == "Exterior"
    assert lv_photos.classify("DSC_0042.jpg")[1] == "other"
