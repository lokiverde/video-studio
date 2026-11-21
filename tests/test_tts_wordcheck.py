"""tts.py word check: a scene whose read does not match its script gets exactly one fresh
take, and whatever is still wrong after it is reported (not fatal)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import tts  # noqa: E402

DATA = {"scenes": [{"id": 1, "narration": "Rent is due."}, {"id": 2, "narration": "Read the lease before you sign."}]}


def run_check(monkeypatch, results):
    calls, retakes = [], []

    def fake_check(job_id, scene_ids=None):
        calls.append(scene_ids)
        return results[len(calls) - 1]

    monkeypatch.setattr(tts.wordcheck, "check_narration", fake_check)
    monkeypatch.setattr(tts, "_narrate_scene", lambda cfg, scene, text, *a: retakes.append((scene["id"], text)))
    left = tts._check_words("job", DATA, {}, "stock", "tim", 1.0, Path("/nowhere"))
    return left, calls, retakes


def test_clean_narration_is_not_retaken(monkeypatch):
    left, calls, retakes = run_check(monkeypatch, [({}, 0)])
    assert left == {} and retakes == [] and calls == [None]


def test_flagged_scene_gets_one_retake_then_clears(monkeypatch):
    left, calls, retakes = run_check(monkeypatch, [({2: ['lost the last word(s) "sign"']}, 0), ({}, 0)])
    assert retakes == [(2, "Read the lease before you sign.")]
    assert calls == [None, {2}]
    assert left == {}


def test_scene_still_wrong_after_the_retake_is_reported_not_retaken_again(monkeypatch):
    still = {2: ['skipped "before you"']}
    left, _, retakes = run_check(monkeypatch, [(still, 0), (still, 0)])
    assert len(retakes) == 1
    assert left == {"2": ['skipped "before you"']}


def test_no_transcriber_skips_quietly(monkeypatch):
    monkeypatch.setattr(tts.wordcheck, "check_narration", lambda *a, **k: None)
    assert tts._check_words("job", DATA, {}, "stock", "tim", 1.0, Path("/nowhere")) == {}
