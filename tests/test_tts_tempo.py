"""Narration tempo: a theme (or a scenes.json) can speed the read up without re-voicing."""
import io
import sys
import wave
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import tts  # noqa: E402


def _silence(seconds: float, rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


def _duration(data: bytes) -> float:
    with wave.open(io.BytesIO(data)) as w:
        return w.getnframes() / w.getframerate()


def test_tempo_defaults_to_one():
    assert tts.resolve_tempo({}, {}) == 1.0


def test_scenes_file_beats_theme():
    assert tts.resolve_tempo({"narration_tempo": 1.2}, {"narration_tempo": 1.1}) == 1.2


def test_theme_tempo_is_used():
    assert tts.resolve_tempo({}, {"narration_tempo": 1.12}) == 1.12


@pytest.mark.parametrize("bad", [0.5, 2.0, "fast", None])
def test_out_of_range_or_junk_tempo_is_rejected(bad):
    with pytest.raises(ValueError):
        tts.resolve_tempo({"narration_tempo": bad}, {})


def test_retime_is_a_no_op_at_one():
    audio = _silence(1.0)
    assert tts.retime(audio, "wav", 1.0) is audio


def test_retime_shortens_the_clip():
    out = tts.retime(_silence(2.0), "wav", 1.25)
    assert _duration(out) == pytest.approx(1.6, abs=0.05)
